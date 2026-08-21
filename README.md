# TheDuo Edge Interpreter

Vietnamese ↔ English speech transcription and translation for frontline communication.

## Lightweight pipeline

```text
Microphone → WebRTC/WebSocket → energy VAD
           → Faster-Whisper medium INT8
           → OPUS-MT VI↔EN beam 1 (CPU, lazy load)
           → bilingual transcript
```

The default local dependency lock and Docker image are CPU-only. Modal supplies the T4 CUDA runtime remotely. BARTpho, WhisperX, Pyannote, DeepFilterNet, NLLB, repeated ASR retries, and second-pass translation are not in the realtime path.

## Test on Modal (recommended)

This keeps model installation and inference off the local machine:

```powershell
uvx modal setup
uvx modal serve main.py
```

Open the HTTPS URL printed by Modal. The remote profile uses Faster-Whisper Medium on one T4; OPUS-MT runs on the container CPU. Modal serves browser audio through the WebSocket fallback because direct WebRTC media requires a TURN/UDP deployment.

For a persistent URL after the smoke test:

```powershell
uvx modal deploy main.py
```

`main.py` remains the only application entrypoint. Modal is supplied by `uvx`, so it is not added to the project lockfile or model runtime.

## Configure once

Edit only `backend/config.py`. It is the single source for local, Docker, Modal, model, audio, segmentation, translation, and UI runtime values. The project does not read `.env` and command-line flags cannot override the configuration.

Keep `GROQ_API_KEY` empty unless the optional Groq feature is intentionally enabled. Never commit a real secret.

## Run locally

Requires Python 3.11:

```powershell
uv python install 3.11
uv sync --locked --extra webrtc
uv run python main.py
```

`main.py` is the only application entrypoint; Docker uses the same file.

Open `http://localhost:8000`. The first run downloads Whisper Medium and the VI→EN OPUS-MT checkpoint. The EN→VI checkpoint is downloaded only after switching direction.

For the largest accuracy profile, change this one line in `backend/config.py`:

```python
WHISPER_MODEL = validate_whisper_model("large-v3")
```

WebRTC is attempted only for local direct connections. If `aiortc` or ICE is unavailable, audio automatically uses WebSocket.

## Docker CPU

```powershell
docker compose up --build
```

The Docker image uses the same `backend/config.py`. `.dockerignore` excludes local environments and model caches.

## Defaults

```python
WHISPER_MODEL = validate_whisper_model("medium")
ASR_DEVICE = "cpu"
ASR_COMPUTE_TYPE = "int8"
MODAL_GPU = "T4"
MODAL_WHISPER_MODEL = validate_whisper_model("medium")
MODAL_ASR_COMPUTE_TYPE = "int8_float16"
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
