"""Thread-safe MarianMT translation for the Vietnamese-English language pair."""

from __future__ import annotations

import logging
import threading
from typing import Optional

import torch

from backend.config import CPU_THREADS

logger = logging.getLogger(__name__)


class MarianTranslator:
    """Lazy-loading VI-to-EN and EN-to-VI translator.

    A separate directional Marian checkpoint is loaded only when that direction
    is first requested.
    """

    MODEL_IDS = {
        ("vi", "en"): "Helsinki-NLP/opus-mt-vi-en",
        ("en", "vi"): "Helsinki-NLP/opus-mt-en-vi",
    }

    _LANG_ALIASES = {
        "vi": "vi",
        "vie": "vi",
        "vie_latn": "vi",
        "vietnamese": "vi",
        "en": "en",
        "eng": "en",
        "eng_latn": "en",
        "english": "en",
    }

    def __init__(
        self,
        src_lang: str = "vie_Latn",
        tgt_lang: str = "eng_Latn",
        device: str = "cpu",
        cache_dir: Optional[str] = None,
        vi_en_model: Optional[str] = None,
        en_vi_model: Optional[str] = None,
    ):
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.device = device
        self.cache_dir = cache_dir
        self.model_ids = {
            ("vi", "en"): vi_en_model or self.MODEL_IDS[("vi", "en")],
            ("en", "vi"): en_vi_model or self.MODEL_IDS[("en", "vi")],
        }

        default_direction = self._direction(src_lang, tgt_lang)
        self.model_name = self.model_ids.get(default_direction)

        # Compatibility attributes retained for code which introspects the
        # translator after load_model. They refer to the default direction.
        self.model = None
        self.tokenizer = None
        self.is_loaded = False

        self._models: dict[tuple[str, str], object] = {}
        self._tokenizers: dict[tuple[str, str], object] = {}
        self._load_lock = threading.RLock()
        self._inference_lock = threading.Lock()

    @classmethod
    def _canonical_lang(cls, language: Optional[str]) -> str:
        if not language:
            return ""
        normalized = language.strip().lower().replace("-", "_")
        return cls._LANG_ALIASES.get(normalized, normalized)

    @classmethod
    def _direction(
        cls,
        src_lang: Optional[str],
        tgt_lang: Optional[str],
    ) -> tuple[str, str]:
        return cls._canonical_lang(src_lang), cls._canonical_lang(tgt_lang)

    def _load_direction(self, direction: tuple[str, str]):
        if direction not in self.MODEL_IDS:
            raise ValueError(
                f"Unsupported Marian translation direction: "
                f"{direction[0] or '?'} -> {direction[1] or '?'}"
            )

        if direction in self._models:
            return self._tokenizers[direction], self._models[direction]

        with self._load_lock:
            if direction in self._models:
                return self._tokenizers[direction], self._models[direction]

            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            model_id = self.model_ids[direction]
            logger.info("Loading MarianMT %s on %s", model_id, self.device)

            if str(self.device).startswith("cpu"):
                torch.set_num_threads(CPU_THREADS)

            tokenizer = AutoTokenizer.from_pretrained(
                model_id,
                cache_dir=self.cache_dir,
            )

            model_kwargs = {"cache_dir": self.cache_dir}
            if str(self.device).startswith("cuda"):
                model_kwargs["torch_dtype"] = torch.float16

            model = AutoModelForSeq2SeqLM.from_pretrained(
                model_id,
                **model_kwargs,
            )
            model.to(self.device)
            model.eval()

            self._tokenizers[direction] = tokenizer
            self._models[direction] = model
            self.is_loaded = True

            default_direction = self._direction(self.src_lang, self.tgt_lang)
            if direction == default_direction or self.model is None:
                self.model_name = model_id
                self.tokenizer = tokenizer
                self.model = model

            logger.info("MarianMT ready: %s", model_id)
            return tokenizer, model

    def load_model(self):
        """Load only the constructor's default translation direction."""

        direction = self._direction(self.src_lang, self.tgt_lang)
        self._load_direction(direction)

    @staticmethod
    def _target_prefix(tokenizer, direction: tuple[str, str]) -> str:
        """Return the Latin Vietnamese target token when the model exposes it."""

        if direction != ("en", "vi"):
            return ""

        supported = getattr(tokenizer, "supported_language_codes", None) or ()
        candidates = (">>vie<<", ">>vi<<", ">>vie_Latn<<")
        for candidate in candidates:
            if candidate in supported:
                return candidate

        # opus-mt-en-vi documents a mandatory target prefix because it also
        # supports vie_Hani. Older tokenizer metadata may not expose the list.
        return ">>vie<<"

    def translate(
        self,
        text: str,
        src_lang: Optional[str] = None,
        tgt_lang: Optional[str] = None,
        max_length: int = 256,
    ) -> str:
        if not text or not text.strip():
            return ""

        effective_src = src_lang or self.src_lang
        effective_tgt = tgt_lang or self.tgt_lang
        direction = self._direction(effective_src, effective_tgt)

        if direction[0] == direction[1] and direction[0] in {"vi", "en"}:
            return text.strip()

        try:
            tokenizer, model = self._load_direction(direction)

            # Generation and tokenizer work are serialized. This avoids CPU
            # oversubscription and protects mutable state inside HF tokenizers.
            with self._inference_lock:
                source_text = text.strip()
                prefix = self._target_prefix(tokenizer, direction)
                if prefix and not source_text.startswith(prefix):
                    source_text = f"{prefix} {source_text}"

                inputs = tokenizer(
                    source_text,
                    return_tensors="pt",
                    truncation=True,
                    max_length=256,
                )
                model_device = next(model.parameters()).device
                inputs = {
                    key: value.to(model_device)
                    for key, value in inputs.items()
                }

                with torch.inference_mode():
                    outputs = model.generate(
                        **inputs,
                        max_length=max_length,
                        num_beams=1,
                        do_sample=False,
                    )

                translated = tokenizer.decode(
                    outputs[0],
                    skip_special_tokens=True,
                )
                return translated.strip()

        except Exception as exc:
            logger.error("Marian translation error: %s", exc)
            return ""


__all__ = ["MarianTranslator"]
