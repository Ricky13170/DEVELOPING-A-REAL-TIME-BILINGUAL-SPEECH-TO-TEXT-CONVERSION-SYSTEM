const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;
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
        this.pendingBuffer = [];
        this.sendInterval = null;
        this.workletLoaded = false;
        this.selectedDeviceId = null;
        this.availableDevices = [];
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
            // Request permission first
            await navigator.mediaDevices.getUserMedia({ audio: true });

            const devices = await navigator.mediaDevices.enumerateDevices();
            const mics = devices.filter(d => d.kind === 'audioinput' && d.deviceId);

            // Get top 3 microphones
            this.availableDevices = mics.slice(0, 3).map((d, i) => ({
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

    async getComputerAudioStream() {
        const stream = await navigator.mediaDevices.getDisplayMedia({
            video: true,
            audio: {
                echoCancellation: false,
                noiseSuppression: false,
                sampleRate: { ideal: 16000 }
            }
        });
        stream.getVideoTracks().forEach(t => t.stop());
        if (stream.getAudioTracks().length === 0) {
            throw new Error('No audio - enable "Share audio"');
        }
        return stream;
    }

    async startRecording(source = 'microphone') {
        await this.init();

        if (this.audioContext.state === 'suspended') {
            await this.audioContext.resume();
        }

        try {
            this.mediaStream = source === 'computer'
                ? await this.getComputerAudioStream()
                : await this.getMicrophoneStream();
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

        this.pendingBuffer = [];
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
        this.pendingBuffer.push(...resampled);
    }

    flushBuffer() {
        if (!this.isRecording || this.pendingBuffer.length === 0) return;

        const float32 = new Float32Array(this.pendingBuffer);
        this.pendingBuffer = [];

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

        console.log('[Audio] Recording stopped');
    }
}

export { AudioManager };