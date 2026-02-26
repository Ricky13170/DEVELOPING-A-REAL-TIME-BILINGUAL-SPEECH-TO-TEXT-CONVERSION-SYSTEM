import os
from backend.config import (
    WHISPER_MODEL, WHISPER_LANGUAGE, 
    NLLB_MODEL, NLLB_SRC_LANG, NLLB_TGT_LANG
)
from backend.asr import WhisperASR
from backend.translation import NLLBTranslator

def download_models():
    print("Pre-downloading models...")
    
    # Whisper
    print(f"Downloading Whisper: {WHISPER_MODEL}")
    asr = WhisperASR(
        model_size=WHISPER_MODEL,
        language=WHISPER_LANGUAGE,
        cache_dir="/cache/whisper"
    )
    try:
        asr.load_model() 
    except Exception as e:
        print(f"Whisper load warning: {e}")

    # NLLB
    print(f"Downloading NLLB: {NLLB_MODEL}")
    translator = NLLBTranslator(
        model_name=NLLB_MODEL,
        src_lang=NLLB_SRC_LANG,
        tgt_lang=NLLB_TGT_LANG,
        cache_dir="/cache/nllb"
    )
    translator.load_model()
        
    print("All models downloaded to /cache")


if __name__ == "__main__":
    download_models()