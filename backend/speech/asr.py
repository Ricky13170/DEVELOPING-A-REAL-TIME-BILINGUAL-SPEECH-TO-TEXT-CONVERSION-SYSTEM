"""Faster-Whisper adapter used by the streaming pipeline."""

import logging
import threading

import numpy as np

from backend.speech.audio_normalizer import AdaptiveNormalizer
from backend.config import (
    ASR_BEAM_SIZE,
    ASR_COMPUTE_TYPE,
    ASR_WORD_TIMESTAMPS,
    CPU_THREADS,
)

logger = logging.getLogger(__name__)
SAMPLE_RATE = 16000


class WhisperASR:
    def __init__(
        self,
        model_size="small",
        language=None,
        device="cpu",
        cache_dir=None,
        compute_type=None,
    ):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.cache_dir = cache_dir
        self.compute_type = compute_type or ASR_COMPUTE_TYPE
        self.model = None
        self._lock = threading.Lock()
        self.normalizer = AdaptiveNormalizer(target_dB=-20.0, sample_rate=SAMPLE_RATE)

    def load_model(self):
        if self.model is not None:
            return

        from faster_whisper import WhisperModel

        logger.info(
            "Loading Faster-Whisper %s on %s (%s)",
            self.model_size,
            self.device,
            self.compute_type,
        )
        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            download_root=self.cache_dir,
            num_workers=1,
            cpu_threads=CPU_THREADS,
        )
        logger.info("Faster-Whisper loaded")

    def transcribe(
        self,
        audio: np.ndarray,
        prompt: str = None,
        temperature: float = None,
        condition_on_previous_text: bool = True,
        language: str = None,
    ) -> tuple[str, float, list]:
        if self.model is None:
            self.load_model()
        if len(audio) < SAMPLE_RATE // 2:
            return "", 0.0, []

        normalized_audio, _ = self.normalizer.normalize(audio)
        normalized_audio = normalized_audio.astype(np.float32, copy=False)
        effective_language = language or self.language

        with self._lock:
            segments_iter, _ = self.model.transcribe(
                normalized_audio,
                language=effective_language,
                task="transcribe",
                beam_size=ASR_BEAM_SIZE,
                best_of=1,
                temperature=0.0 if temperature is None else temperature,
                initial_prompt=prompt or None,
                condition_on_previous_text=condition_on_previous_text,
                repetition_penalty=1.15,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.4,
                word_timestamps=ASR_WORD_TIMESTAMPS,
                vad_filter=False,
            )
            segments = list(segments_iter)

        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            return "", 0.0, []

        avg_logprob = sum(segment.avg_logprob for segment in segments) / max(len(segments), 1)
        confidence = min(1.0, max(0.0, 1.0 + avg_logprob / 2.0))
        words = []
        if ASR_WORD_TIMESTAMPS:
            for segment in segments:
                for word in segment.words or []:
                    words.append({
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                        "score": word.probability,
                    })

        return text, confidence, words
