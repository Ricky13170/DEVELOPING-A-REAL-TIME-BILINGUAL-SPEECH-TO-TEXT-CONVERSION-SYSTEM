import numpy as np
from backend.config import SAMPLE_RATE
class AudioBuffer:
    def __init__(self):
        self.chunks = []  
        self.start_time = 0.0 
        self.total_samples = 0
    
    @property
    def duration(self) -> float:
        """Get buffer duration in seconds"""
        return self.total_samples / SAMPLE_RATE
    
    @property
    def timestamp(self) -> str:
        total_sec = int(self.start_time)
        minutes = total_sec // 60
        seconds = total_sec % 60
        return f"{minutes:02d}:{seconds:02d}"
    
    def append(self, audio: np.ndarray):
        if audio.size == 0:
            return
        
        flat_audio = audio.flatten().astype(np.float32)
        self.chunks.append(flat_audio)
        self.total_samples += flat_audio.size
    
    def get_audio(self) -> np.ndarray:
        if not self.chunks:
            return np.array([], dtype=np.float32)
        
        return np.concatenate(self.chunks)
    
    def trim(self, keep_sec: float):
        keep_samples = int(keep_sec * SAMPLE_RATE)
        
        if self.total_samples <= keep_samples:
            return
        
        full_audio = self.get_audio()
        
        removed_samples = self.total_samples - keep_samples
        self.start_time += removed_samples / SAMPLE_RATE
        
        new_audio = full_audio[-keep_samples:]
        
        self.chunks = [new_audio]
        self.total_samples = new_audio.size
    
    def clear(self):
        """Clear entire buffer"""
        self.chunks = []
        self.total_samples = 0
        self.start_time = 0.0
    
    def is_empty(self) -> bool:
        """Check if buffer is empty"""
        return self.total_samples == 0
    
    def __len__(self) -> int:
        """Return number of samples in buffer"""
        return self.total_samples