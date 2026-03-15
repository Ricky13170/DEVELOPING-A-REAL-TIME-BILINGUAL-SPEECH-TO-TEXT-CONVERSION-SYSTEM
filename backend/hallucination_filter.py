import hashlib
import difflib
from collections import deque
import logging

logger = logging.getLogger(__name__)

class HallucinationFilter:
    def __init__(self, history_size: int = 5):

        self.recent_hashes = deque(maxlen=history_size)
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
    
    def _hash_text(self, text: str) -> str:
        """Create hash for repetition detection"""
        normalized = text.lower().strip()
        return hashlib.md5(normalized.encode()).hexdigest()[:8]
    
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
        
        if len(text) < 2:
            return True, "too_short"
        
        if audio_rms < 0.02 and len(words) > 6:
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
                    
        if matched:
            return True, "repetition"
        
        if confidence < 0.15:
            logger.debug(f"Very low confidence: {confidence:.2f}")
            return True, "low_confidence"
        

        if len(set(words)) == 1 and len(words) >= 3:
            logger.debug(f"Repeated single word: {words[0]}")
            return True, "repeated_word"
        

        if is_final:
            text_hash = self._hash_text(text)
            self.recent_hashes.append(text_hash)
            self.recent_texts.append(text)
        
        return False, "ok"
    
    def reset(self):
        """Reset filter state (call at session start)"""
        self.recent_hashes.clear()
        self.recent_texts.clear()
    
    def get_history(self) -> list[str]:
        """Get recent transcript history"""
        return list(self.recent_texts)
