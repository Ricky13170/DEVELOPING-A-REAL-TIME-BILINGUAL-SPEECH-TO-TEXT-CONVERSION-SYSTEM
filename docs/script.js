/* ═══════════ NAV SCROLL EFFECT ═══════════ */
window.addEventListener('scroll', () => {
    document.getElementById('nav')?.classList.toggle('scrolled', window.scrollY > 40);
});

/* ═══════════ WAVEFORM CANVAS ═══════════ */
(function initWave() {
    const canvas = document.getElementById('waveCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let w, h, time = 0;

    function resize() {
        w = canvas.width = canvas.offsetWidth * devicePixelRatio;
        h = canvas.height = canvas.offsetHeight * devicePixelRatio;
        ctx.scale(devicePixelRatio, devicePixelRatio);
    }
    resize();
    window.addEventListener('resize', resize);

    function draw() {
        const cw = canvas.offsetWidth, ch = canvas.offsetHeight;
        ctx.clearRect(0, 0, cw, ch);
        time += 0.015;

        for (let l = 0; l < 3; l++) {
            ctx.beginPath();
            const alpha = 0.15 - l * 0.04;
            ctx.strokeStyle = `rgba(108,99,255,${alpha})`;
            ctx.lineWidth = 1.5;
            for (let x = 0; x <= cw; x += 2) {
                const y = ch / 2 +
                    Math.sin(x * 0.008 + time + l) * 15 +
                    Math.sin(x * 0.015 + time * 1.3 + l * 2) * 10 +
                    Math.sin(x * 0.003 + time * 0.7) * 20;
                x === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
            }
            ctx.stroke();
        }
        requestAnimationFrame(draw);
    }
    draw();
})();

/* ═══════════ SCROLL ANIMATIONS ═══════════ */
document.addEventListener('DOMContentLoaded', () => {
    const targets = document.querySelectorAll(
        '.pipe-step, .feature-card, .bench-card, .step-card, .section-header, .arch-image, .tech-stack, .bench-table-wrap, .demo-container'
    );
    targets.forEach(el => el.classList.add('fade-up'));

    const io = new IntersectionObserver((entries) => {
        entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); io.unobserve(e.target); } });
    }, { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    targets.forEach(el => io.observe(el));
});

/* ═══════════ INTERACTIVE DEMO ═══════════ */
const DEMO_SCRIPT = [
    { vi: "Dừng băng chuyền trước khi bảo trì", en: "Stop the conveyor before maintenance", delay: 800 },
    { vi: "Khóa nguồn điện và treo thẻ cảnh báo", en: "Lock out the power and attach a warning tag", delay: 1200 },
    { vi: "Áp suất đường ống đang ở mức sáu bar", en: "The line pressure is at six bar", delay: 1500 },
    { vi: "Kiểm tra cảm biến số ba ở khu vực đóng gói", en: "Check sensor number three in the packing area", delay: 1000 },
    { vi: "Xe nâng đang đi vào cửa kho phía đông", en: "The forklift is entering the east warehouse door", delay: 1800 },
    { vi: "Nguy hiểm, không khởi động máy", en: "Danger, do not start the machine", delay: 1600 },
];

(function initDemo() {
    const btn = document.getElementById('demoPlayBtn');
    const status = document.getElementById('demoStatus');
    const transcript = document.getElementById('demoTranscript');
    const meter = document.getElementById('demoMeter');
    if (!btn) return;

    let playing = false, timeouts = [];

    btn.addEventListener('click', () => {
        if (playing) { stopDemo(); return; }
        startDemo();
    });

    function startDemo() {
        playing = true;
        btn.classList.add('playing');
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>';
        status.textContent = 'Processing audio...';
        meter.classList.add('active');
        transcript.innerHTML = '';

        let totalDelay = 0;
        DEMO_SCRIPT.forEach((line, i) => {
            // Show partial (Vietnamese) first
            timeouts.push(setTimeout(() => {
                if (!playing) return;
                addSegment(line.vi, '', false, i);
                status.textContent = `Segment ${i + 1}/${DEMO_SCRIPT.length} — Transcribing...`;
            }, totalDelay));

            // Then show final with translation
            timeouts.push(setTimeout(() => {
                if (!playing) return;
                addSegment(line.vi, line.en, true, i);
                status.textContent = `Segment ${i + 1}/${DEMO_SCRIPT.length} — Translated`;
            }, totalDelay + 600));

            totalDelay += line.delay;
        });

        // Auto-stop
        timeouts.push(setTimeout(() => {
            if (playing) {
                status.textContent = `✓ Complete — ${DEMO_SCRIPT.length} segments processed`;
                meter.classList.remove('active');
                btn.classList.remove('playing');
                btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>';
                playing = false;
            }
        }, totalDelay + 800));
    }

    function stopDemo() {
        playing = false;
        timeouts.forEach(clearTimeout);
        timeouts = [];
        btn.classList.remove('playing');
        btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>';
        status.textContent = 'Click play to start demo';
        meter.classList.remove('active');
    }

    function addSegment(vi, en, isFinal, idx) {
        let seg = transcript.querySelector(`[data-idx="${idx}"]`);
        if (!seg) {
            const empty = transcript.querySelector('.demo-empty');
            if (empty) empty.remove();
            seg = document.createElement('div');
            seg.className = 'demo-seg';
            seg.dataset.idx = idx;
            transcript.appendChild(seg);
        }

        if (isFinal) {
            seg.innerHTML = `
                <div class="src">${vi}<span class="pipeline-tag">Faster-Whisper → confidence gate</span></div>
                <div class="tgt">${en}<span class="pipeline-tag">OPUS-MT VI↔EN · beam 1</span></div>
            `;
        } else {
            seg.innerHTML = `<div class="src partial">${vi}...</div>`;
        }
        transcript.scrollTop = transcript.scrollHeight;
    }
})();
