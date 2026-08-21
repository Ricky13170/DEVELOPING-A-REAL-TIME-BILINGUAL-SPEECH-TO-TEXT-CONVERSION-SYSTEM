"""Low-cost adaptive energy voice activity detection."""

import numpy as np

from backend.config import (
    VAD_ALPHA,
    VAD_BASE_THRESHOLD,
    VAD_INITIAL_NOISE,
    VAD_MAX_NOISE,
    VAD_MIN_NOISE,
    VAD_SPEECH_PROB_THRESHOLD,
)


class VADManager:
    """Streaming VAD without neural weights or device-specific dependencies."""

    def __init__(
        self,
        base_threshold: float = VAD_BASE_THRESHOLD,
        alpha: float = VAD_ALPHA,
        min_noise: float = VAD_MIN_NOISE,
        max_noise: float = VAD_MAX_NOISE,
    ):
        self.base_threshold = base_threshold
        self.alpha = alpha
        self.min_noise = min_noise
        self.max_noise = max_noise
        self._initial_noise = max(min_noise, VAD_INITIAL_NOISE)
        self.noise_level = self._initial_noise
        self._last_prob = 0.0

    def load(self):
        """Compatibility no-op; energy VAD has no model weights."""

    def detect(self, audio: np.ndarray) -> tuple[bool, float]:
        if len(audio) == 0:
            return False, 0.0

        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        threshold = self.noise_level + self.base_threshold
        is_speech = rms > threshold

        if not is_speech:
            estimated = (1.0 - self.alpha) * self.noise_level + self.alpha * rms
            self.noise_level = float(np.clip(estimated, self.min_noise, self.max_noise))

        speech_prob = float(np.clip(rms / max(threshold * 2.0, 1e-6), 0.0, 1.0))
        self._last_prob = speech_prob
        return is_speech, speech_prob

    def is_speech(self, audio: np.ndarray) -> bool:
        return self.detect(audio)[0]

    def get_last_prob(self) -> float:
        return self._last_prob

    def reset(self):
        self.noise_level = self._initial_noise
        self._last_prob = 0.0

    def get_stats(self) -> dict:
        threshold = self.noise_level + self.base_threshold
        return {
            "backend": "adaptive-energy",
            "noise_level": self.noise_level,
            "threshold": threshold,
            "speech_probability": self._last_prob,
            "is_speech": self._last_prob >= VAD_SPEECH_PROB_THRESHOLD,
        }
