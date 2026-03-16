import { getLanguage, getTargetLanguages, saveLanguagePreference, loadLanguagePreference } from './languages.js';
import { SubtitleOverlay } from './subtitle.js';

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
            screenLayoutBtn: document.getElementById('screenLayoutBtn'),
            // Language selectors
            tgtLangBtn: document.getElementById('tgtLangBtn'),
            tgtLangFlag: document.getElementById('tgtLangFlag'),
            tgtLangName: document.getElementById('tgtLangName'),
            tgtLangMenu: document.getElementById('tgtLangMenu'),
            tgtLangDropdown: document.getElementById('tgtLangDropdown'),
            displayModeBtn: document.getElementById('displayModeBtn'),
            // Demo & settings

            settingsBtn: document.getElementById('settingsBtn'),
            loginBtn: document.getElementById('loginBtn'),
            settingsModal: document.getElementById('settingsModal'),
            settingsClose: document.getElementById('settingsClose'),
            settingsSave: document.getElementById('settingsSave'),
            loginModal: document.getElementById('loginModal'),
            loginClose: document.getElementById('loginClose'),
            templateChips: document.getElementById('templateChips'),
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
        this.segmentDataCache = new Map(); 

        // Display mode: 'mixed' (original + translation together) or 'split' (side by side)
        this.displayMode = localStorage.getItem('asr_displayMode') || 'mixed';

        // Language state — source is always 'auto'
        this.srcLang = 'auto';
        this.tgtLang = loadLanguagePreference().tgtCode;

        this.setupEventHandlers();
        this.initLanguageSelectors();

        // Show sidebar on start (desktop)
        if (window.innerWidth > 1024 && this.el.sidebar) {
            this.el.sidebar.classList.add('active');
        }

        // Initialize Subtitle overlay inside screen panel
        if (this.el.screenVideoWrap) {
            this.subtitleOverlay = new SubtitleOverlay(this.el.screenVideoWrap);
        }

        if (this.el.screenPreview) {
            this.el.screenPreview.playsInline = true;
        }
    }

    /* ═══════════ LANGUAGE SELECTORS ═══════════ */

    initLanguageSelectors() {
        this._updateLangButton();
        this._populateLangMenu('tgt');

        // Target language button
        if (this.el.tgtLangBtn) {
            this.el.tgtLangBtn.onclick = (e) => {
                e.stopPropagation();
                this.el.tgtLangDropdown?.classList.toggle('active');
                this.el.tgtLangMenu?.classList.toggle('active');
            };
        }

        // Close menus on outside click
        document.addEventListener('click', () => {
            this.el.tgtLangDropdown?.classList.remove('active');
            this.el.tgtLangMenu?.classList.remove('active');
        });
    }

    _updateLangButton() {
        const lang = getLanguage(this.tgtLang);
        if (!lang) return;
        if (this.el.tgtLangFlag) this.el.tgtLangFlag.textContent = lang.flag;
        if (this.el.tgtLangName) this.el.tgtLangName.textContent = lang.name;
    }

    _populateLangMenu() {
        const menu = this.el.tgtLangMenu;
        if (!menu) return;

        const langs = getTargetLanguages(this.srcLang);

        menu.innerHTML = langs.map(lang => `
            <div class="dropdown-item ${lang.code === this.tgtLang ? 'active' : ''}" data-code="${lang.code}">
                <span class="item-flag">${lang.flag}</span>
                <span class="item-name">${lang.name}</span>
            </div>
        `).join('');

        menu.querySelectorAll('.dropdown-item').forEach(item => {
            item.onclick = (e) => {
                e.stopPropagation();
                this.tgtLang = item.dataset.code;
                this._updateLangButton();
                this._populateLangMenu();
                saveLanguagePreference(this.srcLang, this.tgtLang);

                if (this.onLangChange) {
                    this.onLangChange(this.getSelectedLanguages());
                }

                this.el.tgtLangDropdown?.classList.remove('active');
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

        // Picture-in-Picture
        const pipBtn = document.getElementById('pipBtn');
        if (pipBtn) {
            pipBtn.onclick = () => this.togglePiP();
        }

        // Screen layout toggle
        if (this.el.screenLayoutBtn) {
            this.el.screenLayoutBtn.onclick = () => this.toggleScreenLayout();
        }

        this.loadRecordingsSidebar();
        this.setupPanelResizer();

        // Template chips
        if (this.el.templateChips) {
            this.el.templateChips.onclick = (e) => {
                const chip = e.target.closest('[data-template]');
                if (chip) this.applyTemplate(chip.dataset.template);
            };
        }

        // Settings modal
        if (this.el.settingsBtn) {
            this.el.settingsBtn.onclick = () => this.el.settingsModal?.classList.add('active');
        }
        if (this.el.settingsClose) {
            this.el.settingsClose.onclick = () => this.el.settingsModal?.classList.remove('active');
        }
        if (this.el.settingsSave) {
            this.el.settingsSave.onclick = () => {
                this.saveSettings();
                this.el.settingsModal?.classList.remove('active');
                this.showNotification('Settings saved');
            };
        }

        // Login modal
        if (this.el.loginBtn) {
            this.el.loginBtn.onclick = () => this.el.loginModal?.classList.add('active');
        }
        if (this.el.loginClose) {
            this.el.loginClose.onclick = () => this.el.loginModal?.classList.remove('active');
        }
        const googleBtn = document.getElementById('googleSignIn');
        if (googleBtn) {
            googleBtn.onclick = () => this.showNotification('Google login coming soon');
        }

        // Close new modals on overlay click
        [this.el.settingsModal, this.el.loginModal].forEach(modal => {
            if (modal) {
                modal.onclick = (e) => {
                    if (e.target === modal) modal.classList.remove('active');
                };
            }
        });

        this.loadSettings();
    }

    /* ═══════════ PANEL RESIZER ═══════════ */

    setupPanelResizer() {
        const resizer = document.getElementById('panelResizer');
        const screenPanel = this.el.screenPanel;
        if (!resizer || !screenPanel) return;

        let isResizing = false;
        let startPos = 0;
        let startSize = 0;

        const isVertical = () => this._screenLayout === 'vertical';

        const onStart = (e) => {
            if (screenPanel.classList.contains('hidden')) return;
            isResizing = true;
            const clientX = e.clientX || e.touches?.[0]?.clientX || 0;
            const clientY = e.clientY || e.touches?.[0]?.clientY || 0;
            startPos = isVertical() ? clientX : clientY;
            startSize = isVertical() ? screenPanel.offsetWidth : screenPanel.offsetHeight;
            document.body.style.cursor = isVertical() ? 'col-resize' : 'row-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        };

        const onMove = (e) => {
            if (!isResizing) return;
            const clientX = e.clientX || e.touches?.[0]?.clientX || 0;
            const clientY = e.clientY || e.touches?.[0]?.clientY || 0;
            const container = document.querySelector('.content');
            if (!container) return;

            if (isVertical()) {
                const dx = clientX - startPos;
                const maxW = container.offsetWidth * 0.8;
                const newWidth = Math.max(200, Math.min(maxW, startSize + dx));
                screenPanel.style.flex = 'none';
                screenPanel.style.width = `${newWidth}px`;
                screenPanel.style.height = '';
            } else {
                const dy = clientY - startPos;
                const maxH = container.offsetHeight * 0.8;
                const newHeight = Math.max(120, Math.min(maxH, startSize + dy));
                screenPanel.style.flex = 'none';
                screenPanel.style.height = `${newHeight}px`;
                screenPanel.style.width = '';
            }
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
        // Apply saved layout preference (horizontal or vertical)
        const content = document.querySelector('.content');
        this._screenLayout = localStorage.getItem('asr_screenLayout') || 'horizontal';
        if (content) {
            content.classList.add('screen-' + this._screenLayout);
        }
        this._updateScreenLayoutIcon();

        if (this.el.screenPreview && stream) {
            this.el.screenPreview.srcObject = stream;
        }
        if (this.el.screenShareBtn) {
            this.el.screenShareBtn.classList.add('active');
        }
        // Auto-switch to split mode for 2-column transcript
        this._preScreenDisplayMode = this.displayMode;
        if (this.displayMode !== 'split') {
            this.displayMode = 'split';
            localStorage.setItem('asr_displayMode', this.displayMode);
            this._updateDisplayModeBtn();
            this._clearDisplayedSegments();
        }
    }

    hideScreenPanel() {
        if (this.el.screenPanel) {
            this.el.screenPanel.classList.add('hidden');
            this.el.screenPanel.style.width = '';
            this.el.screenPanel.style.flex = '';
        }
        const content = document.querySelector('.content');
        if (content) {
            content.classList.remove('screen-horizontal', 'screen-vertical');
        }

        if (this.el.screenPreview) {
            // Exit PiP if active
            if (document.pictureInPictureElement === this.el.screenPreview) {
                document.exitPictureInPicture().catch(() => {});
            }
            this.el.screenPreview.srcObject = null;
        }
        if (this.el.screenShareBtn) {
            this.el.screenShareBtn.classList.remove('active');
        }
        // Restore previous display mode
        if (this._preScreenDisplayMode && this._preScreenDisplayMode !== this.displayMode) {
            this.displayMode = this._preScreenDisplayMode;
            localStorage.setItem('asr_displayMode', this.displayMode);
            this._updateDisplayModeBtn();
            this._clearDisplayedSegments();
        }
        this._preScreenDisplayMode = null;
    }

    togglePiP() {
        const video = this.el.screenPreview;
        if (!video) return;
        if (document.pictureInPictureElement === video) {
            document.exitPictureInPicture().catch(() => {});
        } else {
            video.requestPictureInPicture().catch((err) => {
                this.showNotification('PiP not supported');
            });
        }
    }

    toggleScreenLayout() {
        const content = document.querySelector('.content');
        if (!content) return;
        const current = this._screenLayout || 'horizontal';
        const next = current === 'horizontal' ? 'vertical' : 'horizontal';
        content.classList.remove('screen-' + current);
        content.classList.add('screen-' + next);
        this._screenLayout = next;
        localStorage.setItem('asr_screenLayout', next);
        this._updateScreenLayoutIcon();
        // Reset inline size when switching layout
        if (this.el.screenPanel) {
            this.el.screenPanel.style.width = '';
            this.el.screenPanel.style.height = '';
            this.el.screenPanel.style.flex = '';
        }
    }

    _updateScreenLayoutIcon() {
        const btn = this.el.screenLayoutBtn;
        if (!btn) return;
        const isVertical = this._screenLayout === 'vertical';
        // Vertical split icon (line down middle) vs horizontal split icon (line across middle)
        btn.innerHTML = isVertical
            ? '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="2" y1="12" x2="22" y2="12"/></svg>'
            : '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="18" rx="2"/><line x1="12" y1="3" x2="12" y2="21"/></svg>';
        btn.title = isVertical ? 'Switch to horizontal layout' : 'Switch to vertical layout';
    }

    /* ═══════════ AUDIO SOURCE ═══════════ */

    setAudioSource(source) {
        this.currentSource = source;
        if (this.el.audioSourceText) {
            if (source === 'computer') {
                this.el.audioSourceText.textContent = 'System Audio';
            } else if (source === 'mixed') {
                this.el.audioSourceText.textContent = 'Mixed Audio';
            } else if (source === 'screen') {
                this.el.audioSourceText.textContent = 'Screen';
            } else {
                this.el.audioSourceText.textContent = 'Microphone';
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
            // Horizontal split icon (top/bottom)
            this.el.displayModeBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="7" rx="1"/><rect x="3" y="14" width="18" height="7" rx="1"/></svg>`;
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
        // Cache the segment data for mode switching
        const id = data.segment_id || 0;
        this.segmentDataCache.set(id, { ...data });

        if (this.displayMode === 'split') {
            this._addTranscriptSplit(data);
        } else {
            this._addTranscriptMixed(data);
        }

        // Highlight refined translations (second-pass)
        if (data.refined && data.target) {
            const enSpan = document.getElementById(`en-seg-${id}`)
                || this.el.panelContent?.querySelector(`.split-pane-target [data-seg="${id}"]`);
            if (enSpan) {
                enSpan.classList.remove('refined');
                // Force reflow to restart animation
                void enSpan.offsetWidth;
                enSpan.classList.add('refined');
            }
        }

        // Update subtitles on video overlay
        if (this.subtitleOverlay) {
            this.subtitleOverlay.update(data.source, data.target, data.is_final);
        }
    }

    _ensureContinuousContainers() {
        if (!this.el.panelContent) return;

        const emptyState = this.el.panelContent.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        if (!this.el.panelContent.querySelector('#viContainer')) {
            const viLabel = document.createElement('div');
            viLabel.className = 'container-label';
            viLabel.textContent = 'Vietnamese';
            this.el.panelContent.appendChild(viLabel);

            const viC = document.createElement('div');
            viC.id = 'viContainer';
            viC.className = 'continuous-text vi-container';
            this.el.panelContent.appendChild(viC);

            const enLabel = document.createElement('div');
            enLabel.className = 'container-label';
            enLabel.textContent = 'English';
            this.el.panelContent.appendChild(enLabel);

            const enC = document.createElement('div');
            enC.id = 'enContainer';
            enC.className = 'continuous-text en-container';
            this.el.panelContent.appendChild(enC);
        }
    }

    _addTranscriptMixed(data) {
        const { segment_id, source, target, is_final } = data;
        const id = segment_id || 0;

        if (!this.el.panelContent) return;

        this._ensureContinuousContainers();

        const viC = document.getElementById('viContainer');
        const enC = document.getElementById('enContainer');

        // Helper to update spans with smooth continuous rendering
        const updateSpanContinuous = (container, segId, text, isFinal, langPrefix) => {
            if (!container || !text) return;
            
            let span = document.getElementById(`${langPrefix}-seg-${segId}`);

            if (!span) {
                // Add separator if there are already final spans in the container
                const existingFinals = container.querySelectorAll('.seg-span.final');
                if (existingFinals.length > 0) {
                    const sep = document.createElement('span');
                    sep.className = 'seg-separator';
                    sep.id = `${langPrefix}-sep-${segId}`;
                    sep.textContent = ' ';
                    container.appendChild(sep);
                }

                span = document.createElement('span');
                span.id = `${langPrefix}-seg-${segId}`;
                span.className = 'seg-span';
                container.appendChild(span);
                this.displayedSegments.set(segId, span);
            }

            const words = text.split(/\s+/).filter(Boolean);
            const prevWordsStr = span.dataset.words || '';
            const prevWords = prevWordsStr ? prevWordsStr.split('|||') : [];

            // Find common prefix length
            let commonLen = 0;
            while (commonLen < words.length && commonLen < prevWords.length && words[commonLen] === prevWords[commonLen]) {
                commonLen++;
            }

            // Only update DOM if the text actually changed
            if (words.join(' ') !== prevWords.join(' ')) {
                const html = [];
                for (let i = 0; i < words.length; i++) {
                    if (i < commonLen) {
                        html.push(`<span class="word-stable">${words[i]}</span>`);
                    } else {
                        html.push(`<span class="word-fade" style="animation-delay:${(i - commonLen) * 30}ms">${words[i]}</span>`);
                    }
                }
                span.innerHTML = html.join(' ');
                span.dataset.words = words.join('|||');
            }

            if (isFinal) {
                span.classList.remove('partial');
                span.classList.add('final');
            } else {
                span.classList.add('partial');
                span.classList.remove('final');
            }
        };

        // --- Vietnamese text ---
        updateSpanContinuous(viC, id, source, is_final, 'vi');

        // --- English translation ---
        updateSpanContinuous(enC, id, target, is_final, 'en');

        this.el.panelContent.scrollTop = this.el.panelContent.scrollHeight;
    }

    _addTranscriptSplit(data) {
        const { segment_id, source, target, is_final } = data;
        const id = segment_id || 0;

        if (!this.el.panelContent) return;

        const emptyState = this.el.panelContent.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        // Ensure split container exists (top=source, bottom=target)
        let splitContainer = this.el.panelContent.querySelector('.split-container');
        if (!splitContainer) {
            splitContainer = document.createElement('div');
            splitContainer.className = 'split-container';
            splitContainer.innerHTML = `
                <div class="split-pane split-pane-source" id="splitSource">
                    <div class="split-pane-label">Source</div>
                    <div class="split-pane-body"></div>
                </div>
                <div class="split-divider"></div>
                <div class="split-pane split-pane-target" id="splitTarget">
                    <div class="split-pane-label">Translation</div>
                    <div class="split-pane-body"></div>
                </div>
            `;
            this.el.panelContent.appendChild(splitContainer);
        }

        const srcBody = splitContainer.querySelector('.split-pane-source .split-pane-body');
        const tgtBody = splitContainer.querySelector('.split-pane-target .split-pane-body');

        const updateSplitSpan = (container, text, isFinal) => {
            if (!container || !text) return;
            let span = container.querySelector(`[data-seg="${id}"]`);
            if (!span) {
                span = document.createElement('span');
                span.dataset.seg = id;
                span.className = 'split-seg';
                if (container.children.length > 0) {
                    const sep = document.createElement('span');
                    sep.textContent = ' ';
                    container.appendChild(sep);
                }
                container.appendChild(span);
            }

            const words = text.split(/\s+/).filter(Boolean);
            const prevWordsStr = span.dataset.words || '';
            const prevWords = prevWordsStr ? prevWordsStr.split('|||') : [];

            let commonLen = 0;
            while (commonLen < words.length && commonLen < prevWords.length && words[commonLen] === prevWords[commonLen]) {
                commonLen++;
            }

            if (words.join(' ') !== prevWords.join(' ')) {
                const html = [];
                for (let i = 0; i < words.length; i++) {
                    if (i < commonLen) {
                        html.push(`<span class="word-stable">${words[i]}</span>`);
                    } else {
                        html.push(`<span class="word-fade" style="animation-delay:${(i - commonLen) * 30}ms">${words[i]}</span>`);
                    }
                }
                span.innerHTML = html.join(' ');
                span.dataset.words = words.join('|||');
            }

            if (isFinal) {
                span.classList.remove('partial');
            } else {
                span.classList.add('partial');
            }
        };

        // Source text
        updateSplitSpan(srcBody, source, is_final);

        // Target text
        updateSplitSpan(tgtBody, target, is_final);

        // Auto scroll both panes
        if (srcBody) srcBody.scrollTop = srcBody.scrollHeight;
        if (tgtBody) tgtBody.scrollTop = tgtBody.scrollHeight;
    }

    clearTranscripts() {
        if (this.el.panelContent) {
            this.el.panelContent.innerHTML = '<div class="empty-state"><div class="empty-icon"><svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg></div><p>Click record to start</p></div>';
        }
        this.displayedSegments.clear();
        this.segmentDataCache.clear();
        this.closeClearModal();

        if (this.subtitleOverlay) {
            this.subtitleOverlay.clear();
        }
    }

    _clearDisplayedSegments() {
        if (!this.el.panelContent) return;
        this.el.panelContent.classList.add('switching');
        setTimeout(() => {
            this.el.panelContent.querySelectorAll('.transcript-segment, .split-row, .split-container, .container-label, .continuous-text').forEach(el => el.remove());
            this.displayedSegments.clear();
            for (const [, data] of this.segmentDataCache) {
                if (this.displayMode === 'split') {
                    this._addTranscriptSplit(data);
                } else {
                    this._addTranscriptMixed(data);
                }
            }
            this.el.panelContent.classList.remove('switching');
        }, 200);
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

    /* ═══════════ CONTEXT TEMPLATES ═══════════ */

    applyTemplate(name) {
        const TEMPLATES = {
            meeting: {
                topic: 'Business Meeting',
                keywords: 'agenda, minutes, action items, deadline, project, budget, stakeholders, KPI',
                context: 'This script is about a business meeting. You should use terms like agenda, minutes, action items, deadline, project update, and stakeholder.',
            },
            lecture: {
                topic: 'Academic Lecture',
                keywords: 'theory, concept, methodology, research, hypothesis, analysis, conclusion',
                context: 'This script is about an academic lecture. You should use terms like theory, methodology, hypothesis, research findings, and analysis.',
            },
            interview: {
                topic: 'Job Interview',
                keywords: 'experience, qualifications, skills, role, team, compensation, culture',
                context: 'This script is about a job interview. You should use terms like experience, qualifications, skills, role responsibilities, and compensation.',
            },
            medical: {
                topic: 'Medical Consultation',
                keywords: 'symptoms, diagnosis, treatment, medication, prescription, follow-up, patient',
                context: 'This script is about a medical consultation. You should use terms like symptoms, diagnosis, treatment, medication, and prescription.',
            },
            tech: {
                topic: 'Technical Presentation',
                keywords: 'API, database, architecture, framework, deployment, scalability, performance',
                context: 'This script is about a technical presentation. You should use terms like API, database, architecture, framework, deployment, and scalability.',
            },
            legal: {
                topic: 'Legal Discussion',
                keywords: 'contract, clause, compliance, regulation, liability, amendment, jurisdiction',
                context: 'This script is about a legal discussion. You should use terms like contract, clause, compliance, regulation, liability, and jurisdiction.',
            },
        };
        const tpl = TEMPLATES[name];
        if (!tpl) return;
        if (this.el.lectureTopic) this.el.lectureTopic.value = tpl.topic;
        if (this.el.keywords) this.el.keywords.value = tpl.keywords;
        if (this.el.context) this.el.context.value = tpl.context;
        this.showNotification(`Template: ${tpl.topic}`);
    }

    /* ═══════════ SETTINGS ═══════════ */

    loadSettings() {
        try {
            const saved = JSON.parse(localStorage.getItem('asr_settings') || '{}');
            const interfaceLangEl = document.getElementById('settingInterfaceLang');
            if (interfaceLangEl && saved.interfaceLang) interfaceLangEl.value = saved.interfaceLang;
            // Apply theme
            this._applyTheme(saved.theme || 'light');
            this._updateThemeSwitcher(saved.theme || 'light');
            // Apply interface language
            this._applyInterfaceLang(saved.interfaceLang || 'en');
        } catch (e) {}

        // Theme switcher
        const switcher = document.getElementById('themeSwitcher');
        if (switcher) {
            switcher.onclick = (e) => {
                const opt = e.target.closest('[data-theme]');
                if (!opt) return;
                const theme = opt.dataset.theme;
                this._applyTheme(theme);
                this._updateThemeSwitcher(theme);
            };
        }

        // Interface language change
        const interfaceLangEl = document.getElementById('settingInterfaceLang');
        if (interfaceLangEl) {
            interfaceLangEl.onchange = () => {
                this._applyInterfaceLang(interfaceLangEl.value);
            };
        }

        // Feedback
        const feedbackBtn = document.getElementById('sendFeedbackBtn');
        if (feedbackBtn) {
            feedbackBtn.onclick = () => {
                const text = document.getElementById('feedbackText')?.value?.trim();
                if (!text) { this.showNotification('Please enter feedback'); return; }
                try {
                    const fb = JSON.parse(localStorage.getItem('asr_feedback') || '[]');
                    fb.push({ text, date: new Date().toISOString(), status: 'new' });
                    localStorage.setItem('asr_feedback', JSON.stringify(fb));
                } catch (e) {}
                document.getElementById('feedbackText').value = '';
                this.showNotification('Thank you for your feedback!');
            };
        }
    }

    _applyTheme(theme) {
        let resolved = theme;
        if (theme === 'system') {
            resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        document.documentElement.setAttribute('data-theme', resolved);
        this._currentTheme = theme;
    }

    _updateThemeSwitcher(theme) {
        const switcher = document.getElementById('themeSwitcher');
        if (!switcher) return;
        switcher.querySelectorAll('.theme-opt').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === theme);
        });
    }

    /* ═══════════ INTERFACE LANGUAGE (i18n) ═══════════ */

    _applyInterfaceLang(lang) {
        this._interfaceLang = lang;
        const t = this._i18n[lang] || this._i18n['en'];

        // Toolbar
        const logoEl = document.querySelector('.logo-text');
        if (logoEl) logoEl.textContent = t.appTitle;

        // Context button
        if (this.el.contextBtn) this.el.contextBtn.title = t.contextSettings;

        // Settings modal
        const settingsTitle = this.el.settingsModal?.querySelector('.modal-header h3');
        if (settingsTitle) settingsTitle.textContent = t.settings;
        const appearanceH4 = this.el.settingsModal?.querySelector('.settings-section:first-child h4');
        if (appearanceH4) appearanceH4.textContent = t.appearance;
        const themeLabel = this.el.settingsModal?.querySelector('.settings-section:first-child .setting-row:first-child span');
        if (themeLabel) themeLabel.textContent = t.theme;
        const langLabel = this.el.settingsModal?.querySelector('.settings-section:first-child .setting-row:last-child span');
        if (langLabel) langLabel.textContent = t.interfaceLang;
        const feedbackH4 = this.el.settingsModal?.querySelector('.settings-section:last-child h4');
        if (feedbackH4) feedbackH4.textContent = t.feedback;
        const feedbackArea = document.getElementById('feedbackText');
        if (feedbackArea) feedbackArea.placeholder = t.feedbackPlaceholder;
        const feedbackBtn = document.getElementById('sendFeedbackBtn');
        if (feedbackBtn) feedbackBtn.textContent = t.sendFeedback;
        const doneBtn = this.el.settingsSave;
        if (doneBtn) doneBtn.textContent = t.done;

        // Context modal
        const ctxTitle = this.el.contextModal?.querySelector('.modal-header h3');
        if (ctxTitle) ctxTitle.textContent = t.contextSettings;
        const topicLabel = this.el.contextModal?.querySelector('.form-group:first-child label');
        if (topicLabel) topicLabel.textContent = t.lectureTopic;
        const templateLabel = this.el.contextModal?.querySelectorAll('.form-group')[1]?.querySelector('label');
        if (templateLabel) templateLabel.textContent = t.quickTemplates;
        const kwLabel = this.el.contextModal?.querySelectorAll('.form-group')[2]?.querySelector('label');
        if (kwLabel) kwLabel.textContent = t.keywords;
        const ctxLabel = this.el.contextModal?.querySelectorAll('.form-group')[3]?.querySelector('label');
        if (ctxLabel) ctxLabel.textContent = t.context;

        // Sidebar header
        const sidebarH3 = document.querySelector('.sidebar-header h3');
        if (sidebarH3) sidebarH3.textContent = t.history;
        const viewAllBtn = document.querySelector('.sidebar-btn');
        if (viewAllBtn) {
            const svg = viewAllBtn.querySelector('svg');
            viewAllBtn.textContent = '';
            if (svg) viewAllBtn.appendChild(svg);
            viewAllBtn.append(' ' + t.viewAll);
        }

        // Record button
        if (this.el.recordBtn) this.el.recordBtn.title = t.record;

        // Empty state
        const emptyP = this.el.panelContent?.querySelector('.empty-state p:not(.loading-status):not(.loading-hint)');
        if (emptyP && emptyP.textContent.includes('record')) emptyP.textContent = t.clickRecord;
    }

    get _i18n() {
        return {
            en: {
                appTitle: 'ASR Thesis',
                settings: 'Settings',
                appearance: 'Appearance',
                theme: 'Theme',
                interfaceLang: 'Interface language',
                feedback: 'Feedback',
                feedbackPlaceholder: 'Report a bug or suggest a feature...',
                sendFeedback: 'Send Feedback',
                done: 'Done',
                contextSettings: 'Context Settings',
                lectureTopic: 'Lecture Topic',
                quickTemplates: 'Quick Templates',
                keywords: 'Keywords',
                context: 'Context',
                history: 'History',
                viewAll: 'View All',
                record: 'Record',
                clickRecord: 'Click record to start',
            },
            vi: {
                appTitle: 'ASR Thesis',
                settings: 'Cài đặt',
                appearance: 'Giao diện',
                theme: 'Chủ đề',
                interfaceLang: 'Ngôn ngữ giao diện',
                feedback: 'Phản hồi',
                feedbackPlaceholder: 'Báo lỗi hoặc đề xuất tính năng...',
                sendFeedback: 'Gửi phản hồi',
                done: 'Xong',
                contextSettings: 'Cài đặt ngữ cảnh',
                lectureTopic: 'Chủ đề bài giảng',
                quickTemplates: 'Mẫu nhanh',
                keywords: 'Từ khóa',
                context: 'Ngữ cảnh',
                history: 'Lịch sử',
                viewAll: 'Xem tất cả',
                record: 'Ghi âm',
                clickRecord: 'Nhấn nút ghi âm để bắt đầu',
            },
        };
    }

    saveSettings() {
        const interfaceLang = document.getElementById('settingInterfaceLang')?.value || 'en';
        const theme = this._currentTheme || 'light';
        localStorage.setItem('asr_settings', JSON.stringify({ interfaceLang, theme }));
    }

    getSettings() {
        try {
            return JSON.parse(localStorage.getItem('asr_settings') || '{}');
        } catch (e) {
            return {};
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
                const tags = (rec.tags || []).map(t => `<span class="rec-tag">${t}</span>`).join('');
                return `
                    <div class="recording-card" data-id="${rec.id}">
                        <div class="recording-info">
                            <div class="recording-date">${starred}${name}</div>
                            <div class="recording-duration">${rec.duration || '00:00'} • ${count} segs</div>
                            ${tags ? `<div class="recording-tags">${tags}</div>` : ''}
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
