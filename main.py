"""Run the bilingual speech service locally or on Modal.

Examples:
    python main.py
    python main.py --whisper-model large-v3
    modal serve main.py
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import backend.config as cfg


PROJECT_ROOT = Path(__file__).resolve().parent


# Modal is deliberately not a project dependency. ``uvx modal serve main.py``
# supplies the CLI locally while all model dependencies and inference run in
# the remote container.
try:
    import modal
except ImportError:
    modal = None


if modal is not None:
    modal_image = (
        modal.Image.from_registry(
            cfg.MODAL_BASE_IMAGE,
            add_python=cfg.MODAL_PYTHON_VERSION,
        )
        .apt_install(*cfg.MODAL_APT_PACKAGES)
        .uv_pip_install(
            cfg.MODAL_TORCH_REQUIREMENT,
            index_url=cfg.MODAL_TORCH_INDEX_URL,
        )
        .uv_pip_install(*cfg.MODAL_RUNTIME_REQUIREMENTS)
        .env(cfg.modal_runtime_environment())
        .add_local_dir(
            PROJECT_ROOT / "backend",
            remote_path=f"{cfg.MODAL_REMOTE_ROOT}/backend",
        )
        .add_local_dir(
            PROJECT_ROOT / "frontend",
            remote_path=f"{cfg.MODAL_REMOTE_ROOT}/frontend",
        )
    )

    app = modal.App(cfg.MODAL_APP_NAME)
    model_cache = modal.Volume.from_name(
        cfg.MODAL_MODEL_CACHE_VOLUME,
        create_if_missing=True,
    )

    @app.cls(
        image=modal_image,
        gpu=cfg.MODAL_GPU,
        memory=cfg.MODAL_MEMORY_MB,
        timeout=cfg.MODAL_TIMEOUT_SECONDS,
        startup_timeout=cfg.MODAL_TIMEOUT_SECONDS,
        scaledown_window=cfg.MODAL_SCALEDOWN_SECONDS,
        max_containers=cfg.MODAL_MAX_CONTAINERS,
        volumes={cfg.MODAL_VOLUME_MOUNT_PATH: model_cache},
    )
    @modal.concurrent(max_inputs=cfg.MODAL_MAX_INPUTS)
    class ModalRuntime:
        """One warm T4 container shared by the ASGI and WebSocket routes."""

        @modal.enter()
        def load_models(self):
            if cfg.MODAL_REMOTE_ROOT not in sys.path:
                sys.path.insert(0, cfg.MODAL_REMOTE_ROOT)

            from backend.realtime.session import ASRService

            self.service = ASRService()
            asyncio.run(self.service.init())

        @modal.asgi_app()
        def web(self):
            from backend.web_app import create_web_app

            return create_web_app(
                service=self.service,
                frontend_dir=f"{cfg.MODAL_REMOTE_ROOT}/frontend",
                deployment=cfg.MODAL_DEPLOYMENT_NAME,
                compute_label=cfg.MODAL_COMPUTE_LABEL,
            )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the bilingual ASR server locally on CPU"
    )
    parser.add_argument("--port", type=int, default=cfg.WEB_PORT, help="Server port")
    parser.add_argument("--host", default=cfg.WEB_HOST, help="Server host")
    parser.add_argument(
        "--whisper-model",
        default=None,
        choices=cfg.SUPPORTED_WHISPER_MODELS,
        help=f"Faster-Whisper model (default: {cfg.WHISPER_MODEL})",
    )
    parser.add_argument(
        "--enable-groq",
        action="store_true",
        help="Enable optional cloud summary/context features",
    )
    parser.add_argument(
        "--cache-dir",
        default=cfg.MODEL_CACHE_DIR,
        help="Directory used for downloaded model caches",
    )
    return parser.parse_args()


def apply_config(args):
    """Apply CLI overrides to the centralized configuration."""

    whisper_override = args.whisper_model or cfg.WHISPER_MODEL
    cfg.WHISPER_MODEL = cfg.validate_whisper_model(whisper_override)
    os.environ.setdefault("OMP_NUM_THREADS", str(cfg.CPU_THREADS))
    os.environ.setdefault("MKL_NUM_THREADS", str(cfg.CPU_THREADS))

    groq_requested = args.enable_groq or cfg.ENABLE_GROQ
    cfg.ENABLE_GROQ = bool(groq_requested and cfg.GROQ_API_KEY)
    cfg.GROQ_API_KEY = cfg.GROQ_API_KEY if cfg.ENABLE_GROQ else ""
    return cfg


def main():
    args = parse_args()
    cfg = apply_config(args)

    cfg.MODEL_CACHE_DIR = os.path.abspath(args.cache_dir)
    cfg.HF_HOME = os.path.join(cfg.MODEL_CACHE_DIR, "huggingface")
    os.environ.setdefault("HF_HOME", cfg.HF_HOME)
    os.makedirs(args.cache_dir, exist_ok=True)

    print("=" * 60)
    print("  TheDuo Edge Server")
    print("=" * 60)
    print(f"  Device  : {cfg.ASR_DEVICE}")
    print(f"  Whisper : {cfg.WHISPER_MODEL}")
    print("  NMT     : OPUS-MT vi-en / en-vi (lazy)")
    print(f"  ASR type: {cfg.ASR_COMPUTE_TYPE}")
    print(f"  Groq    : {'ON (cloud extra)' if cfg.ENABLE_GROQ else 'OFF (offline core)'}")
    print(f"  Cache   : {args.cache_dir}")
    print("=" * 60)

    print("\nLoading models (first run may take a few minutes)...")
    from backend.realtime.session import ASRService

    service = ASRService()
    asyncio.run(service.init())
    print("Models loaded.\n")

    from backend.web_app import create_web_app

    web_app = create_web_app(
        service=service,
        frontend_dir=os.path.join(os.path.dirname(__file__), "frontend"),
        deployment=cfg.LOCAL_DEPLOYMENT_NAME,
        compute_label=cfg.LOCAL_COMPUTE_LABEL,
    )

    print(f"Server running at http://localhost:{args.port}")
    print("Open this URL in your browser to start transcribing.\n")

    import uvicorn

    uvicorn.run(web_app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
