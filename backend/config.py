"""Runtime configuration with lightweight, environment-overridable defaults."""

import os


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


# The only runtime profile is CPU-only, so CUDA is never selected implicitly.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "vi") or None
ASR_DEVICE = os.getenv("ASR_DEVICE", "cpu")
ASR_COMPUTE_TYPE = os.getenv("ASR_COMPUTE_TYPE", "int8")
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
TRANSLATION_DEVICE = os.getenv("TRANSLATION_DEVICE", "cpu")

# Audio / adaptive energy VAD. No neural VAD model is loaded per session.
SAMPLE_RATE = 16000
VAD_BASE_THRESHOLD = _float("VAD_BASE_THRESHOLD", 0.012)
VAD_ALPHA = _float("VAD_ALPHA", 0.05)
VAD_MIN_NOISE = _float("VAD_MIN_NOISE", 0.001)
VAD_MAX_NOISE = _float("VAD_MAX_NOISE", 0.05)

# Streaming segmentation.
MAX_SEGMENT_SEC = _float("MAX_SEGMENT_SEC", 3.0)
OVERLAP_SEC = _float("OVERLAP_SEC", 0.35)
SILENCE_LIMIT = _float("SILENCE_LIMIT", 0.45)
MIN_DECODE_SEC = _float("MIN_DECODE_SEC", 0.8)
PROB_DROP_THRESHOLD = _float("PROB_DROP_THRESHOLD", 0.4)
CONTINUOUS_SPEECH_PARTIAL_SEC = _float("CONTINUOUS_SPEECH_PARTIAL_SEC", 1.5)
PRE_SPEECH_SEC = _float("PRE_SPEECH_SEC", 0.25)
ENABLE_PARTIAL_TRANSCRIPTS = _bool("ENABLE_PARTIAL_TRANSCRIPTS", False)

# Lightweight stabilisation / confidence gate.
AGREEMENT_N = _int("AGREEMENT_N", 2)
HALLUCINATION_HISTORY_SIZE = _int("HALLUCINATION_HISTORY_SIZE", 5)
MAX_HALLUCINATION_RETRIES = _int("MAX_HALLUCINATION_RETRIES", 0)
OVERLAP_THRESHOLD_DIFF = _float("OVERLAP_THRESHOLD_DIFF", 0.1)

# Cloud-only convenience features are opt-in and excluded from the edge path.
ENABLE_GROQ = _bool("ENABLE_GROQ", False)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "") if ENABLE_GROQ else ""
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_TIMEOUT = _int("GROQ_TIMEOUT", 10)
AUTO_SUMMARY_MIN_DURATION = _int("AUTO_SUMMARY_MIN_DURATION", 0)
