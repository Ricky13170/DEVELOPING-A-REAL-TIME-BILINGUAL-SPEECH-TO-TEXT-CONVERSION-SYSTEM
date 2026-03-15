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

# VAD (Energy-based)
VAD_THRESHOLD = 0.01
MIN_SILENCE_DURATION = 0.6
MAX_BUFFER_DURATION = 8.0

# NLLB Translation
NLLB_MODEL = "facebook/nllb-200-3.3B"
NLLB_SRC_LANG = "vie_Latn"
NLLB_TGT_LANG = "eng_Latn"
NLLB_DEVICE = "cuda"

# Second-pass re-translation 
RETRANSLATE_BATCH_SIZE = 3     
RETRANSLATE_DELAY_SEC = 2.0      

# Audio
SAMPLE_RATE = 16000

# VAD Configuration
VAD_BASE_THRESHOLD = 0.015  
VAD_ALPHA = 0.05          
VAD_MIN_NOISE = 0.001     
VAD_MAX_NOISE = 0.05       

# Segmentation Configuration
MAX_SEGMENT_SEC = 3.1       
OVERLAP_SEC = 0.5           
SILENCE_LIMIT = 0.5         
MIN_DECODE_SEC = 1.0      
OVERLAP_THRESHOLD_DIFF = 0.1  

# Streaming tuning (prob-based emission)
PROB_DROP_THRESHOLD = 0.4     
CONTINUOUS_SPEECH_PARTIAL_SEC = 1.5  
PRE_SPEECH_SEC = 0.3               

# Local Agreement
AGREEMENT_N = 2          

# Hallucination Filter
HALLUCINATION_HISTORY_SIZE = 5

# BARTpho Post-processing
import os
ENABLE_BARTPHO = False  
BARTPHO_ADAPTER = "522H0134-NguyenNhatHuy/bartpho-syllable-correction"
BARTPHO_DEVICE = "cuda"

# Groq LLM (context priming + auto summary)
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_TIMEOUT = 10
AUTO_SUMMARY_MIN_DURATION = 120  
