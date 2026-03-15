import os
import numpy as np
import torch
import logging
from backend.config import SAMPLE_RATE

logger = logging.getLogger(__name__)


class VADManager:
    """Pyannote neural VAD for streaming speech detection.
    
    Loads the bundled Pyannote model from whisperx/assets/pytorch_model.bin
    to avoid HuggingFace token requirement.
    
    Interface:
        is_speech(audio) → bool
        load(), reset(), get_stats()
    """
    
    def __init__(self, device: str = "cuda", threshold: float = 0.5):
        self.device = device
        self.threshold = threshold
        self.model = None
        self._loaded = False
        
        # Rolling context buffer — Pyannote needs longer context for accuracy
        self._context_samples = SAMPLE_RATE * 2  # 2 seconds
        self._context_buffer = np.array([], dtype=np.float32)
        
        # Stats tracking
        self._last_prob = 0.0
    
    def _find_model_path(self) -> str:
        """Find the bundled pytorch_model.bin from whisperx package"""
        import whisperx
        whisperx_dir = os.path.dirname(os.path.abspath(whisperx.__file__))
        model_fp = os.path.join(whisperx_dir, "assets", "pytorch_model.bin")
        
        if not os.path.exists(model_fp):
            raise FileNotFoundError(
                f"Pyannote model not found at {model_fp}. "
                "Make sure whisperx is installed with its assets."
            )
        
        return model_fp
    
    def load(self):
        """Load Pyannote segmentation model from WhisperX bundled assets"""
        if self._loaded:
            return
        
        from backend.torch_patch import apply_torch_load_patch, suppress_stdout
        apply_torch_load_patch()
        
        from pyannote.audio import Model
        
        model_fp = self._find_model_path()
        logger.info(f"[VAD] Loading Pyannote model from {model_fp}")
        
        with suppress_stdout():
            self.model = Model.from_pretrained(model_fp)
            self.model.to(self.device)
            self.model.eval()
        
        self._loaded = True
        logger.info("[VAD] Pyannote VAD ready (bundled model)")
    
    def detect(self, audio: np.ndarray) -> tuple:
        """Check if audio chunk contains speech using Pyannote neural inference.
        
        Returns (is_speech: bool, speech_prob: float) — probability-aware detection.
        
        Maintains a 2-second rolling context buffer and runs the segmentation
        model on it. Uses the last few output frames (corresponding to the new
        chunk) to determine speech activity.
        
        Args:
            audio: float32 audio chunk at 16kHz (~250ms = 4000 samples)
            
        Returns:
            (is_speech, speech_prob) tuple
        """
        if not self._loaded:
            self.load()
        
        if len(audio) == 0:
            return False, 0.0
        
        # Build context: append new chunk, keep last 2 seconds
        self._context_buffer = np.concatenate([self._context_buffer, audio])
        if len(self._context_buffer) > self._context_samples:
            self._context_buffer = self._context_buffer[-self._context_samples:]
        
        # Prepare tensor: (batch=1, channel=1, samples)
        waveform = torch.from_numpy(self._context_buffer).float()
        waveform = waveform.unsqueeze(0).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            output = self.model(waveform)
        
        probs = torch.sigmoid(output)
        
        # Use the last few frames (corresponding to the new chunk)
        num_frames = probs.shape[1]
        chunk_ratio = len(audio) / len(self._context_buffer)
        last_n = max(1, int(num_frames * chunk_ratio))
        recent_probs = probs[0, -last_n:, :]
        
        speech_prob = recent_probs.max(dim=-1).values.mean().item()
        self._last_prob = speech_prob
        
        return speech_prob > self.threshold, speech_prob

    def is_speech(self, audio: np.ndarray) -> bool:
        """Backward-compatible wrapper for detect()."""
        is_speech, _ = self.detect(audio)
        return is_speech
    
    def get_last_prob(self) -> float:
        """Get the last computed speech probability."""
        return self._last_prob
    
    def reset(self):
        """Reset VAD state (call at session start)"""
        self._context_buffer = np.array([], dtype=np.float32)
        self._last_prob = 0.0
    
    def get_stats(self) -> dict:
        return {
            "speech_probability": self._last_prob,
            "threshold": self.threshold,
            "is_speech": self._last_prob > self.threshold,
            "context_duration_ms": int(len(self._context_buffer) / SAMPLE_RATE * 1000),
        }
