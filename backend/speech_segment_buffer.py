import numpy as np
from backend.config import SAMPLE_RATE
class SpeechSegmentBuffer:
    def __init__(
        self, 
        sample_rate: int = 16000,
        max_sec: float = 8.0,
        overlap_sec: float = 0.5,
        silence_limit: float = 0.6
    ):
        self.sr = sample_rate
        self.max_sec = max_sec
        self.overlap_sec = overlap_sec
        self.silence_limit = silence_limit
        self.reset()
    
    def reset(self):
        self.in_speech = False
        self.segment = [] 
        self.overlap = np.zeros(0, dtype=np.float32)  
        self.last_voice_ts = 0.0  
    
    def process(self, audio: np.ndarray, is_speech: bool, now_ts: float):
        if is_speech:
            if not self.in_speech:

                self.in_speech = True
                self.segment = [self.overlap] if len(self.overlap) > 0 else []
            
            self.last_voice_ts = now_ts
            self.segment.append(audio)
            
            # Check max_sec EVEN during continuous speech
            total_samples = sum(len(chunk) for chunk in self.segment)
            total_sec = total_samples / self.sr
            
            if total_sec >= self.max_sec:
                chunk = np.concatenate(self.segment)
                self._update_overlap(chunk)
                self.segment = []
                self.in_speech = False
                return 'final', chunk
            
            return None
        
        if not self.in_speech:

            return None
        
        silence_duration = now_ts - self.last_voice_ts
        
        self.segment.append(audio)
        
        total_samples = sum(len(chunk) for chunk in self.segment)
        total_sec = total_samples / self.sr
        
        
        if silence_duration >= self.silence_limit:
            chunk = np.concatenate(self.segment)
            self._update_overlap(chunk)
            self.reset()
            return "final", chunk
        
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