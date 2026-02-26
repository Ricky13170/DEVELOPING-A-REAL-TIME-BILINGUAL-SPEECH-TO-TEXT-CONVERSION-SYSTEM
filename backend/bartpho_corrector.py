import re
import logging
from typing import Optional, List, Tuple
import torch
logger = logging.getLogger(__name__)

BARTPHO_ADAPTER = "522H0134-NguyenNhatHuy/bartpho-syllable-correction"
BARTPHO_BASE = "vinai/bartpho-syllable"

# English Detection — Three Layers
# Layer 1: Vietnamese diacritics → always Vietnamese
_VIET_CHARS = set(
    "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợ"
    "ùúủũụưứừửữựỳýỷỹỵđ"
    "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ"
    "ÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ"
)

_ASCII_WORD = re.compile(r'^[A-Za-z0-9]+$')
_PUNCT = re.compile(r'^[^\w\s]+|[^\w\s]+$')

_COMMON_EN_ABBREV = {
    "AI", "ML", "NLP", "GPU", "CPU", "API", "LLM", "CNN", "RNN", "GAN",
    "IoT", "SQL", "LSTM", "BERT", "GPT", "RAM", "SSD", "HDD",
    "USB", "HTTP", "HTTPS", "URL", "HTML", "CSS", "JSON", "XML", "REST",
    "OK", "IT", "CV", "IP", "OS", "UI", "UX", "ID", "ASIC", "FPGA",
    "PDF", "SDK", "CLI", "GUI", "OOP", "MVP", "POC", "SaaS", "PaaS",
    "AWS", "GCP", "CUDA", "TPU", "VRAM", "FLOPS", "FPS",
}

# Layer 2: Common English words in Vietnamese tech/academic speech
_COMMON_EN_WORDS = {
    # ML / AI
    "machine", "learning", "deep", "network", "neural", "computer",
    "vision", "processing", "natural", "language", "algorithm",
    "training", "dataset", "feature", "transformer", "attention",
    "encoder", "decoder", "embedding", "classification", "regression",
    "clustering", "segmentation", "detection", "recognition",
    "generation", "reinforcement", "supervised", "unsupervised",
    "optimization", "gradient", "backpropagation", "overfitting",
    "convolution", "pooling", "recurrent", "generative", "discriminative",
    "pretrained", "fine", "tuning", "inference", "prediction",
    "benchmark", "baseline", "hyperparameter", "parameter", "weight",
    "batch", "epoch", "loss", "accuracy", "precision", "recall",
    # Media / Internet
    "audio", "video", "online", "offline", "download", "upload",
    "youtube", "google", "facebook", "twitter", "github", "website",
    "streaming", "podcast", "channel", "content", "creator",
    # Academic
    "homework", "deadline", "project", "assignment", "presentation",
    "slide", "demo", "tutorial", "workshop", "feedback", "review",
    "paper", "conference", "journal", "thesis", "abstract",
    "research", "experiment", "evaluation", "metric",
    # Tech general
    "software", "hardware", "server", "database", "cloud", "framework",
    "smartphone", "laptop", "desktop", "tablet", "internet",
    "bluetooth", "wifi", "router", "browser", "plugin", "update",
    "install", "backup", "firewall", "protocol",
    # Programming
    "code", "debug", "deploy", "compile", "runtime", "interface",
    "function", "variable", "string", "array", "module", "library",
    "frontend", "backend", "fullstack", "container", "docker",
    "microservice", "pipeline", "workflow", "script", "repository",
    "commit", "merge", "branch", "pull", "push", "request",
}

# Safety: minimum ratio of output/input word count
_MIN_LENGTH_RATIO = 0.5


def _strip_punct(word: str) -> str:
    """Strip leading/trailing punctuation from a word"""
    return _PUNCT.sub("", word)


def _is_english_word(word: str) -> bool:
    """
    Check if a word is English (three-layer detection).

    Layer 1: Diacritics + Caps + Abbreviation rules
    Layer 2: Common English word list
    """
    if not word:
        return False

    # Has Vietnamese diacritics → definitely Vietnamese
    if any(c in _VIET_CHARS for c in word):
        return False

    # Not ASCII → not English
    if not _ASCII_WORD.match(word):
        return False

    # Known abbreviation (case-insensitive)
    if word in _COMMON_EN_ABBREV or word.upper() in _COMMON_EN_ABBREV:
        return True

    # ALL CAPS ≥2 chars → English (GPU, API, etc.)
    if len(word) >= 2 and word.isupper():
        return True

    # Mixed case mid-word → English (TensorFlow, PyTorch)
    if any(c.isupper() for c in word[1:]):
        return True

    # Starts uppercase + ≥4 chars → English proper noun
    if word[0].isupper() and len(word) >= 4:
        return True

    # Common English word list (case-insensitive)
    if word.lower() in _COMMON_EN_WORDS:
        return True

    # Default: short lowercase ASCII word → assume Vietnamese
    return False


def split_en_vi(text: str) -> List[Tuple[str, bool]]:
    """
    Split text into chunks of (text, is_english).

    Three-layer detection:
      1. Per-word rules (diacritics, caps, abbreviations, word list)
      2. Consecutive ASCII-only words (2+) → all treated as English
      3. Group into contiguous chunks
    """
    words = text.split()
    if not words:
        return []

    classifications = []  
    for word in words:
        clean = _strip_punct(word)
        is_en = _is_english_word(clean)
        is_ascii = bool(_ASCII_WORD.match(clean)) if clean else False
        classifications.append((word, is_en, is_ascii))

    i = 0
    while i < len(classifications):
        word, is_en, is_ascii = classifications[i]
        if is_ascii and not is_en:
         
            j = i
            while j < len(classifications) and classifications[j][2]:
                j += 1
            if j - i >= 2:
               
                for k in range(i, j):
                    w, _, a = classifications[k]
                    classifications[k] = (w, True, a)
                    logger.debug(f"[EN-detect] consecutive ASCII: '{w}' → English")
            i = j
        else:
            i += 1

    chunks = []
    current_words = []
    current_is_en = classifications[0][1]

    for word, is_en, _ in classifications:
        if is_en == current_is_en:
            current_words.append(word)
        else:
            chunks.append((" ".join(current_words), current_is_en))
            current_words = [word]
            current_is_en = is_en

    if current_words:
        chunks.append((" ".join(current_words), current_is_en))

    return chunks


# BARTpho Corrector
class BARTphoCorrector:
    def __init__(
        self,
        adapter_id: str = BARTPHO_ADAPTER,
        device: str = "cuda",
        cache_dir: Optional[str] = None,
    ):
        self.adapter_id = adapter_id
        self.device = device
        self.cache_dir = cache_dir

        self.model = None
        self.tokenizer = None
        self.is_loaded = False

    def load_model(self):
        if self.is_loaded:
            return

        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from peft import PeftModel
        from backend.torch_patch import suppress_stdout

        logger.info(f"Loading BARTpho corrector: {self.adapter_id}")

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.adapter_id,
            cache_dir=self.cache_dir,
        )

        with suppress_stdout():
            base_model = AutoModelForSeq2SeqLM.from_pretrained(
                BARTPHO_BASE,
                cache_dir=self.cache_dir,
                dtype=torch.float16,
            )
            self.model = PeftModel.from_pretrained(
                base_model,
                self.adapter_id,
                cache_dir=self.cache_dir,
            )

        self.model = self.model.to(self.device)
        self.model.eval()
        self.is_loaded = True
        logger.info("BARTpho corrector ready")

    def _infer(self, text: str, max_length: int = 256) -> str:
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_length=max_length,
                num_beams=4,
                early_stopping=True,
                do_sample=False,
            )

        corrected = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

        # Length safety check 
        in_words = len(text.split())
        out_words = len(corrected.split()) if corrected else 0

        if in_words > 0 and out_words / in_words < _MIN_LENGTH_RATIO:
            logger.warning(
                f"[BARTpho] Rejected: output too short "
                f"({out_words}/{in_words} words = {out_words/in_words:.0%}). "
                f"Keeping original: '{text[:60]}'"
            )
            return text

        return corrected

    def correct(self, text: str, max_length: int = 256) -> str:
        """
        Correct Vietnamese ASR transcription errors (English-Aware v2).

        Flow: Split(EN/VI) → Correct(VI only) → Merge
        Safety: Rejects corrections that drop too many words.

        Args:
            text: Raw ASR output (mixed Vietnamese + English)
            max_length: Max output token length

        Returns:
            Corrected text with English parts preserved
        """
        if not text or not text.strip():
            return ""

        if not self.is_loaded:
            self.load_model()

        try:
            # Split into EN/VI chunks
            chunks = split_en_vi(text)

            # Log detection results
            en_parts = [c for c, is_en in chunks if is_en]
            if en_parts:
                logger.info(f"[BARTpho] English protected: {en_parts}")

            # If entirely English, skip BARTpho entirely
            if all(is_en for _, is_en in chunks):
                logger.info(f"[BARTpho] All English, skipping: '{text[:60]}'")
                return text

            # Correct only Vietnamese chunks
            vi_chunks = [(i, chunk) for i, (chunk, is_en) in enumerate(chunks) if not is_en]
            result_chunks = list(chunks)

            for idx, vi_text in vi_chunks:
                if vi_text.strip():
                    corrected_vi = self._infer(vi_text, max_length)
                    result_chunks[idx] = (corrected_vi, False)

            # Merge back
            result = " ".join(chunk for chunk, _ in result_chunks)
            return result.strip()

        except Exception as e:
            logger.error(f"BARTpho correction error: {e}")
            return text  