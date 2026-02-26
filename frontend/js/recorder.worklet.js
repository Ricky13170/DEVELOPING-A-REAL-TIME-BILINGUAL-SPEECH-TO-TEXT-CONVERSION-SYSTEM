class RecorderWorklet extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 4096;
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;
    }

    calculateRMS(data) {
        let sum = 0;
        for (let i = 0; i < data.length; i++) {
            sum += data[i] * data[i];
        }
        return Math.sqrt(sum / data.length);
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0];

            const rms = this.calculateRMS(channelData);

            this.port.postMessage({
                command: 'process',
                inputBuffer: channelData,
                rms: rms
            });
        }
        return true;
    }
}

registerProcessor('recorder-worklet', RecorderWorklet);