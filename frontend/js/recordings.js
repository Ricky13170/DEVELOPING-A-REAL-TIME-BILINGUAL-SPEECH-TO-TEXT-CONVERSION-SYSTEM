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

        this.selectedId = null;
        this.recordings = [];
        this.menuOpenId = null;
    }

    init() {
        this.loadRecordings();
        this.setupListeners();
        this.setupModals();
        this.setupSummarize();


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

            return `
                <div class="recording-item ${active}" data-id="${rec.id}">
                    <div class="recording-info">
                        <div class="recording-date">${starred}${name}</div>
                        <div class="recording-time">${rec.duration || '00:00'} • ${count} segments</div>
                    </div>
                    <div class="recording-actions">
                        <button class="menu-btn" data-menu="${rec.id}" title="Options">⋮</button>
                        <div class="context-menu" id="menu-${rec.id}">
                            <div class="context-menu-item" data-action="rename" data-id="${rec.id}">Rename</div>
                            <div class="context-menu-item" data-action="star" data-id="${rec.id}">${rec.starred ? 'Unstar' : 'Star'}</div>
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
            case 'export': this.exportRecording(id); break;
            case 'delete': this.showDeleteModal(id); break;
        }
    }

    toggleStar(id) {
        const rec = this.recordings.find(r => String(r.id) === String(id));
        if (rec) {
            rec.starred = !rec.starred;
            this.saveRecordings();
            this.loadRecordings();
        }
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

    /* ═══════════ COPY ═══════════ */

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

    /* ═══════════ EXPORT ═══════════ */

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

    /* ═══════════ SUMMARIZE ═══════════ */

    setupSummarize() {
        if (this.summarizeBtn) {
            this.summarizeBtn.onclick = () => this.summarizeSelected();
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
    }

    async summarizeSelected() {
        const rec = this.recordings.find(r => String(r.id) === String(this.selectedId));
        if (!rec || !rec.transcript || rec.transcript.length === 0) {
            this.showNotification('No transcript to summarize');
            return;
        }

        // Collect all source text
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
                body: JSON.stringify({ text, topic: rec.customName || '' })
            });

            if (resp.ok) {
                const data = await resp.json();
                this.showSummary(data.summary || 'No summary generated.');
            } else {
                this.showNotification('Could not generate summary');
            }
        } catch (e) {
            this.showNotification('Summary failed');
        } finally {
            if (this.summarizeBtn) this.summarizeBtn.disabled = false;
        }
    }

    showSummary(summary) {
        if (!summary || !this.summaryModal) return;

        let html = summary
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^### (.+)$/gm, '<h4>$1</h4>')
            .replace(/^## (.+)$/gm, '<h3>$1</h3>')
            .replace(/^# (.+)$/gm, '<h2>$1</h2>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/\n/g, '<br>');

        if (this.summaryContent) this.summaryContent.innerHTML = html;
        this.summaryModal.classList.add('active');
        this.showNotification('Summary ready!');
    }

    showNotification(msg) {
        if (!this.notification) return;
        this.notification.textContent = msg;
        this.notification.classList.add('active');
        setTimeout(() => this.notification.classList.remove('active'), 2500);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new RecordingsManager().init();
});