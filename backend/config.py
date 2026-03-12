import os

# Modal
MODAL_APP_NAME = "asr-thesis"
MODAL_GPU = "A100"
MODAL_MEMORY = 24576
MODAL_TIMEOUT = 600
MODAL_CONTAINER_IDLE_TIMEOUT = 120

# Whisper
WHISPER_MODEL = "large-v3"
WHISPER_LANGUAGE = "vi"  
ASR_DEVICE = "cuda"

# NLLB Translation
NLLB_MODEL = "facebook/nllb-200-3.3B"
NLLB_SRC_LANG = "vie_Latn"
NLLB_TGT_LANG = "eng_Latn"
NLLB_DEVICE = "cuda"

# Audio
SAMPLE_RATE = 16000

# VAD Configuration
VAD_BASE_THRESHOLD = 0.015  
VAD_ALPHA = 0.05          
VAD_MIN_NOISE = 0.001     
VAD_MAX_NOISE = 0.05       

# Segmentation Configuration
MAX_SEGMENT_SEC = 5.0       
OVERLAP_SEC = 0.8           
SILENCE_LIMIT = 0.5         
MIN_DECODE_SEC = 1.0      

# Local Agreement
AGREEMENT_N = 2          

# Hallucination Filter
HALLUCINATION_HISTORY_SIZE = 5

# Sentence-level translation
MT_FLUSH_TIMEOUT = 2.5  # seconds to wait before flushing incomplete sentence

# Groq LLM (context priming + auto summary)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TIMEOUT = 10
AUTO_SUMMARY_MIN_DURATION = 120

# HuggingFace
HF_TOKEN = os.environ.get("HF_TOKEN", "")