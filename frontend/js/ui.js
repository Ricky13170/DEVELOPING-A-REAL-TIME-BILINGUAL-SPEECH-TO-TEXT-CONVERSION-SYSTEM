class UIManager {
    constructor() {
        this.el = {
            audioSourceBtn: document.getElementById('audioSourceBtn'),
            audioSourceText: document.getElementById('audioSourceText'),
            audioDropdown: document.getElementById('audioDropdown'),
            audioMeter: document.getElementById('audioMeter'),
            timer: document.getElementById('timer'),
            recordBtn: document.getElementById('recordBtn'),
            panelContent: document.getElementById('panelContent'),
            fontDecrease: document.getElementById('fontDecrease'),
            fontIncrease: document.getElementById('fontIncrease'),
            contextBtn: document.getElementById('contextBtn'),
            copyBtn: document.getElementById('copyBtn'),
            clearBtn: document.getElementById('clearBtn'),
            sidebar: document.getElementById('sidebar'),
            sidebarToggle: document.getElementById('sidebarToggle'),
            recordingsList: document.getElementById('recordingsList'),
            contextModal: document.getElementById('contextModal'),
            closeModal: document.getElementById('closeModal'),
            keywords: document.getElementById('keywords'),
            context: document.getElementById('context'),
            clearContextBtn: document.getElementById('clearContextBtn'),
            saveContextBtn: document.getElementById('saveContextBtn'),
            notification: document.getElementById('notification'),
            clearModal: document.getElementById('clearModal'),
            deleteRecordingModal: document.getElementById('deleteRecordingModal'),
            lectureTopic: document.getElementById('lectureTopic'),
            aiGenerateBtn: document.getElementById('aiGenerateBtn'),
            summarizeBtn: document.getElementById('summarizeBtn'),
            summaryModal: document.getElementById('summaryModal'),
            summaryContent: document.getElementById('summaryContent'),
        };

        this.timerInterval = null;
        this.startTime = null;
        this.currentSource = 'microphone';
        this.fontSizeLevel = 0;
        this.pendingDeleteId = null;
        this.onContextSave = null;
        this.onSummarize = null;
        this.displayedSegments = new Map();

        this.setupEventHandlers();
    }

    setupEventHandlers() {
        if (this.el.audioSourceBtn) {
            this.el.audioSourceBtn.onclick = (e) => {
                e.stopPropagation();
                this.el.audioDropdown?.classList.toggle('active');
            };
        }

        document.addEventListener('click', () => {
            this.el.audioDropdown?.classList.remove('active');
        });

        if (this.el.audioDropdown) {
            this.el.audioDropdown.querySelectorAll('.dropdown-item').forEach(item => {
                item.onclick = () => {
                    this.setAudioSource(item.dataset.source);
                    this.el.audioDropdown.classList.remove('active');
                };
            });
        }

        if (this.el.fontDecrease) this.el.fontDecrease.onclick = () => this.changeFontSize(-1);
        if (this.el.fontIncrease) this.el.fontIncrease.onclick = () => this.changeFontSize(1);

        if (this.el.clearBtn) {
            this.el.clearBtn.onclick = () => {
                this.el.clearModal?.classList.add('active');
            };
        }

        const clearClose = this.el.clearModal?.querySelector('.modal-close');
        const clearCancel = this.el.clearModal?.querySelector('.btn-secondary');
        const clearConfirm = this.el.clearModal?.querySelector('.btn-primary');
        if (clearClose) clearClose.onclick = () => this.closeClearModal();
        if (clearCancel) clearCancel.onclick = () => this.closeClearModal();
        if (clearConfirm) clearConfirm.onclick = () => this.confirmClear();

        if (this.el.copyBtn) this.el.copyBtn.onclick = () => this.copyTranscripts();
        if (this.el.contextBtn) this.el.contextBtn.onclick = () => this.showContextModal();
        if (this.el.closeModal) this.el.closeModal.onclick = () => this.hideContextModal();
        if (this.el.clearContextBtn) this.el.clearContextBtn.onclick = () => this.clearContext();
        if (this.el.saveContextBtn) this.el.saveContextBtn.onclick = () => this.saveContext();

        [this.el.contextModal, this.el.clearModal].forEach(modal => {
            if (modal) {
                modal.onclick = (e) => {
                    if (e.target === modal) modal.classList.remove('active');
                };
            }
        });

        // AI Generate keywords from topic
        if (this.el.aiGenerateBtn) this.el.aiGenerateBtn.onclick = () => this.aiGenerateKeywords();

        // Summarize button
        if (this.el.summarizeBtn) {
            this.el.summarizeBtn.onclick = () => {
                if (this.onSummarize) this.onSummarize();
            };
        }

        // Summary modal controls
        const closeSummaryBtn = document.getElementById('closeSummaryBtn');
        const closeSummaryX = document.getElementById('closeSummaryModal');
        const copySummaryBtn = document.getElementById('copySummaryBtn');
        const closeSummary = () => this.el.summaryModal?.classList.remove('active');
        if (closeSummaryBtn) closeSummaryBtn.onclick = closeSummary;
        if (closeSummaryX) closeSummaryX.onclick = closeSummary;
        if (copySummaryBtn) {
            copySummaryBtn.onclick = async () => {
                const text = this.el.summaryContent?.innerText;
                if (text) {
                    try {
                        await navigator.clipboard.writeText(text);
                        this.showNotification('Summary copied!');
                    } catch (e) {
                        this.showNotification('Copy failed');
                    }
                }
            };
        }
        if (this.el.summaryModal) {
            this.el.summaryModal.onclick = (e) => {
                if (e.target === this.el.summaryModal) closeSummary();
            };
        }

        if (this.el.sidebarToggle) {
            this.el.sidebarToggle.onclick = () => this.toggleSidebar();
        }

        this.loadRecordingsSidebar();
    }

    setAudioSource(source) {
        this.currentSource = source;
        if (this.el.audioSourceText) {
            this.el.audioSourceText.textContent = source === 'computer' ? 'Computer Audio' : 'Microphone';
        }
    }

    getAudioSource() {
        return this.currentSource;
    }

    updateAudioMeter(rms) {
        const level = Math.min(10, Math.floor(rms * 80));
        const bars = this.el.audioMeter?.querySelectorAll('.meter-bar-h') || [];
        bars.forEach((bar, i) => bar.classList.toggle('active', i < level));
    }

    resetAudioMeter() {
        const bars = this.el.audioMeter?.querySelectorAll('.meter-bar-h') || [];
        bars.forEach(bar => bar.classList.remove('active'));
    }

    startTimer() {
        this.startTime = Date.now();
        this.timerInterval = setInterval(() => this.updateTimer(), 1000);
        this.updateTimer();
    }

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    updateTimer() {
        const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        if (this.el.timer) {
            this.el.timer.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }
    }

    resetTimer() {
        if (this.el.timer) this.el.timer.textContent = '00:00';
    }

    updateRecordButton(isRecording) {
        if (!this.el.recordBtn) return;
        if (isRecording) {
            this.el.recordBtn.classList.add('recording');
            this.el.recordBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>';
        } else {
            this.el.recordBtn.classList.remove('recording');
            this.el.recordBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"/><path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/></svg>';
        }
    }

    changeFontSize(delta) {
        this.fontSizeLevel = Math.max(-1, Math.min(2, this.fontSizeLevel + delta));
        if (!this.el.panelContent) return;
        this.el.panelContent.classList.remove('font-sm', 'font-lg', 'font-xl');
        if (this.fontSizeLevel === -1) this.el.panelContent.classList.add('font-sm');
        else if (this.fontSizeLevel === 1) this.el.panelContent.classList.add('font-lg');
        else if (this.fontSizeLevel === 2) this.el.panelContent.classList.add('font-xl');
    }

    addTranscriptSegment(data) {
        const { segment_id, source, target, is_final } = data;
        const id = segment_id || 0;

        if (!this.el.panelContent) return;

        const emptyState = this.el.panelContent.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        let seg = document.getElementById(`seg-${id}`);

        if (!seg) {
            seg = document.createElement('div');
            seg.id = `seg-${id}`;
            seg.className = 'transcript-segment';
            seg.innerHTML = `<div class="vi-text"></div><div class="en-text"></div>`;
            this.el.panelContent.appendChild(seg);
            this.displayedSegments.set(id, seg);
        }

        const viEl = seg.querySelector('.vi-text');
        const enEl = seg.querySelector('.en-text');

        if (source && viEl) {
            if (is_final) {
                viEl.innerHTML = source;
            } else {
                viEl.innerHTML = `<span style="opacity: 0.6; font-style: italic;">${source}</span>`;
            }
        }

        if (target && enEl) enEl.textContent = target;

        if (is_final) {
            seg.classList.remove('partial');
            seg.classList.add('final');
        } else {
            seg.classList.add('partial');
            seg.classList.remove('final');
        }

        this.el.panelContent.scrollTop = this.el.panelContent.scrollHeight;
    }

    clearTranscripts() {
        if (this.el.panelContent) {
            this.el.panelContent.innerHTML = '<div class="empty-state"><p>Click record to start</p></div>';
        }
        this.displayedSegments.clear();
        this.closeClearModal();
    }

    async copyTranscripts() {
        const segs = Array.from(this.el.panelContent?.querySelectorAll('.transcript-segment') || []);
        const lines = segs.map(seg => {
            const vi = seg.querySelector('.vi-text')?.textContent || '';
            const en = seg.querySelector('.en-text')?.textContent || '';
            return en ? `${vi}\n> ${en}` : vi;
        }).filter(l => l.trim());

        if (lines.length === 0) {
            this.showNotification('Nothing to copy');
            return;
        }

        try {
            await navigator.clipboard.writeText(lines.join('\n\n'));
            this.showNotification('Copied!');
        } catch (e) {
            this.showNotification('Copy failed');
        }
    }

    showNotification(msg) {
        if (!this.el.notification) return;
        this.el.notification.textContent = msg;
        this.el.notification.classList.add('active');
        setTimeout(() => this.el.notification.classList.remove('active'), 2500);
    }

    closeClearModal() {
        this.el.clearModal?.classList.remove('active');
    }

    confirmClear() {
        this.clearTranscripts();
        this.showNotification('Cleared');
    }

    loadRecordingsSidebar() {
        if (!this.el.recordingsList) return;
        try {
            const recordings = JSON.parse(localStorage.getItem('recordings') || '[]');
            if (recordings.length === 0) {
                this.el.recordingsList.innerHTML = '<div class="empty-state"><p>No recordings</p></div>';
                return;
            }

            this.el.recordingsList.innerHTML = recordings.slice(0, 5).map(rec => {
                const name = rec.customName || `${rec.date} ${rec.time}`;
                const count = rec.transcript?.length || 0;
                const starred = rec.starred ? '⭐ ' : '';
                return `
                    <div class="recording-card" data-id="${rec.id}">
                        <div class="recording-info">
                            <div class="recording-date">${starred}${name}</div>
                            <div class="recording-duration">${rec.duration || '00:00'} • ${count} segs</div>
                        </div>
                        <div class="recording-card-actions">
                            <button class="btn-view-small" data-action="view" data-id="${rec.id}">👁</button>
                            <button class="btn-delete-small" data-action="delete" data-id="${rec.id}">×</button>
                        </div>
                    </div>
                `;
            }).join('');

            this.el.recordingsList.querySelectorAll('[data-action]').forEach(btn => {
                btn.onclick = (e) => {
                    e.stopPropagation();
                    const { action, id } = btn.dataset;
                    if (action === 'view') this.viewRecording(id);
                    else if (action === 'delete') this.deleteRecording(id);
                };
            });
        } catch (e) { }
    }

    viewRecording(id) {
        localStorage.setItem('selectedRecordingId', id);
        window.location.href = 'recordings.html';
    }

    deleteRecording(id) {
        this.pendingDeleteId = id;
        this.showDeleteModal();
    }

    showDeleteModal() {
        if (!this.el.deleteRecordingModal) return;
        this.el.deleteRecordingModal.classList.add('active');

        const close = document.getElementById('deleteModalClose');
        const cancel = document.getElementById('deleteModalCancel');
        const confirm = document.getElementById('deleteModalConfirm');

        if (close) close.onclick = () => this.hideDeleteModal();
        if (cancel) cancel.onclick = () => this.hideDeleteModal();
        if (confirm) confirm.onclick = () => this.confirmDeleteRecording();

        this.el.deleteRecordingModal.onclick = (e) => {
            if (e.target === this.el.deleteRecordingModal) this.hideDeleteModal();
        };
    }

    hideDeleteModal() {
        this.el.deleteRecordingModal?.classList.remove('active');
        this.pendingDeleteId = null;
    }

    confirmDeleteRecording() {
        if (!this.pendingDeleteId) return;
        try {
            let recordings = JSON.parse(localStorage.getItem('recordings') || '[]');
            recordings = recordings.filter(r => String(r.id) !== String(this.pendingDeleteId));
            localStorage.setItem('recordings', JSON.stringify(recordings));
            this.loadRecordingsSidebar();
            this.showNotification('Deleted');
        } catch (e) { }
        this.hideDeleteModal();
    }

    toggleSidebar() {
        this.el.sidebar?.classList.toggle('active');
        this.loadRecordingsSidebar();
    }

    showContextModal() {
        this.el.contextModal?.classList.add('active');
    }

    hideContextModal() {
        this.el.contextModal?.classList.remove('active');
    }

    clearContext() {
        if (this.el.keywords) this.el.keywords.value = '';
        if (this.el.context) this.el.context.value = '';
        if (this.el.lectureTopic) this.el.lectureTopic.value = '';
    }

    saveContext() {
        const keywords = (this.el.keywords?.value || '').split(',').map(k => k.trim()).filter(k => k);
        const context = (this.el.context?.value || '').trim();
        const topic = this.getLectureTopic();
        if (this.onContextSave) this.onContextSave({ keywords, context, topic });
        this.hideContextModal();
        this.showNotification('Saved');
    }

    getLectureTopic() {
        return (this.el.lectureTopic?.value || '').trim();
    }

    async aiGenerateKeywords() {
        const topic = this.getLectureTopic();
        if (!topic) {
            this.showNotification('Enter a topic first');
            return;
        }

        const btn = this.el.aiGenerateBtn;
        const original = btn?.innerHTML;
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '⏳ Generating...';
        }

        try {
            const resp = await fetch('/api/expand-keywords', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic })
            });

            if (resp.ok) {
                const data = await resp.json();
                if (data.keywords && this.el.keywords) {
                    this.el.keywords.value = data.keywords;
                    this.showNotification('Keywords generated!');
                }
            } else {
                this.showNotification('Could not generate keywords');
            }
        } catch (e) {
            this.showNotification('Generation failed');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = original;
            }
        }
    }

    showSummary(data) {
        const { summary, topic } = data;
        if (!summary || !this.el.summaryModal) return;

        let html = summary
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^### (.+)$/gm, '<h4>$1</h4>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/^# (.+)$/gm, '<h2>$1</h2>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/\n/g, '<br>');

        if (this.el.summaryContent) {
            this.el.summaryContent.innerHTML = html;
        }
        this.el.summaryModal.classList.add('active');
        this.showNotification('Summary ready!');
    }
}

export { UIManager };