/**
 * SubtitleOverlay — Floating subtitle display over a video element.
 * Shows bilingual captions (source + translation) with auto-fade.
 */
export class SubtitleOverlay {
    constructor(containerEl) {
        this.container = containerEl;
        this.el = null;
        this.sourceEl = null;
        this.targetEl = null;
        this.fadeTimer = null;
        this.fadeDuration = 5000; // ms before fade-out after last update
        this._build();
    }

    _build() {
        this.el = document.createElement('div');
        this.el.className = 'subtitle-overlay';
        this.el.innerHTML = `
            <div class="subtitle-source"></div>
            <div class="subtitle-target"></div>
        `;
        this.sourceEl = this.el.querySelector('.subtitle-source');
        this.targetEl = this.el.querySelector('.subtitle-target');
        this.container.appendChild(this.el);
    }

    /**
     * Update subtitle text.
     * @param {string} source - Source language text
     * @param {string} target - Translated text (optional)
     * @param {boolean} isFinal - Whether the segment is finalized
     */
    update(source, target = '', isFinal = false) {
        if (!source && !target) return;

        this.el.classList.add('visible');
        this.el.classList.remove('fade-out');

        if (source) {
            this.sourceEl.textContent = source;
            this.sourceEl.classList.toggle('partial', !isFinal);
        }

        if (target) {
            this.targetEl.textContent = target;
            this.targetEl.style.display = 'block';
        } else {
            this.targetEl.style.display = isFinal ? 'block' : 'none';
        }

        // Reset fade timer
        this._resetFade();
    }

    _resetFade() {
        if (this.fadeTimer) clearTimeout(this.fadeTimer);
        this.fadeTimer = setTimeout(() => {
            this.el.classList.add('fade-out');
        }, this.fadeDuration);
    }

    /** Clear all subtitle text */
    clear() {
        this.sourceEl.textContent = '';
        this.targetEl.textContent = '';
        this.el.classList.remove('visible');
        if (this.fadeTimer) clearTimeout(this.fadeTimer);
    }

    /** Remove the overlay element entirely */
    destroy() {
        this.clear();
        if (this.el && this.el.parentNode) {
            this.el.parentNode.removeChild(this.el);
        }
    }

    /** Set font size for subtitles */
    setFontSize(level) {
        this.el.classList.remove('subtitle-sm', 'subtitle-lg', 'subtitle-xl');
        if (level === -1) this.el.classList.add('subtitle-sm');
        else if (level === 1) this.el.classList.add('subtitle-lg');
        else if (level >= 2) this.el.classList.add('subtitle-xl');
    }
}
