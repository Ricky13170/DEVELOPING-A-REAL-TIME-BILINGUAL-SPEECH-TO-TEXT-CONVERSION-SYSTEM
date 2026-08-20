import { exportSRT, exportVTT, exportTXT, exportJSON } from './export.js';

class RecordingsManager {
    constructor() {
        this.listEl = document.getElementById('recordingsList');
        this.contentEl = document.getElementById('transcriptContent');
        this.titleEl = document.getElementById('recordingTitle');
        this.subtitleEl = document.getElementById('recordingSubtitle');
        this.summarizeBtn = document.getElementById('summarizeBtn');
        this.summaryModal = document.getElementById('summaryModal');
        this.summaryContent = document.getElementById('summaryContent');
        this.notification = document.getElementById('notification');

        this.summaryLangSelect = document.getElementById('summaryLangSelect');
        this.qaPanel = document.getElementById('qaPanel');
        this.qaChat = document.getElementById('qaChat');
        this.qaInput = document.getElementById('qaInput');
        this.contentBody = document.getElementById('contentBody');

        this.selectedId = null;
        this.recordings = [];
        this.menuOpenId = null;
        this._originalSummary = null;
        this._summaryLayoutBlocks = null;
        this._currentSummaryBlocks = null;
        this.groqAvailable = false;
    }

    init() {
        this.loadRecordings();
        this.setupListeners();
        this.setupModals();
        this.setupSummarize();
        this.setupQA();
        this.configureOptionalFeatures();


        const preSelected = localStorage.getItem('selectedRecordingId');
        if (preSelected) {
            localStorage.removeItem('selectedRecordingId');
            setTimeout(() => this.selectRecording(preSelected), 200);
        } else if (this.recordings.length > 0) {
            this.selectRecording(this.recordings[0].id);
        }
    }

    loadRecordings() {
        try {
            this.recordings = JSON.parse(localStorage.getItem('recordings') || '[]');
            // Sort: starred first, then by date
            this.recordings.sort((a, b) => {
                if (a.starred && !b.starred) return -1;
                if (!a.starred && b.starred) return 1;
                return (b.id || 0) - (a.id || 0);
            });
        } catch (e) {
            this.recordings = [];
        }
        this.renderList();
    }

    renderList() {
        if (!this.listEl) return;

        if (this.recordings.length === 0) {
            this.listEl.innerHTML = '<div class="empty-state"><p>No recordings</p></div>';
            return;
        }

        this.listEl.innerHTML = this.recordings.map(rec => {
            const name = rec.customName || `${rec.date} ${rec.time}`;
            const count = rec.transcript?.length || 0;
            const active = String(rec.id) === String(this.selectedId) ? 'active' : '';
            const starred = rec.starred ? '⭐ ' : '';
            const tags = (rec.tags || []).map(t => `<span class="rec-tag">${this._escapeHtml(t)}</span>`).join('');

            return `
                <div class="recording-item ${active}" data-id="${rec.id}">
                    <div class="recording-info">
                        <div class="recording-date">${starred}${this._escapeHtml(name)}</div>
                        <div class="recording-time">${rec.duration || '00:00'} • ${count} segments</div>
                        ${tags ? `<div class="recording-tags">${tags}</div>` : ''}
                    </div>
                    <div class="recording-actions">
                        <button class="menu-btn" data-menu="${rec.id}" title="Options">⋮</button>
                        <div class="context-menu" id="menu-${rec.id}">
                            <div class="context-menu-item" data-action="rename" data-id="${rec.id}">Rename</div>
                            <div class="context-menu-item" data-action="star" data-id="${rec.id}">${rec.starred ? 'Unstar' : 'Star'}</div>
                            <div class="context-menu-item" data-action="tag" data-id="${rec.id}">Add Tag</div>
                            <div class="context-menu-item" data-action="export" data-id="${rec.id}">Export</div>
                            <div class="context-menu-item delete" data-action="delete" data-id="${rec.id}">Delete</div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }

    setupListeners() {
        if (!this.listEl) return;

        document.addEventListener('click', () => {
            this.closeAllMenus();
        });

        this.listEl.addEventListener('click', (e) => {
            const menuBtn = e.target.closest('[data-menu]');
            if (menuBtn) {
                e.stopPropagation();
                const id = menuBtn.dataset.menu;
                this.toggleMenu(id);
                return;
            }

            const actionEl = e.target.closest('[data-action]');
            if (actionEl) {
                e.stopPropagation();
                const { action, id } = actionEl.dataset;
                this.handleAction(action, id);
                this.closeAllMenus();
                return;
            }

            const item = e.target.closest('.recording-item');
            if (item) {
                this.selectRecording(item.dataset.id);
            }
        });
    }

    toggleMenu(id) {
        const menu = document.getElementById(`menu-${id}`);
        if (!menu) return;

        const isOpen = menu.classList.contains('active');
        this.closeAllMenus();

        if (!isOpen) {
            menu.classList.add('active');
            this.menuOpenId = id;
        }
    }

    closeAllMenus() {
        document.querySelectorAll('.context-menu.active').forEach(m => m.classList.remove('active'));
        this.menuOpenId = null;
    }

    handleAction(action, id) {
        switch (action) {
            case 'rename': this.showRenameModal(id); break;
            case 'star': this.toggleStar(id); break;
            case 'tag': this.showTagModal(id); break;
            case 'export': this.exportRecording(id); break;
            case 'delete': this.showDeleteModal(id); break;
        }
    }

    toggleStar(id) {
        const rec = this.recordings.find(r => String(r.id) === String(id));
        if (rec) {
            rec.starred = !rec.starred;
            this.saveRecordings();
            this.renderList();
            if (String(this.selectedId) === String(id)) this.selectRecording(id);
        }
    }

    showTagModal(id) {
        this.pendingTagId = id;
        const input = document.getElementById('tagInput');
        if (input) input.value = '';
        this._renderTagList();
        document.getElementById('tagModal')?.classList.add('active');
    }

    hideTagModal() {
        document.getElementById('tagModal')?.classList.remove('active');
        this.pendingTagId = null;
    }

    _renderTagList() {
        const container = document.getElementById('tagListManage');
        if (!container) return;
        const rec = this.recordings.find(r => String(r.id) === String(this.pendingTagId));
        const tags = rec?.tags || [];
        if (tags.length === 0) {
            container.innerHTML = '<div class="empty-tags-hint">No tags yet</div>';
            return;
        }
        container.innerHTML = tags.map(t => `
            <div class="tag-manage-item">
                <span class="tag-manage-label">${this._escapeHtml(t)}</span>
                <button class="tag-manage-delete" data-remove-tag="${this._escapeHtml(t)}" title="Remove">&times;</button>
            </div>
        `).join('');
    }

    removeTag(tagName) {
        const rec = this.recordings.find(r => String(r.id) === String(this.pendingTagId));
        if (!rec || !rec.tags) return;
        rec.tags = rec.tags.filter(t => t !== tagName);
        this.saveRecordings();
        this.renderList();
        this._renderTagList();
        if (String(this.selectedId) === String(this.pendingTagId)) this.selectRecording(this.pendingTagId);
    }

    saveTag(tagValue) {
        const tag = (tagValue || '').trim().toLowerCase().substring(0, 20);
        if (!tag || !this.pendingTagId) return;
        const rec = this.recordings.find(r => String(r.id) === String(this.pendingTagId));
        if (rec) {
            if (!rec.tags) rec.tags = [];
            if (!rec.tags.includes(tag)) {
                rec.tags.push(tag);
                this.saveRecordings();
                this.renderList();
            }
        }
        const input = document.getElementById('tagInput');
        if (input) input.value = '';
        this._renderTagList();
    }

    addTag(id) {
        this.showTagModal(id);
    }

    exportRecording(id) {
        const rec = this.recordings.find(r => String(r.id) === String(id));
        if (rec && rec.transcript) {
            exportSRT(rec.transcript);
        }
    }

    setupModals() {
        const renameModal = document.getElementById('renameModal');
        const renameClose = document.getElementById('renameModalClose');
        const renameCancel = document.getElementById('renameModalCancel');
        const renameSave = document.getElementById('renameModalSave');

        if (renameClose) renameClose.onclick = () => this.hideRenameModal();
        if (renameCancel) renameCancel.onclick = () => this.hideRenameModal();
        if (renameSave) renameSave.onclick = () => this.saveRename();
        if (renameModal) renameModal.onclick = (e) => {
            if (e.target === renameModal) this.hideRenameModal();
        };

        const deleteModal = document.getElementById('deleteModal');
        const deleteClose = document.getElementById('deleteModalClose');
        const deleteCancel = document.getElementById('deleteModalCancel');
        const deleteConfirm = document.getElementById('deleteModalConfirm');

        if (deleteClose) deleteClose.onclick = () => this.hideDeleteModal();
        if (deleteCancel) deleteCancel.onclick = () => this.hideDeleteModal();
        if (deleteConfirm) deleteConfirm.onclick = () => this.confirmDelete();
        if (deleteModal) deleteModal.onclick = (e) => {
            if (e.target === deleteModal) this.hideDeleteModal();
        };

        // Tag modal
        const tagModal = document.getElementById('tagModal');
        const tagClose = document.getElementById('tagModalClose');
        const tagCancel = document.getElementById('tagModalCancel');
        const tagSave = document.getElementById('tagModalSave');
        const tagInput = document.getElementById('tagInput');
        const tagSuggestions = document.getElementById('tagSuggestions');
        const tagListManage = document.getElementById('tagListManage');

        if (tagClose) tagClose.onclick = () => this.hideTagModal();
        if (tagCancel) tagCancel.onclick = () => this.hideTagModal();
        if (tagSave) tagSave.onclick = () => this.saveTag(tagInput?.value);
        if (tagInput) tagInput.onkeydown = (e) => { if (e.key === 'Enter') this.saveTag(tagInput.value); };
        if (tagModal) tagModal.onclick = (e) => { if (e.target === tagModal) this.hideTagModal(); };
        if (tagSuggestions) {
            tagSuggestions.onclick = (e) => {
                const chip = e.target.closest('[data-tag]');
                if (chip) this.saveTag(chip.dataset.tag);
            };
        }
        if (tagListManage) {
            tagListManage.onclick = (e) => {
                const delBtn = e.target.closest('[data-remove-tag]');
                if (delBtn) this.removeTag(delBtn.dataset.removeTag);
            };
        }
    }

    showRenameModal(id) {
        this.pendingRenameId = id;
        const rec = this.recordings.find(r => String(r.id) === String(id));
        const input = document.getElementById('renameInput');
        if (input && rec) {
            input.value = rec.customName || `${rec.date} ${rec.time}`;
        }
        document.getElementById('renameModal')?.classList.add('active');
    }

    hideRenameModal() {
        document.getElementById('renameModal')?.classList.remove('active');
        this.pendingRenameId = null;
    }

    saveRename() {
        const input = document.getElementById('renameInput');
        const newName = input?.value?.trim();
        if (!newName || !this.pendingRenameId) {
            this.hideRenameModal();
            return;
        }

        const rec = this.recordings.find(r => String(r.id) === String(this.pendingRenameId));
        if (rec) {
            rec.customName = newName;
            this.saveRecordings();
            this.renderList();
            if (String(this.selectedId) === String(this.pendingRenameId)) {
                this.selectRecording(this.pendingRenameId);
            }
        }
        this.hideRenameModal();
    }

    showDeleteModal(id) {
        this.pendingDeleteId = id;
        document.getElementById('deleteModal')?.classList.add('active');
    }

    hideDeleteModal() {
        document.getElementById('deleteModal')?.classList.remove('active');
        this.pendingDeleteId = null;
    }

    confirmDelete() {
        if (!this.pendingDeleteId) {
            this.hideDeleteModal();
            return;
        }

        this.recordings = this.recordings.filter(r => String(r.id) !== String(this.pendingDeleteId));
        this.saveRecordings();

        if (String(this.selectedId) === String(this.pendingDeleteId)) {
            this.selectedId = null;
            this.showEmpty();
        }

        this.renderList();
        this.hideDeleteModal();
    }

    saveRecordings() {
        localStorage.setItem('recordings', JSON.stringify(this.recordings));
    }

    selectRecording(id) {
        this.selectedId = id;

        this.listEl?.querySelectorAll('.recording-item').forEach(el => {
            el.classList.toggle('active', String(el.dataset.id) === String(id));
        });

        const rec = this.recordings.find(r => String(r.id) === String(id));
        if (!rec) {
            this.showEmpty();
            return;
        }

        const name = rec.customName || `${rec.date} ${rec.time}`;
        const starred = rec.starred ? '⭐ ' : '';
        if (this.titleEl) this.titleEl.textContent = starred + name;
        if (this.subtitleEl) this.subtitleEl.textContent = `${rec.duration || '00:00'} • ${rec.transcript?.length || 0} segments`;

        // Reset summary state for new recording
        this._originalSummary = null;
        this._summaryLayoutBlocks = null;
        this._currentSummaryBlocks = null;
        if (this.summaryLangSelect) this.summaryLangSelect.value = 'en';
        if (this.viewSummaryBtn) this.viewSummaryBtn.classList.add('hidden');
        this.summaryModal?.classList.remove('active');
        this.closeQA();

        this.renderTranscript(rec.transcript || []);
    }

    renderTranscript(transcript) {
        const container = this.contentEl?.querySelector('.transcript-container-full') || this.contentEl;
        if (!container) return;

        if (!transcript || transcript.length === 0) {
            container.innerHTML = '<div class="empty-state"><p>No transcript</p></div>';
            return;
        }

        container.innerHTML = transcript.map((item, i) => {
            const src = item.source || item.vi || '';
            const tgt = item.target || item.en || '';

            return `
                <div class="transcript-segment final">
                    <div class="src-text">${src}</div>
                    ${tgt ? `<div class="tgt-text">${tgt}</div>` : ''}
                </div>
            `;
        }).join('');
    }

    showEmpty() {
        if (this.titleEl) this.titleEl.textContent = 'Select a recording';
        if (this.subtitleEl) this.subtitleEl.textContent = '';

        const container = this.contentEl?.querySelector('.transcript-container-full') || this.contentEl;
        if (container) {
            container.innerHTML = '<div class="empty-state"><p>Select a recording</p></div>';
        }
    }

    setupCopy() {
        if (this.copyBtn) {
            this.copyBtn.onclick = () => this.copyTranscript();
        }
    }

    async copyTranscript() {
        const rec = this.recordings.find(r => String(r.id) === String(this.selectedId));
        if (!rec || !rec.transcript || rec.transcript.length === 0) {
            this.showNotification('No transcript to copy');
            return;
        }
        const lines = rec.transcript.map(t => {
            const src = t.source || t.vi || '';
            const tgt = t.target || t.en || '';
            return tgt ? `${src}\n${tgt}` : src;
        }).filter(s => s.trim());
        try {
            await navigator.clipboard.writeText(lines.join('\n\n'));
            this.showNotification('Copied!');
        } catch (e) {
            this.showNotification('Copy failed');
        }
    }

    setupExport() {
        if (this.exportBtn) {
            this.exportBtn.onclick = (e) => {
                e.stopPropagation();
                this.exportMenu?.classList.toggle('active');
            };
        }
        if (this.exportMenu) {
            this.exportMenu.querySelectorAll('[data-format]').forEach(item => {
                item.onclick = (e) => {
                    e.stopPropagation();
                    this.exportAs(item.dataset.format);
                    this.exportMenu.classList.remove('active');
                };
            });
        }
        document.addEventListener('click', () => {
            this.exportMenu?.classList.remove('active');
        });
    }

    exportAs(format) {
        const rec = this.recordings.find(r => String(r.id) === String(this.selectedId));
        if (!rec || !rec.transcript) {
            this.showNotification('No transcript to export');
            return;
        }
        const transcript = rec.transcript.map(t => ({
            source: t.source || t.vi || '',
            target: t.target || t.en || ''
        }));
        try {
            switch (format) {
                case 'srt': exportSRT(transcript); break;
                case 'vtt': exportVTT(transcript); break;
                case 'txt': exportTXT(transcript); break;
                case 'json': exportJSON(transcript); break;
            }
            this.showNotification(`Exported as ${format.toUpperCase()}`);
        } catch (e) {
            this.showNotification('Export failed');
        }
    }

    setupSummarize() {
        if (this.summarizeBtn) {
            this.summarizeBtn.onclick = () => this.summarizeSelected();
        }

        this.viewSummaryBtn = document.getElementById('viewSummaryBtn');
        if (this.viewSummaryBtn) {
            this.viewSummaryBtn.onclick = () => {
                if (this._currentSummaryBlocks && this.summaryModal) {
                    this._renderSummaryBlocks(this._currentSummaryBlocks);
                    this.summaryModal.classList.add('active');
                }
            };
        }

        const closeSummaryBtn = document.getElementById('closeSummaryBtn');
        const closeSummaryX = document.getElementById('closeSummaryModal');
        const copySummaryBtn = document.getElementById('copySummaryBtn');
        const closeSummary = () => this.summaryModal?.classList.remove('active');

        if (closeSummaryBtn) closeSummaryBtn.onclick = closeSummary;
        if (closeSummaryX) closeSummaryX.onclick = closeSummary;
        if (copySummaryBtn) {
            copySummaryBtn.onclick = async () => {
                const text = this.summaryContent?.innerText;
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
        if (this.summaryModal) {
            this.summaryModal.onclick = (e) => {
                if (e.target === this.summaryModal) closeSummary();
            };
        }

        // Language change → translate through the local VI↔EN model
        if (this.summaryLangSelect) {
            this.summaryLangSelect.onchange = () => this._translateSummary();
        }

        // Font size controls
        this._summaryFontSize = parseFloat(localStorage.getItem('summaryFontSize') || '0.95');
        const fontDec = document.getElementById('summaryFontDec');
        const fontInc = document.getElementById('summaryFontInc');
        this._applySummaryFontSize();
        if (fontDec) fontDec.onclick = () => {
            this._summaryFontSize = Math.max(0.7, this._summaryFontSize - 0.05);
            this._applySummaryFontSize();
        };
        if (fontInc) fontInc.onclick = () => {
            this._summaryFontSize = Math.min(1.6, this._summaryFontSize + 0.05);
            this._applySummaryFontSize();
        };
    }

    async configureOptionalFeatures() {
        try {
            const response = await fetch('/api/status');
            const data = response.ok ? await response.json() : {};
            this.groqAvailable = Array.isArray(data.features)
                && data.features.includes('groq_extras');
        } catch (error) {
            this.groqAvailable = false;
        }

        const askAiBtn = document.getElementById('askAiBtn');
        const qaSendBtn = document.getElementById('qaSendBtn');
        for (const button of [this.summarizeBtn, askAiBtn, qaSendBtn]) {
            if (!button) continue;
            button.disabled = !this.groqAvailable;
            if (!this.groqAvailable) {
                button.title = 'Optional cloud AI is disabled in offline mode';
            }
        }
    }

    async summarizeSelected() {
        const rec = this.recordings.find(r => String(r.id) === String(this.selectedId));
        if (!rec || !rec.transcript || rec.transcript.length === 0) {
            this.showNotification('No transcript to summarize');
            return;
        }

        const text = rec.transcript
            .map(t => t.vi || t.source || '')
            .filter(s => s.trim())
            .join(' ');

        if (!text.trim()) {
            this.showNotification('No text to summarize');
            return;
        }

        this.showNotification('Generating summary...');
        if (this.summarizeBtn) this.summarizeBtn.disabled = true;

        try {
            const resp = await fetch('/api/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, topic: rec.customName || '', language: 'en' })
            });

            if (resp.ok) {
                const data = await resp.json();
                this._originalSummary = data.summary || 'No summary generated.';
                this._summaryLayoutBlocks = this._buildSummaryBlocks(this._originalSummary);
                if (this.summaryLangSelect) this.summaryLangSelect.value = 'en';
                this.showSummary(this._summaryLayoutBlocks);
                if (this.viewSummaryBtn) this.viewSummaryBtn.classList.remove('hidden');
            } else {
                this.showNotification('Could not generate summary');
            }
        } catch (e) {
            this.showNotification('Summary failed');
        } finally {
            if (this.summarizeBtn) this.summarizeBtn.disabled = !this.groqAvailable;
        }
    }

    async _translateSummary() {
        const lang = this.summaryLangSelect?.value;
        if (!lang || !this._summaryLayoutBlocks?.length) return;

        if (lang === 'en') {
            this.showSummary(this._summaryLayoutBlocks);
            return;
        }

        const option = this.summaryLangSelect.selectedOptions[0];
        const targetLanguage = option?.dataset?.translation;
        if (!targetLanguage) return;

        if (this.summaryContent) {
            this.summaryContent.innerHTML = '<div class="summary-loading">Translating...</div>';
            this._applySummaryFontSize();
        }

        try {
            const translatedBlocks = await Promise.all(this._summaryLayoutBlocks.map(async (block) => {
                if (!block?.text?.trim()) return { ...block };

                const resp = await fetch('/api/translate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: block.text, src_lang: 'eng_Latn', tgt_lang: targetLanguage })
                });

                if (!resp.ok) return { ...block };

                const data = await resp.json();
                const translated = (data.translated || '').trim();
                return { ...block, text: translated || block.text };
            }));

            this.showSummary(translatedBlocks);
        } catch (e) {
            this.showNotification('Translation failed');
            this.showSummary(this._summaryLayoutBlocks);
        }
    }

    showSummary(summary) {
        if (!summary || !this.summaryModal) return;

        const blocks = Array.isArray(summary)
            ? summary
            : this._buildSummaryBlocks(summary);

        this._renderSummaryBlocks(blocks);
        this._currentSummaryBlocks = blocks;
        this.summaryModal.classList.add('active');
        this.showNotification('Summary ready!');
    }

    _buildSummaryBlocks(text) {
        const lines = String(text || '').split('\n');
        const blocks = [];

        for (const rawLine of lines) {
            const normalized = this._normalizeSummaryLine(rawLine);
            if (!normalized) continue;

            const { text: line, isBullet } = normalized;
            const isUpperHeader = /^[A-Z][A-Z\s&\/]{2,}:?$/.test(line);
            const isTitleCaseHeader = /^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,5}:?$/.test(line) && line.length <= 64;
            const isHeader = isUpperHeader || isTitleCaseHeader;

            blocks.push({
                type: isHeader ? 'title' : (isBullet ? 'bullet' : 'line'),
                text: line.replace(/:$/, '')
            });
        }

        return blocks;
    }

    _normalizeSummaryLine(rawLine) {
        let line = String(rawLine || '').trim();
        if (!line) return null;

        line = line.replace(/^#{1,6}\s*/, '');
        line = line.replace(/\*\*(.*?)\*\*/g, '$1');
        line = line.replace(/__(.*?)__/g, '$1');
        line = line.replace(/`([^`]+)`/g, '$1');

        const bulletMatch = line.match(/^[-*•]\s+(.+)$/);
        if (bulletMatch) {
            return {
                text: bulletMatch[1].trim(),
                isBullet: true,
            };
        }

        return {
            text: line.trim(),
            isBullet: false,
        };
    }

    _renderSummaryBlocks(blocks) {
        if (!this.summaryContent) return;

        const htmlParts = [];
        for (const block of blocks || []) {
            if (!block?.text) continue;

            if (block.type === 'title') {
                htmlParts.push(`<div class="summary-section-title">${this._escapeHtml(block.text)}</div>`);
                continue;
            }

            if (block.type === 'bullet') {
                htmlParts.push(`
                    <p class="summary-line summary-line-bullet">
                        <span class="summary-bullet-dot">•</span>
                        <span>${this._escapeHtml(block.text)}</span>
                    </p>
                `);
                continue;
            }

            const numbered = block.text.match(/^(\d+[.)]\s+)(.+)$/);
            if (numbered) {
                htmlParts.push(`
                    <p class="summary-line summary-line-numbered">
                        <span class="summary-item-num">${this._escapeHtml(numbered[1].trim())}</span>
                        <span>${this._escapeHtml(numbered[2])}</span>
                    </p>
                `);
            } else {
                htmlParts.push(`<p class="summary-line">${this._escapeHtml(block.text)}</p>`);
            }
        }

        this.summaryContent.innerHTML = htmlParts.join('');
        this._applySummaryFontSize();
    }

    _applySummaryFontSize() {
        if (this.summaryContent) {
            this.summaryContent.style.fontSize = `${this._summaryFontSize}rem`;
        }
        localStorage.setItem('summaryFontSize', String(this._summaryFontSize));
    }

    showNotification(msg) {
        if (!this.notification) return;
        this.notification.textContent = msg;
        this.notification.classList.add('active');
        setTimeout(() => this.notification.classList.remove('active'), 2500);
    }

    setupQA() {
        const closeQaPanel = document.getElementById('closeQaPanel');
        const askAiBtn = document.getElementById('askAiBtn');
        const qaSendBtn = document.getElementById('qaSendBtn');

        if (closeQaPanel) closeQaPanel.onclick = () => this.closeQA();
        if (askAiBtn) {
            askAiBtn.onclick = () => {
                this.summaryModal?.classList.remove('active');
                this.openQA();
            };
        }
        if (qaSendBtn) qaSendBtn.onclick = () => this.sendQA();
        if (this.qaInput) {
            this.qaInput.onkeydown = (e) => { if (e.key === 'Enter') this.sendQA(); };
        }

        this._setupQAResizer();
    }

    _setupQAResizer() {
        const resizer = document.getElementById('qaResizer');
        if (!resizer || !this.qaPanel || !this.contentBody) return;

        let isResizing = false;
        let startX = 0;
        let startWidth = 0;

        const onStart = (e) => {
            isResizing = true;
            startX = e.clientX || e.touches?.[0]?.clientX || 0;
            startWidth = this.qaPanel.offsetWidth;
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
            e.preventDefault();
        };

        const onMove = (e) => {
            if (!isResizing) return;
            const clientX = e.clientX || e.touches?.[0]?.clientX || 0;
            const dx = startX - clientX; 
            const containerW = this.contentBody.offsetWidth;
            const newWidth = Math.max(280, Math.min(containerW * 0.7, startWidth + dx));
            this.qaPanel.style.width = `${newWidth}px`;
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

    openQA() {
        if (!this.qaPanel) return;
        if (this.qaChat) {
            this.qaChat.innerHTML = '<div class="qa-welcome"><div class="qa-welcome-icon">✦</div><p>Ask any question about the transcript content.</p></div>';
        }
        this.qaPanel.classList.remove('hidden');
        this.contentBody?.classList.add('qa-active');
        this.qaInput?.focus();
    }

    closeQA() {
        this.qaPanel?.classList.add('hidden');
        this.contentBody?.classList.remove('qa-active');
        if (this.qaPanel) this.qaPanel.style.width = '';
    }

    async sendQA() {
        const question = this.qaInput?.value?.trim();
        if (!question) return;

        const rec = this.recordings.find(r => String(r.id) === String(this.selectedId));
        if (!rec || !rec.transcript?.length) {
            this.showNotification('No transcript available');
            return;
        }

        // Add user message
        this._appendQAMessage('user', question);
        this.qaInput.value = '';

        const transcript = rec.transcript
            .map(t => {
                const source = t.source || t.vi || '';
                const target = t.target || t.en || '';
                return [source, target].filter(Boolean).join('\n');
            })
            .filter(s => s.trim())
            .join('\n\n');

        // Show typing indicator
        const typingEl = this._appendQAMessage('ai', '...');
        typingEl.classList.add('typing');

        try {
            const resp = await fetch('/api/qa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, transcript, topic: rec.customName || '' })
            });

            if (resp.ok) {
                const data = await resp.json();
                typingEl.classList.remove('typing');
                typingEl.textContent = this._stripMarkdown(data.answer || 'No answer generated.');
            } else {
                typingEl.classList.remove('typing');
                typingEl.textContent = 'Could not get an answer. Please try again.';
            }
        } catch (e) {
            typingEl.classList.remove('typing');
            typingEl.textContent = 'Connection error. Please try again.';
        }
    }

    _appendQAMessage(role, text) {
        const msg = document.createElement('div');
        msg.className = `qa-message qa-${role}`;
        msg.textContent = text;
        this.qaChat?.appendChild(msg);
        if (this.qaChat) this.qaChat.scrollTop = this.qaChat.scrollHeight;
        return msg;
    }

    _stripMarkdown(text) {
        if (!text) return '';

        return String(text)
            .replace(/```[\s\S]*?```/g, '')
            .replace(/^\s{0,3}#{1,6}\s*/gm, '')
            .replace(/\*\*(.*?)\*\*/g, '$1')
            .replace(/__(.*?)__/g, '$1')
            .replace(/\*(.*?)\*/g, '$1')
            .replace(/_(.*?)_/g, '$1')
            .replace(/`([^`]*)`/g, '$1')
            .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
            .replace(/^[ \t]*[-*+][ \t]+/gm, '')
            .replace(/^[ \t]*>+[ \t]?/gm, '')
            .replace(/\n{3,}/g, '\n\n')
            .trim();
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new RecordingsManager().init();
});
