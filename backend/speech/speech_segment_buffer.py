import numpy as np
from backend.config import (
    CONTINUOUS_SPEECH_PARTIAL_SEC,
    MAX_SEGMENT_SEC,
    OVERLAP_SEC,
    PRE_SPEECH_SEC,
    PROB_DROP_THRESHOLD,
    SAMPLE_RATE,
    SEGMENT_MIN_EMIT_SEC,
    SEGMENT_PREVIOUS_PROB_THRESHOLD,
    SILENCE_LIMIT,
)

class SpeechSegmentBuffer:
    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        max_sec: float = MAX_SEGMENT_SEC,
        overlap_sec: float = OVERLAP_SEC,
        silence_limit: float = SILENCE_LIMIT,
        pre_speech_sec: float = PRE_SPEECH_SEC
    ):
        self.sr = sample_rate
        self.max_sec = max_sec
        self.overlap_sec = overlap_sec
        self.silence_limit = silence_limit
        self.pre_speech_samples = int(pre_speech_sec * sample_rate)
        self.pre_speech_buffer = []
        self.reset()

    def reset(self):
        self.in_speech = False
        self.segment = []
        self.overlap = np.zeros(0, dtype=np.float32)
        self.last_voice_ts = 0.0
        # Prob-based tracking
        self.prev_prob = 0.0
        self.continuous_speech_start = 0.0
        self.last_partial_emit_ts = 0.0

    def process(self, audio: np.ndarray, is_speech: bool, now_ts: float, speech_prob: float = 0.0):
        """Process audio chunk with probability-aware emission.

        Returns:
            None — no action needed
            ('final', audio_chunk) — finalized segment, decode with is_final=True
            ('partial', audio_chunk) — periodic partial, decode with is_final=False
        """
        if is_speech:
            if not self.in_speech:

                self.in_speech = True
                self.segment = []
                if len(self.overlap) > 0:
                    self.segment.append(self.overlap)
                if self.pre_speech_buffer:
                    self.segment.extend(self.pre_speech_buffer)
                    self.pre_speech_buffer = []
                self.continuous_speech_start = now_ts
                self.last_partial_emit_ts = now_ts

            self.last_voice_ts = now_ts
            self.segment.append(audio)

            total_samples = sum(len(chunk) for chunk in self.segment)
            total_sec = total_samples / self.sr

            prob_drop = self.prev_prob - speech_prob
            if (prob_drop >= PROB_DROP_THRESHOLD
                and total_sec >= SEGMENT_MIN_EMIT_SEC
                and self.prev_prob >= SEGMENT_PREVIOUS_PROB_THRESHOLD):

                old_prob = self.prev_prob
                chunk = np.concatenate(self.segment)
                self._update_overlap(chunk)
                self.reset()
                self.prev_prob = speech_prob
                print(f"⚡ Prob-drop emit: {old_prob:.2f}→{speech_prob:.2f} ({total_sec:.1f}s)")
                return 'final', chunk

            self.prev_prob = speech_prob

            if total_sec >= self.max_sec:
                chunk = np.concatenate(self.segment)
                self._update_overlap(chunk)
                self.segment = []
                self.in_speech = False
                return 'final', chunk

            speech_duration = now_ts - self.continuous_speech_start
            since_last_partial = now_ts - self.last_partial_emit_ts

            if (speech_duration >= CONTINUOUS_SPEECH_PARTIAL_SEC
                and since_last_partial >= CONTINUOUS_SPEECH_PARTIAL_SEC
                and total_sec >= SEGMENT_MIN_EMIT_SEC):
                self.last_partial_emit_ts = now_ts
                chunk = np.concatenate(self.segment)
                return 'partial', chunk

            return None

        self.prev_prob = speech_prob

        if not self.in_speech:

            self.pre_speech_buffer.append(audio)
            total = sum(len(c) for c in self.pre_speech_buffer)
            while total > self.pre_speech_samples and len(self.pre_speech_buffer) > 1:
                total -= len(self.pre_speech_buffer.pop(0))
            return None

        silence_duration = now_ts - self.last_voice_ts

        self.segment.append(audio)

        total_samples = sum(len(chunk) for chunk in self.segment)
        total_sec = total_samples / self.sr

        # Silence exceeded → final
        if silence_duration >= self.silence_limit:
            chunk = np.concatenate(self.segment)
            self._update_overlap(chunk)
            self.reset()
            return "final", chunk

        # Max duration → final
        if total_sec >= self.max_sec:
            chunk = np.concatenate(self.segment)
            self._update_overlap(chunk)
            self.segment = []
            self.in_speech = False
            return 'final', chunk

        return None

    def _update_overlap(self, chunk: np.ndarray):
        n_samples = int(self.overlap_sec * self.sr)

        if len(chunk) >= n_samples:
            self.overlap = chunk[-n_samples:]
        else:
            self.overlap = chunk.copy()

    def get_current_duration(self) -> float:
        """Get current segment duration in seconds"""
        if not self.segment:
            return 0.0
        total_samples = sum(len(chunk) for chunk in self.segment)
        return total_samples / self.sr

    def get_current_audio(self) -> np.ndarray:
        """Get current accumulated audio without finalizing"""
        if not self.segment:
            return np.array([], dtype=np.float32)
        return np.concatenate(self.segment)

    def flush(self):
        """Return an unfinished speech segment when recording stops."""
        if not self.in_speech or not self.segment:
            self.pre_speech_buffer = []
            return None

        chunk = np.concatenate(self.segment)
        self._update_overlap(chunk)
        self.reset()
        self.pre_speech_buffer = []
        return chunk
