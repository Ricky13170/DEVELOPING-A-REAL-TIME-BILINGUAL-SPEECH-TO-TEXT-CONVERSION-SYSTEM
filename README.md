# TheDuo Edge Interpreter

CPU-only Vietnamese ↔ English speech transcription and translation for frontline communication.

## Lightweight pipeline

```text
Microphone → WebRTC/WebSocket → energy VAD
           → Faster-Whisper tiny INT8 (CPU)
           → OPUS-MT VI↔EN beam 1 (CPU, lazy load)
           → bilingual transcript
```

The local runtime never selects CUDA. BARTpho, WhisperX, Pyannote, DeepFilterNet, NLLB, repeated ASR retries, and second-pass translation are not in the realtime path.

## Run locally

Requires Python 3.11:

```powershell
uv python install 3.11
uv sync --locked --extra webrtc
uv run python main.py
```

`main.py` is the only application entrypoint; Docker uses the same file.

Open `http://localhost:8000`. The first run downloads Whisper Tiny and the VI→EN OPUS-MT checkpoint. The EN→VI checkpoint is downloaded only after switching direction.

For better ASR accuracy, with higher CPU latency:

```powershell
uv run python main.py --whisper-model base
```

WebRTC is attempted only for local direct connections. If `aiortc` or ICE is unavailable, audio automatically uses WebSocket.

## Docker CPU

```powershell
docker compose up --build
```

Set `INSTALL_WEBRTC=1` before building if the container needs WebRTC. `.dockerignore` excludes local environments and model caches.

## Defaults

```dotenv
WHISPER_MODEL=tiny
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=int8
CPU_THREADS=2
TRANSLATION_MODEL_VI_EN=Helsinki-NLP/opus-mt-vi-en
TRANSLATION_MODEL_EN_VI=Helsinki-NLP/opus-mt-en-vi
TRANSLATION_DEVICE=cpu
ENABLE_PARTIAL_TRANSCRIPTS=false
MAX_HALLUCINATION_RETRIES=0
ENABLE_GROQ=false
```

Both OPUS-MT checkpoints are Apache-2.0. Groq remains an optional cloud extra and should stay disabled for offline tests.

## Project structure and smoke test

The backend uses only two feature packages: `speech` and `realtime`. See
[docs/architecture.md](docs/architecture.md) for the ownership rules and the
folder-structure rationale.

```powershell
uv run python -m unittest discover -s tests -v
```

## OneVoice proposal

The final device must include offline ASR, translation, and TTS. This repository currently implements ASR + text translation; offline TTS, real noisy-speech benchmarks, peak RAM/power measurements, and Qualcomm/QNN deployment remain proposal milestones.

See [proposal/context.md](proposal/context.md) for the rubric, architecture
notes, measurement checklist, and verified official links.
