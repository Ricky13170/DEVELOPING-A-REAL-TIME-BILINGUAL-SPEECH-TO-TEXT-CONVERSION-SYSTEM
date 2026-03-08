import { getLanguage, getSourceLanguages, getTargetLanguages, saveLanguagePreference, loadLanguagePreference } from './languages.js';

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
            aiContextBtn: document.getElementById('aiContextBtn'),
            // New elements
            screenShareBtn: document.getElementById('screenShareBtn'),
            screenPanel: document.getElementById('screenPanel'),
            screenPreview: document.getElementById('screenPreview'),
            screenVideoWrap: document.getElementById('screenVideoWrap'),
            stopScreenBtn: document.getElementById('stopScreenBtn'),
            // Language selectors
            srcLangBtn: document.getElementById('srcLangBtn'),
            srcLangFlag: document.getElementById('srcLangFlag'),
            srcLangName: document.getElementById('srcLangName'),
            srcLangMenu: document.getElementById('srcLangMenu'),
            srcLangDropdown: document.getElementById('srcLangDropdown'),
            tgtLangBtn: document.getElementById('tgtLangBtn'),
            tgtLangFlag: document.getElementById('tgtLangFlag'),
            tgtLangName: document.getElementById('tgtLangName'),
            tgtLangMenu: document.getElementById('tgtLangMenu'),
            tgtLangDropdown: document.getElementById('tgtLangDropdown'),
            swapLangBtn: document.getElementById('swapLangBtn'),
            displayModeBtn: document.getElementById('displayModeBtn'),
        };

        this.timerInterval = null;
        this.startTime = null;
        this.currentSource = 'microphone';
        this.fontSizeLevel = 0;
        this.pendingDeleteId = null;
        this.onContextSave = null;
        this.onScreenShareToggle = null;
        this.onLangChange = null;
        this.displayedSegments = new Map();

        // Display mode: 'mixed' (original + translation together) or 'split' (side by side)
        this.displayMode = localStorage.getItem('asr_displayMode') || 'mixed';

        // Language state
        const pref = loadLanguagePreference();
        this.srcLang = pref.srcCode;
        this.tgtLang = pref.tgtCode;

        this.setupEventHandlers();
        this.initLanguageSelectors();
    }

    /* ═══════════ LANGUAGE SELECTORS ═══════════ */

    initLanguageSelectors() {
        this._updateLangButton('src');
        this._updateLangButton('tgt');
        this._populateLangMenu('src');
        this._populateLangMenu('tgt');

        // Source language button
        if (this.el.srcLangBtn) {
            this.el.srcLangBtn.onclick = (e) => {
                e.stopPropagation();
                this._toggleLangMenu('src');
            };
        }

        // Target language button
        if (this.el.tgtLangBtn) {
            this.el.tgtLangBtn.onclick = (e) => {
                e.stopPropagation();
                this._toggleLangMenu('tgt');
            };
        }

        // Swap button
        if (this.el.swapLangBtn) {
            this.el.swapLangBtn.onclick = () => {
                // Don't swap if source is 'auto'
                if (this.srcLang === 'auto') {
                    this.showNotification('Cannot swap when source is Auto Detect');
                    return;
                }
                const tmp = this.srcLang;
                this.srcLang = this.tgtLang;
                this.tgtLang = tmp;
                this._updateLangButton('src');
                this._updateLangButton('tgt');
                this._populateLangMenu('src');
                this._populateLangMenu('tgt');
                saveLanguagePreference(this.srcLang, this.tgtLang);

                // Notify app of language change
                if (this.onLangChange) {
                    this.onLangChange(this.getSelectedLanguages());
                }
            };
        }

        // Close menus on outside click
        document.addEventListener('click', () => {
            this.el.srcLangDropdown?.classList.remove('active');
            this.el.srcLangMenu?.classList.remove('active');
            this.el.tgtLangDropdown?.classList.remove('active');
            this.el.tgtLangMenu?.classList.remove('active');
        });
    }

    _toggleLangMenu(type) {
        const dropdown = type === 'src' ? this.el.srcLangDropdown : this.el.tgtLangDropdown;
        const menu = type === 'src' ? this.el.srcLangMenu : this.el.tgtLangMenu;
        const otherDropdown = type === 'src' ? this.el.tgtLangDropdown : this.el.srcLangDropdown;
        const otherMenu = type === 'src' ? this.el.tgtLangMenu : this.el.srcLangMenu;

        // Close other
        otherDropdown?.classList.remove('active');
        otherMenu?.classList.remove('active');

        // Toggle this
        dropdown?.classList.toggle('active');
        menu?.classList.toggle('active');
    }

    _updateLangButton(type) {
        const code = type === 'src' ? this.srcLang : this.tgtLang;
        const lang = getLanguage(code);
        if (!lang) return;

        if (type === 'src') {
            if (this.el.srcLangFlag) this.el.srcLangFlag.textContent = lang.flag;
            if (this.el.srcLangName) this.el.srcLangName.textContent = lang.name;
        } else {
            if (this.el.tgtLangFlag) this.el.tgtLangFlag.textContent = lang.flag;
            if (this.el.tgtLangName) this.el.tgtLangName.textContent = lang.name;
        }
    }

    _populateLangMenu(type) {
        const menu = type === 'src' ? this.el.srcLangMenu : this.el.tgtLangMenu;
        if (!menu) return;

        const langs = type === 'src' ? getSourceLanguages() : getTargetLanguages(this.srcLang);
        const currentCode = type === 'src' ? this.srcLang : this.tgtLang;

        menu.innerHTML = langs.map(lang => `
            <div class="dropdown-item ${lang.code === currentCode ? 'active' : ''}" data-code="${lang.code}">
                <span class="item-flag">${lang.flag}</span>
                <span class="item-name">${lang.name}</span>
                <span class="item-native">${lang.nameNative}</span>
            </div>
        `).join('');

        menu.querySelectorAll('.dropdown-item').forEach(item => {
            item.onclick = (e) => {
                e.stopPropagation();
                const code = item.dataset.code;
                if (type === 'src') {
                    this.srcLang = code;
                    // If source === target, change target
                    if (this.srcLang === this.tgtLang && this.srcLang !== 'auto') {
                        this.tgtLang = this.srcLang === 'en' ? 'vi' : 'en';
                        this._updateLangButton('tgt');
                        this._populateLangMenu('tgt');
                    }
                } else {
                    this.tgtLang = code;
                }
                this._updateLangButton(type);
                this._populateLangMenu(type);
                saveLanguagePreference(this.srcLang, this.tgtLang);

                // Notify app of language change (for mid-session switching)
                if (this.onLangChange) {
                    this.onLangChange(this.getSelectedLanguages());
                }

                // Close menu
                const dropdown = type === 'src' ? this.el.srcLangDropdown : this.el.tgtLangDropdown;
                dropdown?.classList.remove('active');
                menu.classList.remove('active');
            };
        });
    }

    getSelectedLanguages() {
        const src = getLanguage(this.srcLang);
        const tgt = getLanguage(this.tgtLang);
        return {
            srcCode: this.srcLang,
            tgtCode: this.tgtLang,
            srcWhisper: src?.whisper || null,
            srcNllb: src?.nllb || null,
            tgtNllb: tgt?.nllb || null,
        };
    }

    /* ═══════════ EVENT HANDLERS ═══════════ */

    setupEventHandlers() {
        // Audio source dropdown
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

        // Font size
        if (this.el.fontDecrease) this.el.fontDecrease.onclick = () => this.changeFontSize(-1);
        if (this.el.fontIncrease) this.el.fontIncrease.onclick = () => this.changeFontSize(1);

        // Display mode toggle (mixed ↔ split)
        if (this.el.displayModeBtn) {
            this._updateDisplayModeBtn();
            this.el.displayModeBtn.onclick = () => {
                this.displayMode = this.displayMode === 'mixed' ? 'split' : 'mixed';
                localStorage.setItem('asr_displayMode', this.displayMode);
                this._updateDisplayModeBtn();
                this._clearDisplayedSegments();
                this.showNotification(this.displayMode === 'split' ? 'Split mode' : 'Mixed mode');
            };
        }

        // Clear
        if (this.el.clearBtn) {
            this.el.clearBtn.onclick = () => {
                this.el.clearModal?.classList.add('active');
            };
        }

        const clearClose = this.el.clearModal?.querySelector('.modal-close');
        const clearCancel = this.el.clearModal?.querySelector('.btn-ghost');
        const clearConfirm = this.el.clearModal?.querySelector('.btn-danger');
        if (clearClose) clearClose.onclick = () => this.closeClearModal();
        if (clearCancel) clearCancel.onclick = () => this.closeClearModal();
        if (clearConfirm) clearConfirm.onclick = () => this.confirmClear();

        // Context modal
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

        // AI Generate context (keywords + description paragraph)
        if (this.el.aiContextBtn) this.el.aiContextBtn.onclick = () => this.aiGenerateContext();

        // Sidebar toggle
        if (this.el.sidebarToggle) {
            this.el.sidebarToggle.onclick = () => this.toggleSidebar();
        }

        // Screen share
        if (this.el.screenShareBtn) {
            this.el.screenShareBtn.onclick = () => {
                if (this.onScreenShareToggle) this.onScreenShareToggle();
            };
        }

        if (this.el.stopScreenBtn) {
            this.el.stopScreenBtn.onclick = () => {
                if (this.onScreenShareToggle) this.onScreenShareToggle();
            };
        }

        this.loadRecordingsSidebar();
        this.setupPanelResizer();
    }

    /* ═══════════ PANEL RESIZER ═══════════ */

    setupPanelResizer() {
        const resizer = document.getElementById('panelResizer');
        const screenPanel = this.el.screenPanel;
        if (!resizer || !screenPanel) return;

        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        const onStart = (e) => {
            if (screenPanel.classList.contains('hidden')) return;
            isResizing = true;
            startX = e.clientX || e.touches?.[0]?.clientX || 0;
            startWidth = screenPanel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        };

        const onMove = (e) => {
            if (!isResizing) return;
            const clientX = e.clientX || e.touches?.[0]?.clientX || 0;
            const dx = clientX - startX;
            const container = document.querySelector('.content');
            const containerWidth = container?.offsetWidth || 0;
            const newWidth = Math.max(200, Math.min(containerWidth * 0.8, startWidth + dx));
            screenPanel.style.flex = 'none';
            screenPanel.style.width = `${newWidth}px`;
        };

        const onEnd = () => {
            if (!isResizing) return;
            isResizing = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };

        resizer.addEventListener('mousedown', onStart);
        resizer.addEventListener('touchstart', onStart, { passive: false });
        document.addEventListener('mousemove', onMove);
        document.addEventListener('touchmove', onMove, { passive: false });
        document.addEventListener('mouseup', onEnd);
        document.addEventListener('touchend', onEnd);
    }

    /* ═══════════ SCREEN SHARE ═══════════ */

    showScreenPanel(stream) {
        if (this.el.screenPanel) {
            this.el.screenPanel.classList.remove('hidden');
        }
        if (this.el.screenPreview && stream) {
            this.el.screenPreview.srcObject = stream;
        }
        if (this.el.screenShareBtn) {
            this.el.screenShareBtn.classList.add('active');
        }
    }

    hideScreenPanel() {
        if (this.el.screenPanel) {
            this.el.screenPanel.classList.add('hidden');
            this.el.screenPanel.style.width = '';
            this.el.screenPanel.style.flex = '';
        }
        if (this.el.screenPreview) {
            this.el.screenPreview.srcObject = null;
        }
        if (this.el.screenShareBtn) {
            this.el.screenShareBtn.classList.remove('active');
        }
    }

    /* ═══════════ AUDIO SOURCE ═══════════ */

    setAudioSource(source) {
        this.currentSource = source;
        if (this.el.audioSourceText) {
            if (source === 'computer') {
                this.el.audioSourceText.textContent = 'System';
            } else if (source === 'screen') {
                this.el.audioSourceText.textContent = 'Screen';
            } else {
                this.el.audioSourceText.textContent = 'Mic';
            }
        }
    }

    getAudioSource() {
        return this.currentSource;
    }

    /* ═══════════ AUDIO METER ═══════════ */

    updateAudioMeter(rms) {
        const level = Math.min(8, Math.floor(rms * 70));
        const bars = this.el.audioMeter?.querySelectorAll('.meter-bar-h') || [];
        bars.forEach((bar, i) => bar.classList.toggle('active', i < level));
    }

    resetAudioMeter() {
        const bars = this.el.audioMeter?.querySelectorAll('.meter-bar-h') || [];
        bars.forEach(bar => bar.classList.remove('active'));
    }

    /* ═══════════ TIMER ═══════════ */

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

    /* ═══════════ RECORD BUTTON ═══════════ */

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

    /* ═══════════ FONT SIZE ═══════════ */

    changeFontSize(delta) {
        this.fontSizeLevel = Math.max(-1, Math.min(2, this.fontSizeLevel + delta));
        if (!this.el.panelContent) return;
        this.el.panelContent.classList.remove('font-sm', 'font-lg', 'font-xl');
        if (this.fontSizeLevel === -1) this.el.panelContent.classList.add('font-sm');
        else if (this.fontSizeLevel === 1) this.el.panelContent.classList.add('font-lg');
        else if (this.fontSizeLevel === 2) this.el.panelContent.classList.add('font-xl');
    }

    /* ═══════════ DISPLAY MODE ═══════════ */

    _updateDisplayModeBtn() {
        if (!this.el.displayModeBtn) return;
        if (this.displayMode === 'split') {
            // Columns icon
            this.el.displayModeBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="18" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1"/></svg>`;
            this.el.displayModeBtn.title = 'Mode: Split (click for Mixed)';
            this.el.displayModeBtn.classList.add('active');
        } else {
            // Lines icon
            this.el.displayModeBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="15" y2="18"/></svg>`;
            this.el.displayModeBtn.title = 'Mode: Mixed (click for Split)';
            this.el.displayModeBtn.classList.remove('active');
        }
    }

    /* ═══════════ TRANSCRIPTS ═══════════ */

    addTranscriptSegment(data) {
        if (this.displayMode === 'split') {
            this._addTranscriptSplit(data);
        } else {
            this._addTranscriptMixed(data);
        }
    }

    _addTranscriptMixed(data) {
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
            seg.innerHTML = `<div class="src-text"></div><div class="tgt-text" style="display:none"></div>`;
            this.el.panelContent.appendChild(seg);
            this.displayedSegments.set(id, seg);
        }

        const srcEl = seg.querySelector('.src-text');
        const tgtEl = seg.querySelector('.tgt-text');

        if (source && srcEl) {
            if (is_final) {
                srcEl.innerHTML = source;
            } else {
                srcEl.innerHTML = `<span style="opacity: 0.6; font-style: italic;">${source}</span>`;
            }
        }

        if (target && tgtEl) {
            tgtEl.textContent = target;
            tgtEl.style.display = '';
        }

        if (is_final) {
            seg.classList.remove('partial');
            seg.classList.add('final');
        } else {
            seg.classList.add('partial');
            seg.classList.remove('final');
        }

        this.el.panelContent.scrollTop = this.el.panelContent.scrollHeight;
    }

    _addTranscriptSplit(data) {
        const { segment_id, source, target, is_final } = data;
        const id = segment_id || 0;

        if (!this.el.panelContent) return;

        const emptyState = this.el.panelContent.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        let row = document.getElementById(`split-${id}`);

        if (!row) {
            row = document.createElement('div');
            row.id = `split-${id}`;
            row.className = 'split-row';
            row.innerHTML = `<div class="split-source"></div><div class="split-target"></div>`;
            this.el.panelContent.appendChild(row);
        }

        const srcEl = row.querySelector('.split-source');
        const tgtEl = row.querySelector('.split-target');

        if (source && srcEl) {
            if (is_final) {
                srcEl.innerHTML = source;
            } else {
                srcEl.innerHTML = `<span style="opacity: 0.6; font-style: italic;">${source}</span>`;
            }
        }

        if (target && tgtEl) {
            tgtEl.textContent = target;
        }

        if (is_final) {
            row.classList.remove('partial');
            row.classList.add('final');
        } else {
            row.classList.add('partial');
            row.classList.remove('final');
        }

        this.el.panelContent.scrollTop = this.el.panelContent.scrollHeight;
    }

    clearTranscripts() {
        if (this.el.panelContent) {
            this.el.panelContent.innerHTML = '<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg></div><p>Click record to start</p></div>';
        }
        this.displayedSegments.clear();
        this.closeClearModal();
    }

    _clearDisplayedSegments() {
        if (!this.el.panelContent) return;
        this.el.panelContent.querySelectorAll('.transcript-segment, .split-row').forEach(el => el.remove());
        this.displayedSegments.clear();
    }

    /* ═══════════ NOTIFICATIONS ═══════════ */

    showNotification(msg) {
        if (!this.el.notification) return;
        this.el.notification.textContent = msg;
        this.el.notification.classList.add('active');
        setTimeout(() => this.el.notification.classList.remove('active'), 2500);
    }

    /* ═══════════ MODALS ═══════════ */

    closeClearModal() {
        this.el.clearModal?.classList.remove('active');
    }

    confirmClear() {
        this.clearTranscripts();
        this.showNotification('Cleared');
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
        const keywords = (this.el.keywords?.value || '').trim();
        const context = (this.el.context?.value || '').trim();
        const topic = this.getLectureTopic();
        if (this.onContextSave) this.onContextSave({ keywords, context, topic });
        this.hideContextModal();
        this.showNotification('Saved');
    }

    getLectureTopic() {
        return (this.el.lectureTopic?.value || '').trim();
    }

    async aiGenerateContext() {
        const topic = this.getLectureTopic();
        if (!topic) {
            this.showNotification('Enter a topic first');
            return;
        }

        const btn = this.el.aiContextBtn;
        const original = btn?.innerHTML;
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '⏳ Generating...';
        }

        try {
            const resp = await fetch('/api/generate-context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ topic })
            });

            if (resp.ok) {
                const data = await resp.json();
                if (data.keywords && this.el.keywords) {
                    this.el.keywords.value = data.keywords;
                }
                if (data.context && this.el.context) {
                    this.el.context.value = data.context;
                }
                this.showNotification('Context generated!');
            } else {
                this.showNotification('Could not generate context');
            }
        } catch (e) {
            this.showNotification('Context generation failed');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = original;
            }
        }
    }

    /* ═══════════ SIDEBAR ═══════════ */

    toggleSidebar() {
        this.el.sidebar?.classList.toggle('active');
        this.loadRecordingsSidebar();
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
}

export { UIManager };