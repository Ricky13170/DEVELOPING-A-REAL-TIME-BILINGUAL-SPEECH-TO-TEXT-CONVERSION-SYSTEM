# Project Architecture

The project uses a small feature-based layout. It follows the five practical
principles in [The Ultimate Folder Structure Guide](https://medium.com/@boubkerelmaayouf/the-ultimate-folder-structure-guide-for-any-project-any-language-6bb5b8fbd5b3):
predictability, separation of concerns, scalability, consistency, and no
premature folders.

The guide's universal tree is a starting point, not a requirement to create
every directory. Here, `backend/` and `frontend/` already make the two source
roots explicit, so wrapping them in another `src/` level would add path churn
without adding a boundary.

```text
.
├── backend/
│   ├── config.py                 # all environment/runtime settings
│   ├── translation.py            # local VI↔EN translation feature
│   ├── groq_service.py            # optional cloud-only integration
│   ├── web_app.py                 # HTTP/WebSocket application factory
│   ├── speech/                    # audio-to-text feature
│   │   ├── asr.py
│   │   ├── audio_normalizer.py
│   │   ├── vad.py
│   │   ├── speech_segment_buffer.py
│   │   ├── local_agreement.py
│   │   └── hallucination_filter.py
│   └── realtime/                  # live-session orchestration and transport
│       ├── session.py
│       └── webrtc.py
├── frontend/                      # browser UI, one module per UI feature
├── tests/                         # fast tests that do not download models
├── docs/                          # architecture + public project page
├── proposal/                      # OneVoice submission working material
└── main.py                        # one local/Docker/Modal composition root
```

## Dependency direction

```text
main.py
  ├────────────→ web_app.py ──→ realtime/webrtc.py
  └────────────→ realtime/session.py
                        ├───────→ realtime/webrtc.py
                        ├───────→ speech/*
                        ├───────→ translation.py
                        └───────→ groq_service.py (optional)

All backend modules may read config.py.
Speech and translation never import the web or deployment entrypoints.
The web app receives the session service by injection and never imports it.
```

## Where new code goes

- Speech preprocessing, VAD, ASR, and text stabilization: `backend/speech/`.
- Streaming state, queues, WebSocket/WebRTC coordination: `backend/realtime/`.
- VI↔EN model changes: `backend/translation.py`.
- HTTP endpoints only: `backend/web_app.py`.
- Browser behavior: the closest existing module under `frontend/js/`.

Add another folder only after a feature needs at least two cohesive modules.

## Folders intentionally not created

- `core/`, `modules/`, `services/`, `utils/`, and `helpers/`: there is no shared
  concern large enough to justify them yet.
- `public/`: `frontend/` is already the runtime static root and `docs/` is the
  separate GitHub Pages root.
- `scripts/`: the single executable entrypoint is clearer at the repository root.

This is the guide's "start simple, scale when it hurts" rule applied to the
actual project rather than copying its largest example.

## Root policy

The remaining root files stay there because tools and contributors expect them
there:

- `README.md`, `pyproject.toml`, `uv.lock`, and `.python-version`
  describe and reproduce the application environment.
- `main.py` is the single composition root used by direct, Docker, and Modal
  execution. `backend/config.py` is the only user-editable runtime
  configuration source; no environment or CLI override is applied.
- `Dockerfile`, `docker-compose.yml`, and `.dockerignore` form the conventional
  root Docker build context.

Generated environments and caches (`venv/`, `.venv/`, `__pycache__/`, model
weights, and legacy local `.env`) are ignored rather than reorganized into the source
tree.
