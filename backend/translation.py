import logging
from typing import Optional
import torch
logger = logging.getLogger(__name__)

class NLLBTranslator:
    def __init__(self, model_name: str = "facebook/nllb-200-3.3B",
                 src_lang: str = "vie_Latn", tgt_lang: str = "eng_Latn",
                 device: str = "cuda", cache_dir: Optional[str] = None):
        self.model_name = model_name
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.device = device
        self.cache_dir = cache_dir
        self.model = None
        self.tokenizer = None
        self.is_loaded = False

    def load_model(self):
        if self.is_loaded:
            return
        
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        
        logger.info(f"Loading NLLB: {self.model_name}")
        
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            cache_dir=self.cache_dir,
            src_lang=self.src_lang
        )
        
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            self.model_name,
            cache_dir=self.cache_dir,
            torch_dtype=torch.float16,
            device_map="auto",
            low_cpu_mem_usage=True,
        )
        
        self.model.eval()
        self.is_loaded = True
        logger.info("NLLB loaded")

    def translate(self, text: str, max_length: int = 256, 
                   src_lang: str = None, tgt_lang: str = None) -> str:
        """Translate text with optional per-call language override.
        
        Args:
            text: Source text to translate
            max_length: Max output token length
            src_lang: Override source language (NLLB code e.g. 'vie_Latn')
            tgt_lang: Override target language (NLLB code e.g. 'eng_Latn')
        """
        if not text or not text.strip():
            return ""
        
        if not self.is_loaded:
            self.load_model()
        
        effective_src = src_lang or self.src_lang
        effective_tgt = tgt_lang or self.tgt_lang
        
        try:
            # Re-set tokenizer source language for this call
            self.tokenizer.src_lang = effective_src
            
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )
            
            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}
            
            tgt_lang_id = self.tokenizer.convert_tokens_to_ids(effective_tgt)
            
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    forced_bos_token_id=tgt_lang_id,
                    max_length=max_length,
                    num_beams=3,
                    early_stopping=True,
                    do_sample=False
                )
            
            translated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            return translated.strip()
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return ""