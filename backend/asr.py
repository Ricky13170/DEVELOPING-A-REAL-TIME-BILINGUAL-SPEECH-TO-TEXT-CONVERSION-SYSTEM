import numpy as np
import logging
from dataclasses import replace as dataclass_replace
from backend.audio_normalizer import AdaptiveNormalizer
from backend.torch_patch import apply_torch_load_patch, suppress_stdout

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class WhisperASR:
    def __init__(self, model_size="large-v3", language=None, device="cuda", cache_dir=None):
        self.model_size = model_size
        self.language = language
        self.device = device
        self.cache_dir = cache_dir
        self.model = None
        
        self.normalizer = AdaptiveNormalizer(target_dB=-20.0, sample_rate=SAMPLE_RATE)
        logger.info("[ASR] WhisperX with adaptive audio normalization enabled")

    def load_model(self):
        if self.model is not None:
            return

        apply_torch_load_patch()
        
        import whisperx
        
        logger.info(f"Loading WhisperX: {self.model_size}")
        
        compute_type = "float16" if self.device == "cuda" else "int8"
        
        with suppress_stdout():
            self.model = whisperx.load_model(
                self.model_size,
                self.device,
                compute_type=compute_type,
                language=self.language,
                asr_options={"without_timestamps": False, "word_timestamps": True},
                vad_options={"vad_onset": 0.01, "vad_offset": 0.01},
            )
        
        logger.info("WhisperX loaded")

    def transcribe(
        self,
        audio: np.ndarray,
        prompt: str = None,
        temperature: float = None,
        condition_on_previous_text: bool = True,
        language: str = None,
    ) -> tuple:
        """Transcribe audio using WhisperX.
        
        Args:
            audio: float32 audio at 16kHz
            prompt: Context prompt (recent transcript history)
            temperature: Sampling temperature (None = use default 0)
            condition_on_previous_text: If True, provide the previous output to the model context.
            
        Returns:
            (text, confidence, words)
        """
        if self.model is None:
            self.load_model()

        effective_language = language or self.language
        
        if len(audio) < 8000:
            return "", 0.0, []
        
        normalized_audio, norm_stats = self.normalizer.normalize(audio)

        if normalized_audio.dtype != np.float32:
            normalized_audio = normalized_audio.astype(np.float32)
        
        original_options = None
        if hasattr(self.model, 'options'):
            overrides = {}
            if prompt:
                overrides['initial_prompt'] = prompt
            if temperature is not None:
                overrides['temperatures'] = [temperature]
            if condition_on_previous_text is False:
                overrides['condition_on_previous_text'] = False
                
            # Anti-hallucination parameters
            overrides['repetition_penalty'] = 1.2
            overrides['no_speech_threshold'] = 0.6
            overrides['compression_ratio_threshold'] = 2.4
                
            if overrides:
                original_options = self.model.options
                self.model.options = dataclass_replace(
                    self.model.options, **overrides
                )
        
        try:
            # Transcribe with WhisperX (batch_size=1 for streaming segments)
            result = self.model.transcribe(
                normalized_audio,
                batch_size=1,
                language=effective_language,
            )
        finally:
            if original_options is not None:
                self.model.options = original_options
        
        # Collect segments, calculate confidence, and collect words
        text_parts = []
        words = []
        total_prob = 0.0
        seg_count = 0
        
        for segment in result.get("segments", []):
            text_parts.append(segment.get("text", "").strip())
            
            # Combine words from all segments
            if "words" in segment:
                words.extend(segment["words"])
                
            if "avg_logprob" in segment:
                total_prob += segment["avg_logprob"]
                seg_count += 1
        
        text = " ".join(text_parts).strip()
        
        # confidence
        if seg_count > 0:
            avg_logprob = total_prob / seg_count
            conf = min(1.0, max(0.0, 1.0 + avg_logprob / 2))
        elif text:
            conf = 0.8
        else:
            conf = 0.0
        
        return text, conf, words


class StreamingASRProcessor:
    """Streaming processor for audio chunks"""
    
    def __init__(self, asr: WhisperASR, context_size: int = 3):
        self.asr = asr
        self.context_size = context_size
        self.audio_buffer = np.array([], dtype=np.float32)
        self.context_history = []

    def init(self):
        self.audio_buffer = np.array([], dtype=np.float32)
        self.context_history = []

    def insert_audio(self, audio: np.ndarray):
        self.audio_buffer = np.concatenate([self.audio_buffer, audio])

    def process_partial(self, prompt: str = None) -> tuple:
        if len(self.audio_buffer) < SAMPLE_RATE:
            return "", 0.0, []
        
        text, conf, words = self.asr.transcribe(self.audio_buffer, prompt)
        return text, conf, words

    def process_final(self, prompt: str = None) -> tuple:
        if len(self.audio_buffer) < 4000:
            self.audio_buffer = np.array([], dtype=np.float32)
            return "", 0.0, []
        
        text, conf, words = self.asr.transcribe(self.audio_buffer, prompt)
        
        if text:
            self.context_history.append(text)
            if len(self.context_history) > self.context_size * 2:
                self.context_history = self.context_history[-self.context_size:]
        
        self.audio_buffer = np.array([], dtype=np.float32)
        return text, conf, words
