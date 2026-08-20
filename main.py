"""Run the CPU-only bilingual speech service.

Examples:
    python main.py
    python main.py --whisper-model base
    python main.py --port 8080
"""

import argparse
import asyncio
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the bilingual ASR server locally on CPU"
    )
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument(
        "--whisper-model",
        default=None,
        help="Faster-Whisper model size (default: tiny)",
    )
    parser.add_argument(
        "--enable-groq",
        action="store_true",
        help="Enable optional cloud summary/context features",
    )
    parser.add_argument(
        "--cache-dir",
        default="./model_cache",
        help="Directory used for downloaded model caches",
    )
    return parser.parse_args()


def apply_config(args):
    """Force CPU settings before importing model modules."""

    import backend.config as cfg

    whisper_override = args.whisper_model or os.getenv("WHISPER_MODEL")
    cfg.ASR_DEVICE = "cpu"
    cfg.TRANSLATION_DEVICE = "cpu"
    cfg.ASR_COMPUTE_TYPE = "int8"
    cfg.WHISPER_MODEL = whisper_override or "tiny"
    os.environ.setdefault("OMP_NUM_THREADS", str(cfg.CPU_THREADS))
    os.environ.setdefault("MKL_NUM_THREADS", str(cfg.CPU_THREADS))

    groq_requested = args.enable_groq or os.getenv("ENABLE_GROQ", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    cfg.ENABLE_GROQ = bool(groq_requested and os.getenv("GROQ_API_KEY"))
    cfg.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "") if cfg.ENABLE_GROQ else ""
    return cfg


def main():
    args = parse_args()
    cfg = apply_config(args)

    os.environ.setdefault("HF_HOME", os.path.join(args.cache_dir, "huggingface"))
    os.makedirs(args.cache_dir, exist_ok=True)

    print("=" * 60)
    print("  TheDuo Edge - CPU Server")
    print("=" * 60)
    print("  Device  : CPU only")
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
        deployment="local",
        compute_label="CPU only",
    )

    print(f"Server running at http://localhost:{args.port}")
    print("Open this URL in your browser to start transcribing.\n")

    import uvicorn

    uvicorn.run(web_app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
