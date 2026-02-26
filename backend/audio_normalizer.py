import numpy as np
from scipy.signal import butter, lfilter
import logging
logger = logging.getLogger(__name__)

class WhisperAudioNormalizer:
    def __init__(self, target_dB: float = -20.0, sample_rate: int = 16000):
        self.target_dB = target_dB
        self.target_rms = 10 ** (target_dB / 20)  
        self.sample_rate = sample_rate
        
        self.min_gain = 0.3   
        self.max_gain = 5.0   
        
        # Noise gate
        self.noise_floor = 0.001  
        
        logger.info(f"[Normalizer] Target: {target_dB}dBFS, Gain range: {self.min_gain}x - {self.max_gain}x")
    
    def highpass_filter(self, audio: np.ndarray, cutoff: int = 80) -> np.ndarray:

        nyq = 0.5 * self.sample_rate
        normal_cutoff = cutoff / nyq
        
        if normal_cutoff >= 1.0:
            logger.warning(f"[HPF] Cutoff {cutoff}Hz too high for {self.sample_rate}Hz, skipping")
            return audio
        
        b, a = butter(2, normal_cutoff, btype='high')
        return lfilter(b, a, audio)
    
    def calculate_rms_speech_only(self, audio: np.ndarray, threshold: float = 0.005) -> float:

        speech = audio[np.abs(audio) > threshold]
        
        if len(speech) == 0:
            return 1e-6  
        
        return np.sqrt(np.mean(speech ** 2))
    
    def soft_clip(self, audio: np.ndarray, threshold: float = 0.95) -> np.ndarray:

        peak = np.max(np.abs(audio))
        
        if peak > threshold:
            logger.debug(f"[Clip] Peak {peak:.3f} > {threshold}, applying soft clip")

            audio = np.tanh(audio * 0.8)
        
        return audio
    
    def normalize(self, audio: np.ndarray) -> tuple[np.ndarray, dict]:

        if len(audio) < self.sample_rate * 0.5:  
            logger.debug("[Normalizer] Audio too short, skipping normalization")
            return audio, {"skipped": True}
        
        audio = self.highpass_filter(audio, cutoff=80)
        
        rms_original = self.calculate_rms_speech_only(audio)
        original_dB = 20 * np.log10(rms_original + 1e-10)

        gain = self.target_rms / rms_original
        gain = np.clip(gain, self.min_gain, self.max_gain)
        
        audio = audio * gain

        audio = self.soft_clip(audio, threshold=0.95)

        rms_after_clip = self.calculate_rms_speech_only(audio)
        final_gain = self.target_rms / rms_after_clip
        audio = audio * final_gain
        
        # Final stats
        final_rms = self.calculate_rms_speech_only(audio)
        final_dB = 20 * np.log10(final_rms + 1e-10)
        peak = np.max(np.abs(audio))

        audio = audio.astype(np.float32, copy=False)
        
        stats = {
            "original_dB": original_dB,
            "final_dB": final_dB,
            "gain_applied": gain,
            "final_peak": peak,
            "duration": len(audio) / self.sample_rate
        }
        
        # Log if significant gain applied
        if gain > 2.0 or gain < 0.5:
            logger.info(f"[Normalizer] Gain: {gain:.2f}x ({20*np.log10(gain):+.1f}dB), "
                       f"{original_dB:.1f}dB → {final_dB:.1f}dB")
        
        return audio, stats


class AdaptiveNormalizer:
    def __init__(self, target_dB: float = -20.0, sample_rate: int = 16000):
        self.base_normalizer = WhisperAudioNormalizer(target_dB, sample_rate)
        
        # Adaptive parameters
        self.rms_history = []
        self.max_history = 50  
        self.noise_floor = 0.001
        self.noise_floor_updated = False
    
    def update_noise_floor(self, audio: np.ndarray):
        """
        Update noise floor estimate based on quiet segments
        """
        rms = np.sqrt(np.mean(audio ** 2))
        self.rms_history.append(rms)
        
        if len(self.rms_history) > self.max_history:
            self.rms_history.pop(0)
        
        # Update noise floor every 10 segments
        if len(self.rms_history) >= 10 and len(self.rms_history) % 10 == 0:
            # Noise floor = 20th percentile of RMS history
            sorted_rms = sorted(self.rms_history)
            self.noise_floor = sorted_rms[len(sorted_rms) // 5]
            self.noise_floor_updated = True
            
            logger.info(f"[Adaptive] Updated noise floor: {self.noise_floor:.4f} "
                       f"({20*np.log10(self.noise_floor):.1f}dBFS)")
    
    def normalize(self, audio: np.ndarray) -> tuple[np.ndarray, dict]:

        # Update noise floor estimate
        self.update_noise_floor(audio)
        
        # Use base normalizer
        normalized, stats = self.base_normalizer.normalize(audio)
        
        # Add adaptive info to stats
        stats["noise_floor"] = self.noise_floor
        stats["adaptive"] = self.noise_floor_updated
        
        return normalized, stats