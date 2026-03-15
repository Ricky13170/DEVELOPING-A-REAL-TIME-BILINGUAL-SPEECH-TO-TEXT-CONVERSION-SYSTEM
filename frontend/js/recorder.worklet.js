class RecorderWorklet extends AudioWorkletProcessor {
    constructor() {
        super();
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0];

            // RMS for audio level meter (computed on audio thread to keep main thread free)
            let sum = 0;
            for (let i = 0; i < channelData.length; i++) {
                sum += channelData[i] * channelData[i];
            }
            const rms = Math.sqrt(sum / channelData.length);

            // Copy buffer so we can transfer ownership (zero-copy to main thread)
            const copy = channelData.slice();
            this.port.postMessage(
                { command: 'process', inputBuffer: copy, rms },
                [copy.buffer] 
            );
        }
        return true;
    }
}

registerProcessor('recorder-worklet', RecorderWorklet);
