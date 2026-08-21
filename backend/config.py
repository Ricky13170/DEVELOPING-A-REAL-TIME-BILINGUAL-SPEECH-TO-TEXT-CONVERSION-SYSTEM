"""The single source of truth for every runtime and deployment setting."""

from pathlib import Path

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
MODEL_CACHE_DIR = str(PROJECT_ROOT / "model_cache")
HF_HOME = str(Path(MODEL_CACHE_DIR) / "huggingface")
WEB_HOST = "0.0.0.0"
WEB_PORT = 8000
LOCAL_DEPLOYMENT_NAME = "local"
LOCAL_COMPUTE_LABEL = "CPU"
TOKENIZERS_PARALLELISM = False


# Local defaults are CPU-only. The Modal composition root overrides these
# through image environment variables before any model module is imported.
WHISPER_MODEL = validate_whisper_model("medium")
WHISPER_LANGUAGE = "vi"
ASR_DEVICE = "cpu"
ASR_COMPUTE_TYPE = "int8"
CPU_THREADS = 2
ASR_BEAM_SIZE = 1
ASR_WORD_TIMESTAMPS = False

# NMT: small Apache-2.0 Marian checkpoints, loaded lazily per direction.
TRANSLATION_MODEL_VI_EN = "Helsinki-NLP/opus-mt-vi-en"
TRANSLATION_MODEL_EN_VI = "Helsinki-NLP/opus-mt-en-vi"
TRANSLATION_SRC_LANG = "vie_Latn"
TRANSLATION_TGT_LANG = "eng_Latn"
TRANSLATION_DEVICE = "cpu"

# Audio / adaptive energy VAD. No neural VAD model is loaded per session.
SAMPLE_RATE = 16000
AUDIO_SEND_INTERVAL_MS = 250
VAD_BASE_THRESHOLD = 0.012
VAD_ALPHA = 0.05
VAD_MIN_NOISE = 0.001
VAD_MAX_NOISE = 0.05
VAD_INITIAL_NOISE = 0.003
VAD_SPEECH_PROB_THRESHOLD = 0.5

# Audio normalization.
NORMALIZER_TARGET_DB = -20.0
NORMALIZER_MIN_GAIN = 0.3
NORMALIZER_MAX_GAIN = 5.0
NORMALIZER_NOISE_FLOOR = 0.001
NORMALIZER_HIGH_PASS_HZ = 80
NORMALIZER_RMS_THRESHOLD = 0.005
NORMALIZER_SOFT_CLIP_THRESHOLD = 0.95
NORMALIZER_MIN_AUDIO_SEC = 0.5
NORMALIZER_HISTORY_SIZE = 50
NORMALIZER_UPDATE_INTERVAL = 10

# Streaming segmentation.
MAX_SEGMENT_SEC = 3.0
OVERLAP_SEC = 0.35
SILENCE_LIMIT = 0.45
MIN_DECODE_SEC = 0.8
PROB_DROP_THRESHOLD = 0.4
CONTINUOUS_SPEECH_PARTIAL_SEC = 1.5
PRE_SPEECH_SEC = 0.25
ENABLE_PARTIAL_TRANSCRIPTS = False
SEGMENT_MIN_EMIT_SEC = 1.0
SEGMENT_PREVIOUS_PROB_THRESHOLD = 0.6
AUDIO_QUEUE_MAX_CHUNKS = 128
AUDIO_DRAIN_TIMEOUT_SEC = 5.0
TRANSLATION_DRAIN_TIMEOUT_SEC = 8.0
PARTIAL_FINALIZE_TIMEOUT_SEC = 3.0
WEBRTC_EMIT_SEC = 0.16

# Lightweight stabilisation / confidence gate.
AGREEMENT_N = 2
HALLUCINATION_HISTORY_SIZE = 5
MAX_HALLUCINATION_RETRIES = 0
OVERLAP_THRESHOLD_DIFF = 0.1
HALLUCINATION_QUIET_RMS = 0.003
HALLUCINATION_LONG_TEXT_WORDS = 6
HALLUCINATION_RETRY_TEMPERATURES = (0.2, 0.4, 0.6)

# Inference options.
ASR_NUM_WORKERS = 1
ASR_BEST_OF = 1
ASR_TEMPERATURE = 0.0
ASR_REPETITION_PENALTY = 1.15
ASR_NO_SPEECH_THRESHOLD = 0.6
ASR_COMPRESSION_RATIO_THRESHOLD = 2.4
TRANSLATION_MAX_INPUT_LENGTH = 256
TRANSLATION_MAX_OUTPUT_LENGTH = 256
TRANSLATION_NUM_BEAMS = 1

# Cloud-only convenience features are opt-in and excluded from the edge path.
ENABLE_GROQ = False
GROQ_API_KEY = ""
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TIMEOUT = 10
AUTO_SUMMARY_MIN_DURATION = 0
GROQ_TEMPERATURE = 0.3
GROQ_MAX_TOKENS = 1024

# Modal is only a remote smoke-test runtime. Keeping its knobs here means
# main.py, documentation, and deployment code do not each invent defaults.
MODAL_APP_NAME = "theduo-edge-interpreter"
MODAL_GPU = "T4"
MODAL_MEMORY_MB = 12288
MODAL_TIMEOUT_SECONDS = 900
MODAL_SCALEDOWN_SECONDS = 60
MODAL_MAX_INPUTS = 4
MODAL_MAX_CONTAINERS = 1
MODAL_DEPLOYMENT_NAME = "modal"
MODAL_COMPUTE_LABEL = f"Modal {MODAL_GPU}"
MODAL_ENABLE_GROQ = False
MODAL_MODEL_CACHE_VOLUME = "theduo-model-cache"
MODAL_WHISPER_MODEL = validate_whisper_model("medium")
MODAL_ASR_DEVICE = "cuda"
MODAL_ASR_COMPUTE_TYPE = "int8_float16"
MODAL_TRANSLATION_DEVICE = "cpu"
MODAL_MODEL_CACHE_DIR = "/cache"
MODAL_HF_HOME = "/cache/huggingface"
MODAL_VOLUME_MOUNT_PATH = "/cache"
MODAL_REMOTE_ROOT = "/root"
MODAL_BASE_IMAGE = "nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04"
MODAL_PYTHON_VERSION = "3.11"
MODAL_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cpu"
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


def activate_modal_profile() -> None:
    """Select Modal values before importing any inference module."""

    global WHISPER_MODEL, ASR_DEVICE, ASR_COMPUTE_TYPE
    global TRANSLATION_DEVICE, MODEL_CACHE_DIR, HF_HOME, ENABLE_GROQ

    WHISPER_MODEL = MODAL_WHISPER_MODEL
    ASR_DEVICE = MODAL_ASR_DEVICE
    ASR_COMPUTE_TYPE = MODAL_ASR_COMPUTE_TYPE
    TRANSLATION_DEVICE = MODAL_TRANSLATION_DEVICE
    MODEL_CACHE_DIR = MODAL_MODEL_CACHE_DIR
    HF_HOME = MODAL_HF_HOME
    ENABLE_GROQ = MODAL_ENABLE_GROQ
