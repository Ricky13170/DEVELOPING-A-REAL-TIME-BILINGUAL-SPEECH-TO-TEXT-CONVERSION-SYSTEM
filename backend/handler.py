import json
import base64
import asyncio
import numpy as np
import time
import re
from datetime import datetime
from backend.config import (
    SAMPLE_RATE, MAX_SEGMENT_SEC, OVERLAP_SEC, SILENCE_LIMIT,
    MIN_DECODE_SEC, AGREEMENT_N, HALLUCINATION_HISTORY_SIZE,
    ENABLE_BARTPHO, BARTPHO_ADAPTER, BARTPHO_DEVICE,
    GROQ_API_KEY, AUTO_SUMMARY_MIN_DURATION,
)
from backend.asr import WhisperASR, StreamingASRProcessor
from backend.translation import NLLBTranslator
from backend.bartpho_corrector import BARTphoCorrector
from backend.groq_service import GroqService
from backend.vad import VADManager
from backend.speech_segment_buffer import SpeechSegmentBuffer
from backend.local_agreement import LocalAgreement
from backend.hallucination_filter import HallucinationFilter

class ASRService:
    """Service manages shared models across sessions"""
    def __init__(self):
        self.asr = None
        self.translator = None
        self.corrector = None
        self.groq = None
        self.is_initialized = False

    async def init(self):
        loop = asyncio.get_event_loop()
        
        print("[Model] Loading Whisper...")
        self.asr = WhisperASR(
            model_size="large-v3",
            language="vi",
            device="cuda",
            cache_dir="/cache/whisper"
        )
        self.asr.load_model()
        
        # Load BARTpho Corrector
        if ENABLE_BARTPHO:
            t0 = time.time()
            print("[Model] Loading BARTpho Corrector...")
            self.corrector = BARTphoCorrector(
                adapter_id=BARTPHO_ADAPTER,
                device=BARTPHO_DEVICE,
                cache_dir="/cache/huggingface",
            )
            await loop.run_in_executor(None, self.corrector.load_model)
            print(f"[Model] BARTpho loaded in {time.time() - t0:.1f}s")
        else:
            print("[Model] BARTpho disabled (ENABLE_BARTPHO=False)")
        
        print("[Model] Loading NLLB Translator...")
        self.translator = NLLBTranslator(
            model_name="facebook/nllb-200-3.3B",
            src_lang="vie_Latn",
            tgt_lang="eng_Latn",
            device="cuda",
            cache_dir="/cache/nllb"
        )
        await loop.run_in_executor(None, self.translator.load_model)
        
        print("[Model] Initializing Groq LLM...")
        self.groq = GroqService()
        self.groq.init()
        
        self.is_initialized = True
        print("[Model] All models ready")

    def create_session(self):
        return ASRSession(self)


class ASRSession:
    
    def __init__(self, service: ASRService):
        self.service = service
        self.out_queue = asyncio.Queue()
        self.vad = VADManager(device="cuda")
        self.vad.load() 
        self.segmenter = SpeechSegmentBuffer(
            sample_rate=SAMPLE_RATE,
            max_sec=MAX_SEGMENT_SEC,
            overlap_sec=OVERLAP_SEC,
            silence_limit=SILENCE_LIMIT
        )
        self.agreement = LocalAgreement(n=AGREEMENT_N)
        self.hallucination_filter = HallucinationFilter(
            history_size=HALLUCINATION_HISTORY_SIZE
        )
        
        # Session state
        self.is_recording = False
        self.session_start = None
        self.segment_id = 0
        self.last_stable = ""
        self.pending_partial_text = None      
        self.pending_partial_time = None      
        self.PARTIAL_FINALIZE_TIMEOUT = 3.0 
        
        # Language config
        self.do_translate = True
        
        # Context priming (Groq)
        self.topic = ""
        self.initial_prompt = ""
        self.all_transcripts = []  # Collect transcripts for summary
        
        self.transcript_history = [] 
        
        print("[Session] Initialized with segment-based architecture")

    async def handle_incoming(self, message: str):
        """Route incoming WebSocket messages"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            if msg_type == "start":
                await self._handle_start(data)
            elif msg_type == "audio":
                await self._handle_audio(data)
            elif msg_type == "stop":
                await self._handle_stop()
            elif msg_type == "summarize":
                await self._handle_summarize()
            elif msg_type == "ping":
                await self.out_queue.put(json.dumps({"type": "pong"}))
                
        except Exception as e:
            print(f"[Handler] Error: {e}")

    @staticmethod
    def _sanitize_topic(topic: str) -> str:
        """Sanitize user-provided topic input"""
        if not topic:
            return ""
        topic = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', topic)
        return topic.strip()[:200]

    async def _handle_start(self, data):
        """Start recording session"""
        print("[Session] START")
        
        self.topic = self._sanitize_topic(data.get("topic", ""))
        self.is_recording = True
        self.session_start = datetime.now()
        self.segment_id = 0
        self.last_stable = ""
        self.all_transcripts = []
        self.initial_prompt = ""
        
        # Reset all components
        self.vad.reset()
        self.segmenter.reset()
        self.agreement.reset()
        self.hallucination_filter.reset()
        self.transcript_history = []  
        
        # === Context Priming ===
        base_prompt = (
            "AI, ML, deep learning, machine learning, NLP, ChatGPT, GPT, "
            "Gemini, OpenAI, Google, transformer, neural network, LLM, "
            "computer vision, robotics, Python, TensorFlow, PyTorch, "
            "dataset, token, model, fine-tuning, pre-training, embedding, "
            "attention, inference, GPU, API, framework, server, deploy"
        )
        
        if self.topic and self.service.groq and self.service.groq.is_available:
            try:
                await self.out_queue.put(json.dumps({
                    "type": "log", "level": "info",
                    "message": "Generating keywords from topic..."
                }))
                keywords = await self.service.groq.expand_keywords(
                    self.topic, language="vi"
                )
                if keywords:
                    self.initial_prompt = base_prompt + ", " + keywords
                    print(f"[Context] Primed with: {self.initial_prompt[:80]}...")
                else:
                    self.initial_prompt = base_prompt
            except Exception as e:
                print(f"[Context] Keyword expansion failed: {e}")
                self.initial_prompt = base_prompt
        else:
            self.initial_prompt = base_prompt
        
        if self.topic:
            print(f"[Session] Topic: {self.topic[:40]}")
        
        await self.out_queue.put(json.dumps({
            "type": "status",
            "status": "started",
            "topic": self.topic,
            "primed": bool(self.initial_prompt)
        }))

    async def _handle_audio(self, data):
        """Process incoming audio chunk"""
        if not self.is_recording:
            return
        
        if self.pending_partial_text and self.pending_partial_time:
            if time.time() - self.pending_partial_time > self.PARTIAL_FINALIZE_TIMEOUT:
                await self._finalize_pending_partial()

        # Decode audio
        audio_b64 = data.get("audio", "")
        if not audio_b64:
            return
        
        try:
            audio_bytes = base64.b64decode(audio_b64)
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio = audio_int16.astype(np.float32) / 32768.0
        except Exception as e:
            print(f"[Audio] Decode error: {e}")
            return
        
        rms = np.sqrt(np.mean(audio ** 2))
        

        if rms < 0.003:
            is_speech = False
        else:
            is_speech = self.vad.is_speech(audio)

        now_ts = (datetime.now() - self.session_start).total_seconds()
        result = self.segmenter.process(audio, is_speech, now_ts)
        
        if result is None:

            buffer_duration = self.segmenter.get_current_duration()
            
            if (buffer_duration >= 2.0 and 
                now_ts - getattr(self, '_last_intermediate_decode', 0) > 1.5):
                
                self._last_intermediate_decode = now_ts
                current_audio = self.segmenter.get_current_audio()
                
                if len(current_audio) > 16000:
                    asyncio.create_task(
                        self._decode_intermediate(current_audio)
                    )
            
            return 
        
        kind, chunk = result
        duration = len(chunk) / SAMPLE_RATE
        
        print(f"\n🧩 Segment → {kind.upper()} | {duration:.2f}s")
        
        await self._decode_segment(chunk, is_final=(kind == "final"))

    async def _decode_segment(self, audio: np.ndarray, is_final: bool):
        """Decode audio segment with hallucination filtering and local agreement"""
        
        duration = len(audio) / SAMPLE_RATE
        
        if not is_final and duration < MIN_DECODE_SEC:
            print("⚠️ Skip PARTIAL (too short)")
            return
        
        loop = asyncio.get_event_loop()
        start = time.time()
        
        prompt = self._build_prompt()
        
        text, conf = await loop.run_in_executor(
            None,
            self.service.asr.transcribe,
            audio,
            prompt 
        )
        
        inference_ms = int((time.time() - start) * 1000)
        
        if not text:
            return

        audio_rms = np.sqrt(np.mean(audio ** 2))
        is_hallu, reason = self.hallucination_filter.is_hallucination(
            text, audio_rms, conf
        )
        
        if is_hallu:
            print(f"⚠️ Hallucination filtered: {reason}")
            return
        
        print(f"\n📝 {'FINAL' if is_final else 'PARTIAL'} [VI] {text}")
        
        if is_final:

            if self.pending_partial_text:
                await self._finalize_pending_partial()

            stable_text = text
            unstable_text = ""
            self.segment_id += 1
            self.last_stable = stable_text
            self.agreement.reset()
            
            # BARTpho syllable correction (FINAL segments only)
            pp_time = 0.0
            if (self.service.corrector
                and self.service.corrector.is_loaded):
                loop = asyncio.get_event_loop()
                pp_start = time.time()
                corrected = await loop.run_in_executor(
                    None, self.service.corrector.correct, stable_text
                )
                pp_time = time.time() - pp_start
                if corrected and corrected != stable_text:
                    print(f"[PP] \"{stable_text[:40]}\" → \"{corrected[:40]}\" ({pp_time:.2f}s)")
                    stable_text = corrected
            
            # Collect transcript for summary
            self.all_transcripts.append(stable_text)
            
            self.transcript_history.append(stable_text)
            if len(self.transcript_history) > 3:
                self.transcript_history.pop(0)
        else:
            # PARTIAL: Apply local agreement
            stable_text, unstable_text = self.agreement.process(text)
            pp_time = 0.0
            
            self.pending_partial_text = f"{stable_text} {unstable_text}".strip()
            self.pending_partial_time = time.time()

        display_text = f"{stable_text} {unstable_text}".strip()
        
        await self.out_queue.put(json.dumps({
            "type": "transcript",
            "segment_id": self.segment_id + (0 if is_final else 1),
            "source": display_text,
            "target": "",
            "is_final": is_final,
            "confidence": conf,
            "processing_ms": inference_ms,
            "timestamp": self._get_timestamp()
        }))
        
        if is_final and self.do_translate and stable_text:
            asyncio.create_task(self._translate(stable_text, self.segment_id))

    async def _translate(self, text: str, seg_id: int):
        """Translate Vietnamese to English"""
        loop = asyncio.get_event_loop()
        
        try:
            start = time.time()
            translated = await loop.run_in_executor(
                None,
                self.service.translator.translate,
                text
            )
            duration = time.time() - start
            
            if translated:
                print(f"[MT] #{seg_id} ({duration:.1f}s): {translated[:60]}...")
                await self.out_queue.put(json.dumps({
                    "type": "transcript",
                    "segment_id": seg_id,
                    "source": text,
                    "target": translated,
                    "is_final": True,
                    "confidence": 1.0
                }))
        except Exception as e:
            print(f"[MT] Error: {e}")

    async def _handle_stop(self):
        """Stop recording session"""
        print("[Session] STOP")
        
        self.is_recording = False
        session_duration = (datetime.now() - self.session_start).total_seconds() if self.session_start else 0
        
        await self.out_queue.put(json.dumps({
            "type": "status",
            "status": "stopped",
            "segments": self.segment_id
        }))
        
        # Auto Summary via Groq (if session > 2 minutes)
        if (session_duration >= AUTO_SUMMARY_MIN_DURATION
            and self.all_transcripts
            and self.service.groq
            and self.service.groq.is_available):
            await self.out_queue.put(json.dumps({
                "type": "log", "level": "info",
                "message": "Generating lecture summary..."
            }))
            asyncio.create_task(self._generate_summary())

    async def _handle_summarize(self):
        """Handle manual summarize request from client"""
        if not self.all_transcripts:
            await self.out_queue.put(json.dumps({
                "type": "log", "level": "warning",
                "message": "No transcripts to summarize"
            }))
            return
        
        if not self.service.groq or not self.service.groq.is_available:
            await self.out_queue.put(json.dumps({
                "type": "log", "level": "error",
                "message": "Summary service not available"
            }))
            return
        
        await self.out_queue.put(json.dumps({
            "type": "log", "level": "info",
            "message": "Generating summary..."
        }))
        await self._generate_summary()
    
    async def _generate_summary(self):
        """Generate lecture summary via Groq (async, non-blocking)"""
        try:
            full_transcript = "\n".join(self.all_transcripts)
            summary = await self.service.groq.summarize_lecture(
                full_transcript, topic=self.topic
            )
            
            if summary:
                await self.out_queue.put(json.dumps({
                    "type": "summary",
                    "summary": summary,
                    "topic": self.topic,
                    "segments_count": self.segment_id,
                }))
                print(f"[Summary] Generated ({len(summary)} chars)")
        except Exception as e:
            print(f"[Summary] Generation failed: {e}")

    async def _finalize_pending_partial(self):
        """Auto-finalize pending partial after timeout"""
        if not self.pending_partial_text:
            return
    
        print(f"⏰ Auto-finalize pending partial: {self.pending_partial_text[:50]}...")
    
        self.segment_id += 1
        self.last_stable = self.pending_partial_text
    
        await self.out_queue.put(json.dumps({
            "type": "transcript",
            "segment_id": self.segment_id,
            "source": self.pending_partial_text,
            "target": "",
            "is_final": True,  
            "confidence": 0.8,
            "timestamp": self._get_timestamp()
        }))
    
        # Trigger translation
        if self.do_translate:
            asyncio.create_task(self._translate(self.pending_partial_text, self.segment_id))
    
        # Clear pending
        self.pending_partial_text = None
        self.pending_partial_time = None
        self.agreement.reset()

    def _get_timestamp(self) -> str:
        """Get current session timestamp in MM:SS format"""
        if not self.session_start:
            return "00:00"
        
        elapsed = (datetime.now() - self.session_start).total_seconds()
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        return f"{mins:02d}:{secs:02d}"
    
    def _build_prompt(self) -> str:
        """
        Build Whisper prompt from initial_prompt (Groq keywords) + recent history.
        This significantly improves accuracy by providing context.
        """
        parts = []
        
        # Add Groq-generated keywords as base context
        if self.initial_prompt:
            parts.append(self.initial_prompt)
        
        # Add recent transcript history
        if self.transcript_history:
            recent = " ".join(self.transcript_history[-2:])
            if len(recent) > 150:
                recent = recent[-150:]
            parts.append(recent)
        
        return ", ".join(parts) if parts else None
    
    async def _decode_intermediate(self, audio: np.ndarray):
        """
        Intermediate partial decode for live feedback.
        Less strict filtering than regular partials.
        """
        loop = asyncio.get_event_loop()
        
        try:
            prompt = self._build_prompt()
            text, conf = await loop.run_in_executor(
                None,
                self.service.asr.transcribe,
                audio,
                prompt
            )
            
            if text and len(text) > 10: 
                # Apply local agreement
                stable_text, unstable_text = self.agreement.process(text)
                display_text = f"{stable_text} {unstable_text}".strip()
                
                await self.out_queue.put(json.dumps({
                    "type": "transcript",
                    "segment_id": self.segment_id + 1,
                    "source": display_text,
                    "target": "",
                    "is_final": False,
                    "confidence": conf,
                    "timestamp": self._get_timestamp()
                }))
        except Exception as e:
            print(f"[Intermediate] Error: {e}")