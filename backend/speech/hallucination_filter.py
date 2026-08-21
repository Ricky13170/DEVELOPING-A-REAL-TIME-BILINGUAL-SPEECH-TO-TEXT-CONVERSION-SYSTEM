import difflib
import re
from collections import deque
import logging

from backend.config import (
    HALLUCINATION_HISTORY_SIZE,
    HALLUCINATION_LONG_TEXT_WORDS,
    HALLUCINATION_QUIET_RMS,
)

logger = logging.getLogger(__name__)

class HallucinationFilter:
    def __init__(self, history_size: int = HALLUCINATION_HISTORY_SIZE):

        self.recent_texts = deque(maxlen=history_size)

        self.exact_hallucinations = {
            # Single-word artifacts (Vietnamese)
            "ừ", "à", "ờ", "ồ", "ừm", "hử", "hả",

            # Music markers (exact only)
            "music", "♪", "nhạc", "[music]", "[âm nhạc]",

            # English artifacts
            "uh", "um", "hmm",
        }

        self.forbidden_substrings = [
            # YouTube artifacts
            "subscribe", "đăng ký kênh", "like and subscribe",
            "ghiền mì gõ", "la la school",

            # Whisper timestamp artifacts
            "[", "]", ">>", "<<",

            # Music notation when repeated
            "♪♪", "nhạc nhạc",
        ]

        # Repetition is meaningful for short safety commands (for example,
        # "dừng lại, dừng lại"), so those must not be removed as duplicates.
        self.safety_command_terms = {
            "stop", "emergency stop", "danger", "warning", "fire",
            "evacuate", "evacuation", "help", "shut down", "turn off",
            "high voltage", "gas leak",
            "dừng", "dừng lại", "dừng máy", "dừng khẩn cấp", "khẩn cấp",
            "nguy hiểm", "cảnh báo", "cháy", "có cháy", "sơ tán",
            "cứu với", "tắt máy", "ngắt điện", "rò rỉ khí", "điện cao thế",
        }

    def is_safety_command(self, text: str) -> bool:
        """Return whether text is a short operational or safety command."""
        normalized = re.sub(r"[^\w\s]", " ", text.lower(), flags=re.UNICODE)
        normalized = " ".join(normalized.split())
        words = normalized.split()
        if not words or len(words) > 8:
            return False

        padded = f" {normalized} "
        return any(f" {term} " in padded for term in self.safety_command_terms)

    def is_hallucination(
        self,
        text: str,
        audio_rms: float,
        confidence: float = 1.0,
        is_final: bool = True
    ) -> tuple[bool, str]:

        if not text or not text.strip():
            return True, "empty"

        text = text.strip()
        text_lower = text.lower()
        words = text.split()
        is_safety_command = self.is_safety_command(text)

        if len(text) < 2:
            return True, "too_short"

        # Energy VAD already rejects silence. Do not reject valid quiet speech
        # merely because ASR normalizes it before inference.
        if audio_rms < HALLUCINATION_QUIET_RMS and len(words) > HALLUCINATION_LONG_TEXT_WORDS:
            logger.debug(f"Audio-text mismatch: RMS={audio_rms:.4f}, words={len(words)}")
            return True, "quiet_audio_long_text"

        if text_lower in self.exact_hallucinations:
            logger.debug(f"Exact hallucination: '{text}'")
            return True, f"exact:{text}"

        for pattern in self.forbidden_substrings:
            if pattern in text_lower:
                logger.debug(f"Forbidden substring detected: '{pattern}'")
                return True, f"forbidden:{pattern}"


        matched = False
        for recent_text in list(self.recent_texts)[-3:]:
            similarity = difflib.SequenceMatcher(None, text_lower, recent_text.lower().strip()).ratio()

            if len(text_lower) > 10:
                if similarity > 0.85:
                    logger.debug(f"Fuzzy repetition detected (ratio={similarity:.2f}): {text[:50]}...")
                    matched = True
                    break
            else:
                if similarity == 1.0:
                    matched = True
                    break

        if matched and not is_safety_command:
            return True, "repetition"
        if matched:
            logger.info(f"Preserving repeated safety command: '{text[:80]}'")

        if confidence < 0.15:
            logger.debug(f"Very low confidence: {confidence:.2f}")
            return True, "low_confidence"


        if len(set(words)) == 1 and len(words) >= 3 and not is_safety_command:
            logger.debug(f"Repeated single word: {words[0]}")
            return True, "repeated_word"


        if is_final:
            self.recent_texts.append(text)

        return False, "ok"

    def reset(self):
        """Reset filter state (call at session start)"""
        self.recent_texts.clear()

    def get_history(self) -> list[str]:
        """Get recent transcript history"""
        return list(self.recent_texts)
