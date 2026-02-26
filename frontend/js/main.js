import { AudioManager } from './audio.js';
import { SocketManager } from './socket.js';
import { UIManager } from './ui.js';
import { exportSRT, exportVTT, exportTXT, exportJSON } from './export.js';

class ASRApp {
    constructor() {
        this.audioMgr = new AudioManager();
        this.socketMgr = new SocketManager();
        this.uiMgr = new UIManager();
        this.isRecording = false;
        this.isConnecting = false;
        this.serverReady = false;
        this.transcripts = {};
        this.sessionId = null;
        this.lectureTopic = '';
    }

    async init() {
        this.setupAudioCallbacks();
        this.setupSocketCallbacks();
        this.setupUIHandlers();
        this.setupExportHandlers();
        this.uiMgr.updateRecordButton(false);
        await this.loadMicrophones();
        await this.checkServerStatus();
    }

    async loadMicrophones() {
        try {
            const mics = await this.audioMgr.getAvailableMicrophones();
            const micList = document.getElementById('micList');
            if (micList && mics.length > 0) {
                micList.innerHTML = mics.map((mic, i) => `
                    <div class="dropdown-item mic-item" data-source="microphone" data-device="${mic.deviceId}">
                        ${mic.label}
                    </div>
                `).join('');
            }
        } catch (e) {
            console.log('[Mics] Could not enumerate devices');
        }
    }

    async checkServerStatus() {
        const statusEl = document.getElementById('loadingStatus');
        const hintEl = document.querySelector('.loading-hint');
        const spinnerEl = document.getElementById('loadingSpinner');

        try {
            if (statusEl) statusEl.textContent = 'Connecting to server...';
            if (hintEl) hintEl.textContent = 'Models are loading, this may take a moment';

            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                this.serverReady = true;

                // Update loading state to ready
                if (spinnerEl) spinnerEl.classList.add('hidden');
                if (statusEl) {
                    statusEl.textContent = `✓ Ready — ${data.model || 'Whisper'}`;
                    statusEl.classList.add('ready');
                }
                if (hintEl) hintEl.textContent = 'Click the record button to start transcribing';

                this.uiMgr.showNotification(`Ready: ${data.model || 'Whisper'}`);
            }
        } catch (e) {
            if (statusEl) statusEl.textContent = 'Server is starting up...';
            if (hintEl) hintEl.textContent = 'Cold start may take 30-60 seconds';
            this.uiMgr.showNotification('Server loading...');

            // Retry after 5 seconds
            setTimeout(() => this.checkServerStatus(), 5000);
        }
    }

    setupAudioCallbacks() {
        this.audioMgr.onAudioData = (b64) => {
            if (this.isRecording && this.socketMgr.isConnected()) {
                this.socketMgr.send('audio', { audio: b64 });
            }
        };
        this.audioMgr.onLevelUpdate = (rms) => {
            if (this.isRecording) this.uiMgr.updateAudioMeter(rms);
        };
    }

    setupSocketCallbacks() {
        this.socketMgr.onMessage = (data) => {
            if (data.type === 'transcript') {
                this.uiMgr.addTranscriptSegment(data);

                if (data.is_final && (data.source || data.target)) {
                    const id = data.segment_id || Object.keys(this.transcripts).length + 1;
                    if (!this.transcripts[id]) this.transcripts[id] = { vi: '', en: '' };
                    if (data.source) this.transcripts[id].vi = data.source;
                    if (data.target) this.transcripts[id].en = data.target;
                }
            } else if (data.type === 'summary') {
                this.uiMgr.showSummary(data);
            } else if (data.type === 'status') {
                if (data.status === 'started') {
                    this.uiMgr.showNotification('Recording...');
                } else if (data.status === 'stopped') {
                    this.uiMgr.showNotification('Stopped');
                }
            } else if (data.type === 'log') {
                this.uiMgr.showNotification(data.message || '');
            }
        };

        this.socketMgr.onConnected = () => {
            this.isConnecting = false;
            this.serverReady = true;
        };

        this.socketMgr.onDisconnected = () => {
            if (this.isRecording) {
                this.uiMgr.showNotification('Disconnected');
                this.stopRecording();
            }
        };

        this.socketMgr.onError = () => {
            this.isConnecting = false;
            this.uiMgr.showNotification('Connection error');
        };
    }

    setupUIHandlers() {
        if (this.uiMgr.el.recordBtn) {
            this.uiMgr.el.recordBtn.onclick = () => {
                if (this.isRecording) this.stopRecording();
                else this.startRecording();
            };
        }

        this.uiMgr.onContextSave = (data) => {
            this.lectureTopic = data.topic || '';
            if (this.socketMgr.isConnected()) {
                this.socketMgr.send('context', data);
                this.uiMgr.showNotification('Context saved');
            }
        };

        this.uiMgr.onSummarize = () => {
            if (this.socketMgr.isConnected()) {
                this.socketMgr.send('summarize');
                this.uiMgr.showNotification('Generating summary...');
            } else {
                this.uiMgr.showNotification('Not connected');
            }
        };

        // Microphone selection
        const audioDropdown = document.getElementById('audioDropdown');
        if (audioDropdown) {
            audioDropdown.addEventListener('click', (e) => {
                const item = e.target.closest('[data-source]');
                if (!item) return;

                const source = item.dataset.source;
                const deviceId = item.dataset.device;

                if (source === 'microphone' && deviceId) {
                    this.audioMgr.setMicrophone(deviceId);
                    this.uiMgr.setAudioSource('microphone');
                    const label = item.textContent.trim();
                    document.getElementById('audioSourceText').textContent = label.substring(0, 20);
                } else if (source === 'computer') {
                    this.uiMgr.setAudioSource('computer');
                }

                audioDropdown.classList.remove('active');
            });
        }
    }

    setupExportHandlers() {
        const exportBtn = document.getElementById('exportBtn');
        const exportDropdown = document.getElementById('exportDropdown');

        if (exportBtn) {
            exportBtn.onclick = (e) => {
                e.stopPropagation();
                exportDropdown?.classList.toggle('active');
            };
        }

        if (exportDropdown) {
            exportDropdown.querySelectorAll('[data-export]').forEach(item => {
                item.onclick = () => {
                    const format = item.dataset.export;
                    const segments = Object.values(this.transcripts).filter(t => t.vi || t.en);

                    if (segments.length === 0) {
                        this.uiMgr.showNotification('No transcripts');
                        return;
                    }

                    switch (format) {
                        case 'srt': exportSRT(segments); break;
                        case 'vtt': exportVTT(segments); break;
                        case 'txt': exportTXT(segments); break;
                        case 'json': exportJSON(segments); break;
                    }

                    this.uiMgr.showNotification(`Exported ${format.toUpperCase()}`);
                    exportDropdown.classList.remove('active');
                };
            });
        }

        document.addEventListener('click', () => {
            exportDropdown?.classList.remove('active');
        });
    }

    async startRecording() {
        if (this.isConnecting) return;
        if (!this.serverReady) {
            this.uiMgr.showNotification('Server loading...');
            await this.checkServerStatus();
            if (!this.serverReady) return;
        }

        this.isConnecting = true;
        this.uiMgr.showNotification('Connecting...');

        try {
            if (!this.socketMgr.isConnected()) {
                await this.socketMgr.connect();
            }

            const source = this.uiMgr.getAudioSource();
            await this.audioMgr.startRecording(source);

            this.uiMgr.clearTranscripts();
            this.transcripts = {};
            this.sessionId = Date.now();

            const topic = this.lectureTopic || this.uiMgr.getLectureTopic() || '';

            this.socketMgr.send('start', {
                srcLang: null,
                tgtLang: 'en',
                translate: true,
                topic: topic
            });

            this.isRecording = true;
            this.isConnecting = false;
            this.uiMgr.startTimer();
            this.uiMgr.updateRecordButton(true);

        } catch (err) {
            this.isConnecting = false;
            this.isRecording = false;
            this.uiMgr.updateRecordButton(false);
            this.uiMgr.resetAudioMeter();
            this.uiMgr.showNotification(err.message || 'Could not start');
        }
    }

    async stopRecording() {
        if (this.socketMgr.isConnected()) {
            this.socketMgr.send('stop');
        }

        this.audioMgr.stopRecording();

        this.isRecording = false;
        this.isConnecting = false;
        this.uiMgr.stopTimer();
        this.uiMgr.resetAudioMeter();
        this.uiMgr.updateRecordButton(false);

        await new Promise(r => setTimeout(r, 1500));
        this.saveRecording();
    }

    saveRecording() {
        const segments = Object.values(this.transcripts).filter(t => t.vi || t.en);
        if (segments.length === 0) return;

        try {
            const recordings = JSON.parse(localStorage.getItem('recordings') || '[]');
            const now = new Date();

            const rec = {
                id: this.sessionId,
                date: now.toLocaleDateString('en-CA').replace(/-/g, '.'),
                time: now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }),
                duration: this.uiMgr.el.timer?.textContent || '00:00',
                transcript: segments.map(t => ({
                    vi: t.vi || '',
                    en: t.en || '',
                    source: t.vi || '',
                    target: t.en || ''
                }))
            };

            recordings.unshift(rec);
            if (recordings.length > 50) recordings.pop();

            localStorage.setItem('recordings', JSON.stringify(recordings));
            this.uiMgr.showNotification(`Saved ${segments.length} segments`);
            this.uiMgr.loadRecordingsSidebar();
        } catch (e) {
            console.error('[Save] Error:', e);
        }
    }
}

window.addEventListener('DOMContentLoaded', () => {
    const app = new ASRApp();
    app.init();
});
