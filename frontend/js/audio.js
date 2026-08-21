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
        this.inputStreams = [];
        this.sourceNodes = [];
        this.workletNode = null;
        this.processedStreamDestination = null;
        this.silentGainNode = null;
        this.sourceSampleRate = 48000;
        this.targetSampleRate = null;
        this.sendIntervalMs = null;
        this.isRecording = false;
        this.onAudioData = null;
        this.onLevelUpdate = null;
        this.pendingChunks = [];   
        this.pendingLength = 0;    
        this.sendInterval = null;
        this.workletLoaded = false;
        this.selectedDeviceId = null;
        this.availableDevices = [];

        // Screen share state
        this.screenStream = null;
        this.isScreenSharing = false;
        this.onScreenStream = null;  
        this.onScreenStop = null;

        // WebRTC: when true, audio is sent via WebRTC media track
        // and base64/WebSocket sending is skipped
        this._useWebRTC = false;
    }

    setRuntimeConfig({ sampleRate, sendIntervalMs }) {
        const parsedRate = Number(sampleRate);
        const parsedInterval = Number(sendIntervalMs);
        if (!Number.isFinite(parsedRate) || parsedRate <= 0) {
            throw new Error('Invalid sample rate from backend');
        }
        if (!Number.isFinite(parsedInterval) || parsedInterval <= 0) {
            throw new Error('Invalid audio interval from backend');
        }
        this.targetSampleRate = parsedRate;
        this.sendIntervalMs = parsedInterval;
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
                sampleRate: { ideal: this.targetSampleRate }
            }
        };

        if (this.selectedDeviceId) {
            constraints.audio.deviceId = { exact: this.selectedDeviceId };
        }

        return navigator.mediaDevices.getUserMedia(constraints);
    }


    async startScreenShare(options = {}) {
        const { withAudio = true } = options;
        const stream = await navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: withAudio
                ? {
                    echoCancellation: false,
                    noiseSuppression: false,
                    sampleRate: { ideal: this.targetSampleRate }
                }
                : false
        });

        // Check if audio track exists
        const audioTracks = stream.getAudioTracks();
        if (withAudio && audioTracks.length === 0) {
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

        if (this.onScreenStream) this.onScreenStream(stream);

        return stream;
    }


    stopScreenShare() {
        if (this.screenStream) {
            this.screenStream.getTracks().forEach(t => t.stop());
            this.screenStream = null;
        }
        this.isScreenSharing = false;

        if (this.onScreenStop) this.onScreenStop();
        console.log('[Audio] Screen share stopped');
    }

    async getComputerAudioStream() {
        const displayStream = await navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                sampleRate: { ideal: this.targetSampleRate }
            }
        });

        displayStream.getVideoTracks().forEach(t => t.stop());
        if (displayStream.getAudioTracks().length === 0) {
            throw new Error('No audio — enable "Share audio"');
        }

        return displayStream;
    }

    /**
     * Start recording from the given source.
     * @param {'microphone' | 'computer' | 'screen' | 'mixed'} source
     */
    async startRecording(source = 'microphone') {
        if (!this.targetSampleRate || !this.sendIntervalMs) {
            throw new Error('Audio runtime config is not loaded from backend');
        }
        await this.init();

        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }

        this.inputStreams = [];
        this.sourceNodes = [];
        this.mediaStream = null;
        this.sourceNode = null;

        try {
            if (source === 'screen') {
                // Screen share: get audio from screen share stream
                const screenStream = await this.startScreenShare();
                const audioTracks = screenStream.getAudioTracks();

                if (audioTracks.length > 0) {
                    // Create an audio-only stream from the screen share
                    this.inputStreams = [new MediaStream(audioTracks)];
                } else {
                    // Fallback: also get mic audio if no screen audio
                    console.log('[Audio] No screen audio, falling back to mic');
                    this.inputStreams = [await this.getMicrophoneStream()];
                }
            } else if (source === 'computer') {
                this.inputStreams = [await this.getComputerAudioStream()];
            } else if (source === 'mixed') {
                // Mix computer audio + microphone into the same processing node.
                const [computerStream, micStream] = await Promise.all([
                    this.getComputerAudioStream(),
                    this.getMicrophoneStream()
                ]);
                this.inputStreams = [computerStream, micStream];
            } else {
                this.inputStreams = [await this.getMicrophoneStream()];
            }
        } catch (err) {
            console.error('[Audio] Failed to get stream:', err);
            throw err;
        }

        if (this.workletLoaded) {
            this.workletNode = new AudioWorkletNode(this.audioContext, 'recorder-worklet');

            this.workletNode.port.onmessage = (event) => {
                if (!this.isRecording) return;
                const { command, inputBuffer, rms } = event.data;
                if (command === 'process') {
                    this.processAudioChunk(inputBuffer, rms);
                } else if (command === 'level' && this.onLevelUpdate) {
                    this.onLevelUpdate(rms);
                }
            };

            this.sourceNodes = this.inputStreams.map((stream) => this.audioContext.createMediaStreamSource(stream));
            this.sourceNodes.forEach((node) => node.connect(this.workletNode));

            // Keep legacy fields for compatibility with existing call sites.
            this.mediaStream = this.inputStreams[0] || null;
            this.sourceNode = this.sourceNodes[0] || null;

            // Capture the exact Web Audio mix (including mixed mic + computer)
            // as a MediaStream that can be attached to WebRTC.
            this.processedStreamDestination = this.audioContext.createMediaStreamDestination();
            this.workletNode.connect(this.processedStreamDestination);

            // Keep the graph alive without playing captured audio to speakers.
            this.silentGainNode = this.audioContext.createGain();
            this.silentGainNode.gain.value = 0;
            this.workletNode.connect(this.silentGainNode);
            this.silentGainNode.connect(this.audioContext.destination);
        } else {
            console.error('[Audio] Worklet not loaded, recording disabled');
            return;
        }

        this.pendingChunks = [];
        this.pendingLength = 0;
        this.sendInterval = setInterval(() => this.flushBuffer(), this.sendIntervalMs);

        this.isRecording = true;
        console.log('[Audio] Recording started (' + source + '), resampling', this.sourceSampleRate, '->', this.targetSampleRate);
    }

    processAudioChunk(inputData, measuredRms = null) {
        if (!this.isRecording) return;

        const rms = measuredRms ?? calculateRMS(inputData);
        if (this.onLevelUpdate) {
            this.onLevelUpdate(rms);
        }

        if (this.useWebRTC) return;

        // Accumulate native-rate frames and resample the complete 250 ms block.
        // Resampling each 128-sample worklet frame causes rounding drift.
        this.pendingChunks.push(inputData);
        this.pendingLength += inputData.length;
    }

    flushBuffer() {
        if (!this.isRecording || this.pendingLength === 0) return;

        const nativeAudio = new Float32Array(this.pendingLength);
        let offset = 0;
        for (const chunk of this.pendingChunks) {
            nativeAudio.set(chunk, offset);
            offset += chunk.length;
        }
        this.pendingChunks = [];
        this.pendingLength = 0;

        if (this.useWebRTC) return;

        const float32 = linearResample(nativeAudio, this.sourceSampleRate, this.targetSampleRate);

        const int16 = float32ToInt16(float32);
        const base64 = int16ToBase64(int16);

        if (this.onAudioData && base64.length > 0) {
            this.onAudioData(base64);
        }
    }

    stopRecording() {
        if (this.sendInterval) {
            clearInterval(this.sendInterval);
            this.sendInterval = null;
        }

        // Flush the last WebSocket block while recording is still marked active.
        this.flushBuffer();
        this.isRecording = false;

        if (this.workletNode) {
            this.workletNode.disconnect();
            this.workletNode = null;
        }

        if (this.silentGainNode) {
            this.silentGainNode.disconnect();
            this.silentGainNode = null;
        }
        this.processedStreamDestination = null;

        this.sourceNodes.forEach((node) => node.disconnect());
        this.sourceNodes = [];

        this.inputStreams.forEach((stream) => {
            stream.getTracks().forEach((t) => t.stop());
        });
        this.inputStreams = [];

        this.sourceNode = null;
        this.mediaStream = null;

        if (this.isScreenSharing) {
            this.stopScreenShare();
        }

        console.log('[Audio] Recording stopped');
    }

    set useWebRTC(enabled) {
        this._useWebRTC = Boolean(enabled);
        this.workletNode?.port.postMessage({
            command: 'set-webrtc',
            enabled: this._useWebRTC,
        });
    }

    get useWebRTC() {
        return this._useWebRTC;
    }
    /**
     * Get the active audio MediaStream (for WebRTC transport).
     * @returns {MediaStream|null}
     */
    getActiveStream() {
        if (this.processedStreamDestination?.stream?.getAudioTracks().length) {
            return this.processedStreamDestination.stream;
        }
        if (this.inputStreams.length > 0) {
            return this.inputStreams[0];
        }
        return this.mediaStream;
    }
}

export { AudioManager };
