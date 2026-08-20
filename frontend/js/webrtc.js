/**
 * WebRTC Audio Transport
 *
 * Provides ultra-low latency audio streaming via WebRTC,
 * falling back to WebSocket (base64) when unavailable.
 *
 * Signaling is done over the existing WebSocket connection.
 */

export class WebRTCTransport {
    /**
     * @param {WebSocket} ws - Existing WebSocket for signaling
     * @param {Function} onStateChange - Callback: (state: string) => void
     */
    constructor(ws, onStateChange = null) {
        this.ws = ws;
        this.onStateChange = onStateChange;

        /** @type {RTCPeerConnection|null} */
        this.pc = null;

        /** @type {MediaStream|null} */
        this.localStream = null;

        this.connected = false;
        this._iceCandidateQueue = [];
        this._connectTimeoutMs = 3000;
    }

    /**
     * Check if WebRTC is supported in this browser.
     */
    static isSupported() {
        return !!(
            window.RTCPeerConnection &&
            navigator.mediaDevices &&
            navigator.mediaDevices.getUserMedia
        );
    }

    /**
     * Initialize WebRTC connection with the server.
     *
     * @param {MediaStream} stream - Audio stream from getUserMedia
     * @returns {Promise<boolean>} True if connection was established
     */
    async connect(stream) {
        if (!WebRTCTransport.isSupported()) {
            console.warn('[WebRTC] Not supported in this browser');
            return false;
        }

        this.localStream = stream;

        // Local-only mode intentionally avoids public STUN/TURN calls. Host
        // Host candidates cover localhost/LAN; WebSocket remains the fallback.
        const config = { iceServers: [] };

        this.pc = new RTCPeerConnection(config);

        // Add audio tracks to the connection
        for (const track of stream.getAudioTracks()) {
            this.pc.addTrack(track, stream);
        }

        // Handle ICE candidates
        this.pc.onicecandidate = (event) => {
            if (event.candidate) {
                this._sendSignaling({
                    type: 'webrtc_ice',
                    candidate: {
                        candidate: event.candidate.candidate,
                        sdpMid: event.candidate.sdpMid,
                        sdpMLineIndex: event.candidate.sdpMLineIndex,
                    }
                });
            }
        };

        // Track connection state
        this.pc.onconnectionstatechange = () => {
            const state = this.pc.connectionState;
            console.log(`[WebRTC] Connection state: ${state}`);
            this.connected = (state === 'connected');
            this.onStateChange?.(state);

            if (state === 'failed') {
                console.warn('[WebRTC] Connection failed, falling back to WebSocket');
                this.close();
            }
        };

        // Create and send offer
        try {
            const offer = await this.pc.createOffer({
                offerToReceiveAudio: false,
                offerToReceiveVideo: false,
            });
            await this.pc.setLocalDescription(offer);

            this._sendSignaling({
                type: 'webrtc_offer',
                sdp: offer.sdp,
            });

            console.log('[WebRTC] Offer sent, waiting for connection...');
            const connected = await this._waitUntilConnected();
            if (!connected) this.close();
            return connected;
        } catch (err) {
            console.error('[WebRTC] Failed to create offer:', err);
            this.close();
            return false;
        }
    }

    _waitUntilConnected() {
        return new Promise((resolve) => {
            let settled = false;
            const finish = (connected) => {
                if (settled) return;
                settled = true;
                clearTimeout(timeout);
                this.pc?.removeEventListener('connectionstatechange', checkState);
                resolve(connected);
            };
            const checkState = () => {
                const state = this.pc?.connectionState;
                if (state === 'connected') finish(true);
                if (['failed', 'closed', 'disconnected'].includes(state)) finish(false);
            };
            const timeout = setTimeout(() => finish(false), this._connectTimeoutMs);
            this.pc?.addEventListener('connectionstatechange', checkState);
            checkState();
        });
    }

    /**
     * Handle signaling messages from the server (called by SocketManager).
     *
     * @param {Object} data - Parsed message from server
     */
    async handleSignaling(data) {
        if (!this.pc) return;

        try {
            if (data.type === 'webrtc_answer') {
                const answer = new RTCSessionDescription({
                    type: 'answer',
                    sdp: data.sdp,
                });
                await this.pc.setRemoteDescription(answer);
                console.log('[WebRTC] Answer received, connection establishing...');

                // Flush queued ICE candidates
                for (const candidate of this._iceCandidateQueue) {
                    await this.pc.addIceCandidate(candidate);
                }
                this._iceCandidateQueue = [];

            } else if (data.type === 'webrtc_ice') {
                const candidate = new RTCIceCandidate(data.candidate);
                if (this.pc.remoteDescription) {
                    await this.pc.addIceCandidate(candidate);
                } else {
                    this._iceCandidateQueue.push(candidate);
                }

            } else if (data.type === 'webrtc_error') {
                console.warn('[WebRTC] Server error:', data.message);
                this.close();
            }
        } catch (err) {
            console.error('[WebRTC] Signaling error:', err);
        }
    }

    /**
     * Send a signaling message through the WebSocket.
     * @private
     */
    _sendSignaling(msg) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(msg));
        }
    }

    /**
     * Close the WebRTC connection.
     */
    close() {
        if (this.pc) {
            this.pc.close();
            this.pc = null;
        }
        this.connected = false;
        this._iceCandidateQueue = [];
        console.log('[WebRTC] Connection closed');
    }

    /**
     * Whether audio is currently being streamed via WebRTC.
     */
    get isStreaming() {
        return this.connected && this.pc?.connectionState === 'connected';
    }
}
