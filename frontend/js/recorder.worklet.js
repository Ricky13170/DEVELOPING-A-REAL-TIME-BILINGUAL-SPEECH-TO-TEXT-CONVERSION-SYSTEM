class RecorderWorklet extends AudioWorkletProcessor {
    constructor() {
        super();
        this.useWebRTC = false;
        this.port.onmessage = (event) => {
            if (event.data?.command === 'set-webrtc') {
                this.useWebRTC = Boolean(event.data.enabled);
            }
        };
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0];

            // Forward the Web Audio mix to the output. A MediaStreamDestination
            // consumes this output when WebRTC is enabled.
            const output = outputs[0];
            if (output) {
                for (const outputChannel of output) {
                    outputChannel.set(channelData);
                }
            }

            // RMS for audio level meter (computed on audio thread to keep main thread free)
            let sum = 0;
            for (let i = 0; i < channelData.length; i++) {
                sum += channelData[i] * channelData[i];
            }
            const rms = Math.sqrt(sum / channelData.length);

            if (this.useWebRTC) {
                this.port.postMessage({ command: 'level', rms });
            } else {
                const copy = channelData.slice();
                this.port.postMessage(
                    { command: 'process', inputBuffer: copy, rms },
                    [copy.buffer]
                );
            }
        }
        return true;
    }
}

registerProcessor('recorder-worklet', RecorderWorklet);
