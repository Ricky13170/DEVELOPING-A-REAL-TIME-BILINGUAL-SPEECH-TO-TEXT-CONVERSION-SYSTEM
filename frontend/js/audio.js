const SAMPLE_RATE = 16000;
const SEND_INTERVAL_MS = 250;

function linearResample(buffer, fromRate, toRate) {
    if (fromRate === toRate) return buffer;

    const ratio = fromRate / toRate;
    const newLength = Math.ceil(buffer.length / ratio);
    const result = new Float32Array(newLength);

    for (let i = 0; i < newLength; i++) {
        const srcIndex = i * ratio;
        const srcIndexFloor = Math.floor(srcIndex);
        const srcIndexCeil = Math.min(srcIndexFloor + 1, buffer.length - 1);
        const fraction = srcIndex - srcIndexFloor;
        result[i] = buffer[srcIndexFloor] * (1 - fraction) + buffer[srcIndexCeil] * fraction;
    }

    return result;
}

function float32ToInt16(float32) {
    const int16 = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i++) {
        const s = Math.max(-1, Math.min(1, float32[i]));
        int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return int16;
}

function int16ToBase64(int16Array) {
    const bytes = new Uint8Array(int16Array.buffer);
    let binary = '';
    const chunkSize = 8192;
    for (let i = 0; i < bytes.length; i += chunkSize) {
        const chunk = bytes.subarray(i, i + chunkSize);
        binary += String.fromCharCode.apply(null, chunk);
    }
    return btoa(binary);
}

function calculateRMS(buffer) {
    if (!buffer || buffer.length === 0) return 0;
    let sum = 0;
    for (let i = 0; i < buffer.length; i++) {
        sum += buffer[i] * buffer[i];
    }
    return Math.sqrt(sum / buffer.length);
}

class AudioManager {
    constructor() {
        this.audioContext = null;
        this.mediaStream = null;
        this.sourceNode = null;
        this.workletNode = null;
        this.sourceSampleRate = 48000;
        this.isRecording = false;
        this.onAudioData = null;
        this.onLevelUpdate = null;
        this.pendingChunks = [];    // Array of Float32Array chunks (avoids spread)
        this.pendingLength = 0;     // Total samples across chunks
        this.sendInterval = null;
        this.workletLoaded = false;
        this.selectedDeviceId = null;
        this.availableDevices = [];

        // Screen share state
        this.screenStream = null;
        this.isScreenSharing = false;
        this.onScreenStream = null;     // callback: (stream) => show video
        this.onScreenStop = null;       // callback: () => hide video
    }

    async init() {
        if (this.audioContext) return;
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.sourceSampleRate = this.audioContext.sampleRate;
        console.log('[Audio] Native sample rate:', this.sourceSampleRate);

        try {
            await this.audioContext.audioWorklet.addModule('js/recorder.worklet.js');
            this.workletLoaded = true;
            console.log('[Audio] Worklet module loaded');
        } catch (e) {
            console.error('[Audio] Failed to load worklet:', e);
        }
    }

    async getAvailableMicrophones() {
        try {
            await navigator.mediaDevices.getUserMedia({ audio: true });
            const devices = await navigator.mediaDevices.enumerateDevices();
            const mics = devices.filter(d => d.kind === 'audioinput' && d.deviceId);

            this.availableDevices = mics.slice(0, 5).map((d, i) => ({
                deviceId: d.deviceId,
                label: d.label || `Microphone ${i + 1}`,
                isDefault: d.deviceId === 'default' || i === 0
            }));

            console.log('[Audio] Available mics:', this.availableDevices);
            return this.availableDevices;
        } catch (e) {
            console.error('[Audio] Cannot enumerate devices:', e);
            return [];
        }
    }

    setMicrophone(deviceId) {
        this.selectedDeviceId = deviceId;
        console.log('[Audio] Selected mic:', deviceId);
    }

    async getMicrophoneStream() {
        const constraints = {
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
                channelCount: 1,
                sampleRate: { ideal: 16000 }
            }
        };

        if (this.selectedDeviceId) {
            constraints.audio.deviceId = { exact: this.selectedDeviceId };
        }

        return navigator.mediaDevices.getUserMedia(constraints);
    }

    /**
     * Start screen sharing — captures both video AND audio.
     * Returns the full MediaStream (with video tracks for preview).
     */
    async startScreenShare() {
        const stream = await navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                sampleRate: { ideal: 16000 }
            }
        });

        // Check if audio track exists
        const audioTracks = stream.getAudioTracks();
        if (audioTracks.length === 0) {
            // No audio — still show video but warn
            console.warn('[Audio] Screen share has no audio track. Make sure to check "Share audio".');
        }

        this.screenStream = stream;
        this.isScreenSharing = true;

        // Listen for the user clicking browser's "Stop sharing" button
        stream.getVideoTracks().forEach(track => {
            track.onended = () => {
                console.log('[Audio] Screen share stopped by user');
                this.stopScreenShare();
            };
        });

        // Notify UI to show video preview
        if (this.onScreenStream) this.onScreenStream(stream);

        return stream;
    }

    /**
     * Stop screen sharing — cleans up video + audio tracks.
     */
    stopScreenShare() {
        if (this.screenStream) {
            this.screenStream.getTracks().forEach(t => t.stop());
            this.screenStream = null;
        }
        this.isScreenSharing = false;

        if (this.onScreenStop) this.onScreenStop();
        console.log('[Audio] Screen share stopped');
    }

    /**
     * Start recording from the given source.
     * @param {'microphone' | 'computer' | 'screen'} source
     */
    async startRecording(source = 'microphone') {
        await this.init();

        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }

        try {
            if (source === 'screen') {
                // Screen share: get audio from screen share stream
                const screenStream = await this.startScreenShare();
                const audioTracks = screenStream.getAudioTracks();

                if (audioTracks.length > 0) {
                    // Create an audio-only stream from the screen share
                    this.mediaStream = new MediaStream(audioTracks);
                } else {
                    // Fallback: also get mic audio if no screen audio
                    console.log('[Audio] No screen audio, falling back to mic');
                    this.mediaStream = await this.getMicrophoneStream();
                }
            } else if (source === 'computer') {
                // Pure computer audio (getDisplayMedia, no video preview)
                const displayStream = await navigator.mediaDevices.getDisplayMedia({
                    video: true,
                    audio: {
                        echoCancellation: false,
                        noiseSuppression: false,
                        sampleRate: { ideal: 16000 }
                    }
                });
                displayStream.getVideoTracks().forEach(t => t.stop());
                if (displayStream.getAudioTracks().length === 0) {
                    throw new Error('No audio — enable "Share audio"');
                }
                this.mediaStream = displayStream;
            } else {
                this.mediaStream = await this.getMicrophoneStream();
            }
        } catch (err) {
            console.error('[Audio] Failed to get stream:', err);
            throw err;
        }

        this.sourceNode = this.audioContext.createMediaStreamSource(this.mediaStream);

        if (this.workletLoaded) {
            this.workletNode = new AudioWorkletNode(this.audioContext, 'recorder-worklet');

            this.workletNode.port.onmessage = (event) => {
                if (!this.isRecording) return;
                const { command, inputBuffer } = event.data;
                if (command === 'process') {
                    this.processAudioChunk(inputBuffer);
                }
            };

            this.sourceNode.connect(this.workletNode);
            this.workletNode.connect(this.audioContext.destination);
        } else {
            console.error('[Audio] Worklet not loaded, recording disabled');
            return;
        }

        this.pendingChunks = [];
        this.pendingLength = 0;
        this.sendInterval = setInterval(() => this.flushBuffer(), SEND_INTERVAL_MS);

        this.isRecording = true;
        console.log('[Audio] Recording started (' + source + '), resampling', this.sourceSampleRate, '->', SAMPLE_RATE);
    }

    processAudioChunk(inputData) {
        if (!this.isRecording) return;

        const rms = calculateRMS(inputData);
        if (this.onLevelUpdate) {
            this.onLevelUpdate(rms);
        }

        const resampled = linearResample(inputData, this.sourceSampleRate, SAMPLE_RATE);
        this.pendingChunks.push(resampled);
        this.pendingLength += resampled.length;
    }

    flushBuffer() {
        if (!this.isRecording || this.pendingLength === 0) return;

        // Concatenate chunks into a single Float32Array (zero-copy pattern)
        const float32 = new Float32Array(this.pendingLength);
        let offset = 0;
        for (const chunk of this.pendingChunks) {
            float32.set(chunk, offset);
            offset += chunk.length;
        }
        this.pendingChunks = [];
        this.pendingLength = 0;

        const int16 = float32ToInt16(float32);
        const base64 = int16ToBase64(int16);

        if (this.onAudioData && base64.length > 0) {
            this.onAudioData(base64);
        }
    }

    stopRecording() {
        this.isRecording = false;

        if (this.sendInterval) {
            clearInterval(this.sendInterval);
            this.sendInterval = null;
        }

        this.flushBuffer();

        if (this.workletNode) {
            this.workletNode.disconnect();
            this.workletNode = null;
        }

        if (this.sourceNode) {
            this.sourceNode.disconnect();
            this.sourceNode = null;
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(t => t.stop());
            this.mediaStream = null;
        }

        // Stop screen share if active
        if (this.isScreenSharing) {
            this.stopScreenShare();
        }

        console.log('[Audio] Recording stopped');
    }
}

export { AudioManager };