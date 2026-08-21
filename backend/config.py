"""Runtime configuration with lightweight, environment-overridable defaults."""

import os
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _text(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


SUPPORTED_WHISPER_MODELS = (
    "medium",
    "large-v1",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
    "turbo",
)


def validate_whisper_model(model_name: str) -> str:
    normalized = model_name.strip().lower()
    if normalized not in SUPPORTED_WHISPER_MODELS:
        allowed = ", ".join(SUPPORTED_WHISPER_MODELS)
        raise ValueError(
            f"WHISPER_MODEL must be medium or larger. Allowed values: {allowed}"
        )
    return normalized


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Paths shared by every runtime.
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", str(PROJECT_ROOT / "model_cache"))
HF_HOME = os.getenv("HF_HOME", str(Path(MODEL_CACHE_DIR) / "huggingface"))
WEB_HOST = _text("WEB_HOST", "0.0.0.0")
WEB_PORT = _int("WEB_PORT", 8000)
LOCAL_DEPLOYMENT_NAME = _text("LOCAL_DEPLOYMENT_NAME", "local")
LOCAL_COMPUTE_LABEL = _text("LOCAL_COMPUTE_LABEL", "CPU")


# Local defaults are CPU-only. The Modal composition root overrides these
# through image environment variables before any model module is imported.
WHISPER_MODEL = validate_whisper_model(_text("WHISPER_MODEL", "medium"))
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "vi") or None
ASR_DEVICE = _text("ASR_DEVICE", "cpu")
ASR_COMPUTE_TYPE = _text("ASR_COMPUTE_TYPE", "int8")
CPU_THREADS = max(1, _int("CPU_THREADS", 2))
ASR_BEAM_SIZE = _int("ASR_BEAM_SIZE", 1)
ASR_WORD_TIMESTAMPS = _bool("ASR_WORD_TIMESTAMPS", False)

# NMT: small Apache-2.0 Marian checkpoints, loaded lazily per direction.
TRANSLATION_MODEL_VI_EN = os.getenv(
    "TRANSLATION_MODEL_VI_EN",
    "Helsinki-NLP/opus-mt-vi-en",
)
TRANSLATION_MODEL_EN_VI = os.getenv(
    "TRANSLATION_MODEL_EN_VI",
    "Helsinki-NLP/opus-mt-en-vi",
)
TRANSLATION_SRC_LANG = os.getenv("TRANSLATION_SRC_LANG", "vie_Latn")
TRANSLATION_TGT_LANG = os.getenv("TRANSLATION_TGT_LANG", "eng_Latn")
TRANSLATION_DEVICE = _text("TRANSLATION_DEVICE", "cpu")

# Audio / adaptive energy VAD. No neural VAD model is loaded per session.
SAMPLE_RATE = _int("SAMPLE_RATE", 16000)
AUDIO_SEND_INTERVAL_MS = _int("AUDIO_SEND_INTERVAL_MS", 250)
VAD_BASE_THRESHOLD = _float("VAD_BASE_THRESHOLD", 0.012)
VAD_ALPHA = _float("VAD_ALPHA", 0.05)
VAD_MIN_NOISE = _float("VAD_MIN_NOISE", 0.001)
VAD_MAX_NOISE = _float("VAD_MAX_NOISE", 0.05)
VAD_INITIAL_NOISE = _float("VAD_INITIAL_NOISE", 0.003)
VAD_SPEECH_PROB_THRESHOLD = _float("VAD_SPEECH_PROB_THRESHOLD", 0.5)

# Audio normalization.
NORMALIZER_TARGET_DB = _float("NORMALIZER_TARGET_DB", -20.0)
NORMALIZER_MIN_GAIN = _float("NORMALIZER_MIN_GAIN", 0.3)
NORMALIZER_MAX_GAIN = _float("NORMALIZER_MAX_GAIN", 5.0)
NORMALIZER_NOISE_FLOOR = _float("NORMALIZER_NOISE_FLOOR", 0.001)
NORMALIZER_HIGH_PASS_HZ = _int("NORMALIZER_HIGH_PASS_HZ", 80)
NORMALIZER_RMS_THRESHOLD = _float("NORMALIZER_RMS_THRESHOLD", 0.005)
NORMALIZER_SOFT_CLIP_THRESHOLD = _float("NORMALIZER_SOFT_CLIP_THRESHOLD", 0.95)
NORMALIZER_MIN_AUDIO_SEC = _float("NORMALIZER_MIN_AUDIO_SEC", 0.5)
NORMALIZER_HISTORY_SIZE = _int("NORMALIZER_HISTORY_SIZE", 50)
NORMALIZER_UPDATE_INTERVAL = _int("NORMALIZER_UPDATE_INTERVAL", 10)

# Streaming segmentation.
MAX_SEGMENT_SEC = _float("MAX_SEGMENT_SEC", 3.0)
OVERLAP_SEC = _float("OVERLAP_SEC", 0.35)
SILENCE_LIMIT = _float("SILENCE_LIMIT", 0.45)
MIN_DECODE_SEC = _float("MIN_DECODE_SEC", 0.8)
PROB_DROP_THRESHOLD = _float("PROB_DROP_THRESHOLD", 0.4)
CONTINUOUS_SPEECH_PARTIAL_SEC = _float("CONTINUOUS_SPEECH_PARTIAL_SEC", 1.5)
PRE_SPEECH_SEC = _float("PRE_SPEECH_SEC", 0.25)
ENABLE_PARTIAL_TRANSCRIPTS = _bool("ENABLE_PARTIAL_TRANSCRIPTS", False)
SEGMENT_MIN_EMIT_SEC = _float("SEGMENT_MIN_EMIT_SEC", 1.0)
SEGMENT_PREVIOUS_PROB_THRESHOLD = _float("SEGMENT_PREVIOUS_PROB_THRESHOLD", 0.6)
AUDIO_QUEUE_MAX_CHUNKS = _int("AUDIO_QUEUE_MAX_CHUNKS", 128)
AUDIO_DRAIN_TIMEOUT_SEC = _float("AUDIO_DRAIN_TIMEOUT_SEC", 5.0)
TRANSLATION_DRAIN_TIMEOUT_SEC = _float("TRANSLATION_DRAIN_TIMEOUT_SEC", 8.0)
PARTIAL_FINALIZE_TIMEOUT_SEC = _float("PARTIAL_FINALIZE_TIMEOUT_SEC", 3.0)
WEBRTC_EMIT_SEC = _float("WEBRTC_EMIT_SEC", 0.16)

# Lightweight stabilisation / confidence gate.
AGREEMENT_N = _int("AGREEMENT_N", 2)
HALLUCINATION_HISTORY_SIZE = _int("HALLUCINATION_HISTORY_SIZE", 5)
MAX_HALLUCINATION_RETRIES = _int("MAX_HALLUCINATION_RETRIES", 0)
OVERLAP_THRESHOLD_DIFF = _float("OVERLAP_THRESHOLD_DIFF", 0.1)
HALLUCINATION_QUIET_RMS = _float("HALLUCINATION_QUIET_RMS", 0.003)
HALLUCINATION_LONG_TEXT_WORDS = _int("HALLUCINATION_LONG_TEXT_WORDS", 6)
HALLUCINATION_RETRY_TEMPERATURES = (0.2, 0.4, 0.6)

# Inference options.
ASR_NUM_WORKERS = _int("ASR_NUM_WORKERS", 1)
ASR_BEST_OF = _int("ASR_BEST_OF", 1)
ASR_TEMPERATURE = _float("ASR_TEMPERATURE", 0.0)
ASR_REPETITION_PENALTY = _float("ASR_REPETITION_PENALTY", 1.15)
ASR_NO_SPEECH_THRESHOLD = _float("ASR_NO_SPEECH_THRESHOLD", 0.6)
ASR_COMPRESSION_RATIO_THRESHOLD = _float("ASR_COMPRESSION_RATIO_THRESHOLD", 2.4)
TRANSLATION_MAX_INPUT_LENGTH = _int("TRANSLATION_MAX_INPUT_LENGTH", 256)
TRANSLATION_MAX_OUTPUT_LENGTH = _int("TRANSLATION_MAX_OUTPUT_LENGTH", 256)
TRANSLATION_NUM_BEAMS = _int("TRANSLATION_NUM_BEAMS", 1)

# Cloud-only convenience features are opt-in and excluded from the edge path.
ENABLE_GROQ = _bool("ENABLE_GROQ", False)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT = _int("GROQ_TIMEOUT", 10)
AUTO_SUMMARY_MIN_DURATION = _int("AUTO_SUMMARY_MIN_DURATION", 0)
GROQ_TEMPERATURE = _float("GROQ_TEMPERATURE", 0.3)
GROQ_MAX_TOKENS = _int("GROQ_MAX_TOKENS", 1024)

# Modal is only a remote smoke-test runtime. Keeping its knobs here means
# main.py, documentation, and deployment code do not each invent defaults.
MODAL_APP_NAME = _text("MODAL_APP_NAME", "theduo-edge-interpreter")
MODAL_GPU = _text("MODAL_GPU", "T4")
MODAL_MEMORY_MB = _int("MODAL_MEMORY_MB", 12288)
MODAL_TIMEOUT_SECONDS = _int("MODAL_TIMEOUT_SECONDS", 900)
MODAL_SCALEDOWN_SECONDS = _int("MODAL_SCALEDOWN_SECONDS", 60)
MODAL_MAX_INPUTS = _int("MODAL_MAX_INPUTS", 4)
MODAL_MAX_CONTAINERS = _int("MODAL_MAX_CONTAINERS", 1)
MODAL_DEPLOYMENT_NAME = _text("MODAL_DEPLOYMENT_NAME", "modal")
MODAL_COMPUTE_LABEL = _text("MODAL_COMPUTE_LABEL", f"Modal {MODAL_GPU}")
MODAL_ENABLE_GROQ = _bool("MODAL_ENABLE_GROQ", False)
MODAL_MODEL_CACHE_VOLUME = os.getenv(
    "MODAL_MODEL_CACHE_VOLUME",
    "theduo-model-cache",
)
MODAL_WHISPER_MODEL = validate_whisper_model(
    _text("MODAL_WHISPER_MODEL", "medium")
)
MODAL_ASR_DEVICE = _text("MODAL_ASR_DEVICE", "cuda")
MODAL_ASR_COMPUTE_TYPE = _text("MODAL_ASR_COMPUTE_TYPE", "int8_float16")
MODAL_TRANSLATION_DEVICE = _text("MODAL_TRANSLATION_DEVICE", "cpu")
MODAL_MODEL_CACHE_DIR = _text("MODAL_MODEL_CACHE_DIR", "/cache")
MODAL_HF_HOME = _text("MODAL_HF_HOME", "/cache/huggingface")
MODAL_VOLUME_MOUNT_PATH = _text("MODAL_VOLUME_MOUNT_PATH", "/cache")
MODAL_REMOTE_ROOT = _text("MODAL_REMOTE_ROOT", "/root")
MODAL_BASE_IMAGE = _text(
    "MODAL_BASE_IMAGE",
    "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04",
)
MODAL_PYTHON_VERSION = _text("MODAL_PYTHON_VERSION", "3.11")
MODAL_TORCH_INDEX_URL = _text(
    "MODAL_TORCH_INDEX_URL",
    "https://download.pytorch.org/whl/cpu",
)
MODAL_APT_PACKAGES = ("libgomp1",)


def _base_requirements() -> tuple[str, ...]:
    requirements_path = PROJECT_ROOT / "requirements.txt"
    if not requirements_path.is_file():
        return ()
    return tuple(
        line.strip()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


_RUNTIME_REQUIREMENTS = _base_requirements()
MODAL_TORCH_REQUIREMENT = next(
    (item for item in _RUNTIME_REQUIREMENTS if item.lower().startswith("torch")),
    "torch==2.8.0",
)
MODAL_RUNTIME_REQUIREMENTS = tuple(
    item
    for item in _RUNTIME_REQUIREMENTS
    if not item.lower().startswith("torch")
)


def modal_runtime_environment() -> dict[str, str]:
    """Return the complete environment injected into the Modal image."""

    return {
        "WHISPER_MODEL": MODAL_WHISPER_MODEL,
        "WHISPER_LANGUAGE": WHISPER_LANGUAGE or "",
        "ASR_DEVICE": MODAL_ASR_DEVICE,
        "ASR_COMPUTE_TYPE": MODAL_ASR_COMPUTE_TYPE,
        "ASR_BEAM_SIZE": str(ASR_BEAM_SIZE),
        "ASR_WORD_TIMESTAMPS": str(ASR_WORD_TIMESTAMPS).lower(),
        "ASR_NUM_WORKERS": str(ASR_NUM_WORKERS),
        "ASR_BEST_OF": str(ASR_BEST_OF),
        "ASR_TEMPERATURE": str(ASR_TEMPERATURE),
        "ASR_REPETITION_PENALTY": str(ASR_REPETITION_PENALTY),
        "ASR_NO_SPEECH_THRESHOLD": str(ASR_NO_SPEECH_THRESHOLD),
        "ASR_COMPRESSION_RATIO_THRESHOLD": str(ASR_COMPRESSION_RATIO_THRESHOLD),
        "CPU_THREADS": str(CPU_THREADS),
        "TRANSLATION_MODEL_VI_EN": TRANSLATION_MODEL_VI_EN,
        "TRANSLATION_MODEL_EN_VI": TRANSLATION_MODEL_EN_VI,
        "TRANSLATION_SRC_LANG": TRANSLATION_SRC_LANG,
        "TRANSLATION_TGT_LANG": TRANSLATION_TGT_LANG,
        "TRANSLATION_DEVICE": MODAL_TRANSLATION_DEVICE,
        "TRANSLATION_MAX_INPUT_LENGTH": str(TRANSLATION_MAX_INPUT_LENGTH),
        "TRANSLATION_MAX_OUTPUT_LENGTH": str(TRANSLATION_MAX_OUTPUT_LENGTH),
        "TRANSLATION_NUM_BEAMS": str(TRANSLATION_NUM_BEAMS),
        "SAMPLE_RATE": str(SAMPLE_RATE),
        "AUDIO_SEND_INTERVAL_MS": str(AUDIO_SEND_INTERVAL_MS),
        "VAD_BASE_THRESHOLD": str(VAD_BASE_THRESHOLD),
        "VAD_ALPHA": str(VAD_ALPHA),
        "VAD_MIN_NOISE": str(VAD_MIN_NOISE),
        "VAD_MAX_NOISE": str(VAD_MAX_NOISE),
        "VAD_INITIAL_NOISE": str(VAD_INITIAL_NOISE),
        "VAD_SPEECH_PROB_THRESHOLD": str(VAD_SPEECH_PROB_THRESHOLD),
        "NORMALIZER_TARGET_DB": str(NORMALIZER_TARGET_DB),
        "NORMALIZER_MIN_GAIN": str(NORMALIZER_MIN_GAIN),
        "NORMALIZER_MAX_GAIN": str(NORMALIZER_MAX_GAIN),
        "NORMALIZER_NOISE_FLOOR": str(NORMALIZER_NOISE_FLOOR),
        "NORMALIZER_HIGH_PASS_HZ": str(NORMALIZER_HIGH_PASS_HZ),
        "NORMALIZER_RMS_THRESHOLD": str(NORMALIZER_RMS_THRESHOLD),
        "NORMALIZER_SOFT_CLIP_THRESHOLD": str(NORMALIZER_SOFT_CLIP_THRESHOLD),
        "NORMALIZER_MIN_AUDIO_SEC": str(NORMALIZER_MIN_AUDIO_SEC),
        "NORMALIZER_HISTORY_SIZE": str(NORMALIZER_HISTORY_SIZE),
        "NORMALIZER_UPDATE_INTERVAL": str(NORMALIZER_UPDATE_INTERVAL),
        "MAX_SEGMENT_SEC": str(MAX_SEGMENT_SEC),
        "OVERLAP_SEC": str(OVERLAP_SEC),
        "SILENCE_LIMIT": str(SILENCE_LIMIT),
        "MIN_DECODE_SEC": str(MIN_DECODE_SEC),
        "PROB_DROP_THRESHOLD": str(PROB_DROP_THRESHOLD),
        "CONTINUOUS_SPEECH_PARTIAL_SEC": str(CONTINUOUS_SPEECH_PARTIAL_SEC),
        "PRE_SPEECH_SEC": str(PRE_SPEECH_SEC),
        "ENABLE_GROQ": str(MODAL_ENABLE_GROQ).lower(),
        "ENABLE_PARTIAL_TRANSCRIPTS": str(ENABLE_PARTIAL_TRANSCRIPTS).lower(),
        "SEGMENT_MIN_EMIT_SEC": str(SEGMENT_MIN_EMIT_SEC),
        "SEGMENT_PREVIOUS_PROB_THRESHOLD": str(SEGMENT_PREVIOUS_PROB_THRESHOLD),
        "AGREEMENT_N": str(AGREEMENT_N),
        "HALLUCINATION_HISTORY_SIZE": str(HALLUCINATION_HISTORY_SIZE),
        "MAX_HALLUCINATION_RETRIES": str(MAX_HALLUCINATION_RETRIES),
        "OVERLAP_THRESHOLD_DIFF": str(OVERLAP_THRESHOLD_DIFF),
        "HALLUCINATION_QUIET_RMS": str(HALLUCINATION_QUIET_RMS),
        "HALLUCINATION_LONG_TEXT_WORDS": str(HALLUCINATION_LONG_TEXT_WORDS),
        "AUDIO_QUEUE_MAX_CHUNKS": str(AUDIO_QUEUE_MAX_CHUNKS),
        "AUDIO_DRAIN_TIMEOUT_SEC": str(AUDIO_DRAIN_TIMEOUT_SEC),
        "TRANSLATION_DRAIN_TIMEOUT_SEC": str(TRANSLATION_DRAIN_TIMEOUT_SEC),
        "PARTIAL_FINALIZE_TIMEOUT_SEC": str(PARTIAL_FINALIZE_TIMEOUT_SEC),
        "WEBRTC_EMIT_SEC": str(WEBRTC_EMIT_SEC),
        "MODEL_CACHE_DIR": MODAL_MODEL_CACHE_DIR,
        "HF_HOME": MODAL_HF_HOME,
        "TOKENIZERS_PARALLELISM": "false",
    }
