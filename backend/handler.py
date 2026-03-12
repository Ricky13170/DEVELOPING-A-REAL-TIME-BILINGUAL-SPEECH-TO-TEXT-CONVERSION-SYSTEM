import json
import base64
import asyncio
import numpy as np
import time
import re
from functools import partial
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from backend.config import (
    SAMPLE_RATE, MAX_SEGMENT_SEC, OVERLAP_SEC, SILENCE_LIMIT,
    MIN_DECODE_SEC, AGREEMENT_N, HALLUCINATION_HISTORY_SIZE,
    GROQ_API_KEY, AUTO_SUMMARY_MIN_DURATION,
    WHISPER_MODEL, WHISPER_LANGUAGE, ASR_DEVICE,
    NLLB_MODEL, NLLB_SRC_LANG, NLLB_TGT_LANG, NLLB_DEVICE,
    MT_FLUSH_TIMEOUT,
)
from backend.asr import WhisperASR
from backend.translation import NLLBTranslator
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
        self.groq = None
        self.is_initialized = False

    async def init(self):
        loop = asyncio.get_event_loop()
        
        print("[Model] Loading Whisper...")
        self.asr = WhisperASR(
            model_size=WHISPER_MODEL,
            language=WHISPER_LANGUAGE,
            device=ASR_DEVICE,
            cache_dir="/cache/whisper"
        )
        self.asr.load_model()
        
        print("[Model] Loading NLLB Translator...")
        self.translator = NLLBTranslator(
            model_name=NLLB_MODEL,
            src_lang=NLLB_SRC_LANG,
            tgt_lang=NLLB_TGT_LANG,
            device=NLLB_DEVICE,
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


# Named executor for Whisper inference (allows concurrent intermediate + final decodes)
_whisper_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper")


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
        
        # Sentence buffer: accumulate final segments, translate on sentence boundary
        self._mt_buffer = []       # list of (text, seg_id)
        self._mt_flush_time = None
        
        # Language config (per-session, overrideable by client)
        self.do_translate = True
        self.src_lang_whisper = WHISPER_LANGUAGE   # Whisper language code (e.g. 'vi', 'en')
        self.tgt_lang_nllb = NLLB_TGT_LANG         # NLLB target code (e.g. 'eng_Latn')
        self.src_lang_nllb = NLLB_SRC_LANG         # NLLB source code (e.g. 'vie_Latn')
        
        # Context priming (Groq)
        self.topic = ""
        self.initial_prompt = ""
        self.all_transcripts = []  # Collect transcripts for summary
        
        self.transcript_history = [] 
        
        # Background task tracking (prevents fire-and-forget leaks)
        self.bg_tasks = set()
        
        print("[Session] Initialized with segment-based architecture")

    def _create_tracked_task(self, coro):
        """Create and track an asyncio task"""
        task = asyncio.create_task(coro)
        self.bg_tasks.add(task)
        task.add_done_callback(self.bg_tasks.discard)
        return task

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
            elif msg_type == "context":
                await self._handle_context(data)
            elif msg_type == "lang_change":
                await self._handle_lang_change(data)
            elif msg_type == "summarize":
                await self._handle_summarize()
            elif msg_type == "ping":
                await self.out_queue.put(json.dumps({"type": "pong"}))
                
        except Exception as e:
            print(f"[Handler] Error: {e}")

    async def _handle_context(self, data):
        """Update context mid-session without restart"""
        topic = self._sanitize_topic(data.get("topic", ""))
        keywords = data.get("keywords", "")
        context = data.get("context", "")

        if topic:
            self.topic = topic

        # Handle keywords: can be string or list
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)

        parts = []
        if keywords:
            parts.append(keywords)
        if context:
            parts.append(context)
        if self.topic and not parts:
            # Expand topic to keywords + context if no explicit ones given
            try:
                result = await self.service.groq.generate_context(self.topic)
                if result.get("keywords"):
                    parts.append(result["keywords"])
                if result.get("context"):
                    parts.append(result["context"])
            except Exception:
                pass

        if parts:
            self.initial_prompt = ", ".join(parts)
            print(f"[Context] Updated mid-session: {self.initial_prompt[:80]}")

        await self.out_queue.put(json.dumps({
            "type": "log", "level": "info",
            "message": "Context updated"
        }))

    @staticmethod
    def _sanitize_topic(topic: str) -> str:
        """Sanitize user-provided topic input"""
        if not topic:
            return ""
        topic = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', topic)
        return topic.strip()[:200]

    async def _handle_lang_change(self, data):
        """Handle mid-session language change from client"""
        src_whisper = data.get("srcLang")
        tgt_nllb = data.get("tgtNllb")
        src_nllb = data.get("srcNllb")
        
        changed = False
        if src_whisper is not None and src_whisper != self.src_lang_whisper:
            self.src_lang_whisper = src_whisper if src_whisper != 'auto' else None
            changed = True
        if src_nllb and src_nllb != self.src_lang_nllb:
            self.src_lang_nllb = src_nllb
            changed = True
        if tgt_nllb and tgt_nllb != self.tgt_lang_nllb:
            self.tgt_lang_nllb = tgt_nllb
            changed = True
        
        if changed:
            print(f"[Session] Language changed: {self.src_lang_whisper or 'auto'} → {self.tgt_lang_nllb} | translate={self.do_translate}")
            await self.out_queue.put(json.dumps({
                "type": "log", "level": "info",
                "message": f"Language switched: {self.src_lang_whisper or 'auto'} → {self.tgt_lang_nllb}"
            }))

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
        
        # === Apply client language selection ===
        src_whisper = data.get("srcLang")  # e.g. 'vi', 'en', None (auto)
        tgt_code = data.get("tgtLang")    # e.g. 'en', 'vi', 'zh'
        tgt_nllb = data.get("tgtNllb")    # e.g. 'eng_Latn' (direct NLLB code)
        src_nllb = data.get("srcNllb")    # e.g. 'vie_Latn'
        do_translate = data.get("translate", True)
        
        if src_whisper is not None:
            self.src_lang_whisper = src_whisper if src_whisper != 'auto' else None
        if tgt_nllb:
            self.tgt_lang_nllb = tgt_nllb
        if src_nllb:
            self.src_lang_nllb = src_nllb
        self.do_translate = do_translate
        
        print(f"[Session] Language: {self.src_lang_whisper or 'auto'} → {self.tgt_lang_nllb} | translate={self.do_translate}")
        
        # Reset all components
        self.vad.reset()
        self.segmenter.reset()
        self.agreement.reset()
        self.hallucination_filter.reset()
        self.transcript_history = []
        self._mt_buffer = []
        self._mt_flush_time = None
        # Cancel previous background tasks
        for task in list(self.bg_tasks):
            task.cancel()
        self.bg_tasks.clear()
        
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
                    "message": "Generating keywords & context from topic..."
                }))
                result = await self.service.groq.generate_context(
                    self.topic, language=self.src_lang_whisper or "vi"
                )
                context_parts = [base_prompt]
                if result.get("keywords"):
                    context_parts.append(result["keywords"])
                if result.get("context"):
                    context_parts.append(result["context"])
                self.initial_prompt = ", ".join(context_parts)
                print(f"[Context] Primed with: {self.initial_prompt[:80]}...")
            except Exception as e:
                print(f"[Context] Context generation failed: {e}")
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

        # Flush sentence buffer if waiting too long
        if self._mt_buffer and self._mt_flush_time:
            if time.time() - self._mt_flush_time > MT_FLUSH_TIMEOUT:
                self._create_tracked_task(self._flush_translation())

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
                    self._create_tracked_task(
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
            _whisper_executor,
            partial(self.service.asr.transcribe,
                    audio, prompt,
                    language=self.src_lang_whisper)
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
            
            # Collect transcript for summary
            self.all_transcripts.append(stable_text)
            
            # Cap array size to prevent memory/context overflow for very long sessions
            total_chars = sum(len(t) for t in self.all_transcripts)
            while total_chars > 20000 and len(self.all_transcripts) > 1:
                removed = self.all_transcripts.pop(0)
                total_chars -= len(removed)
            
            self.transcript_history.append(stable_text)
            if len(self.transcript_history) > 3:
                self.transcript_history.pop(0)
        else:
            # PARTIAL: Apply local agreement
            stable_text, unstable_text = self.agreement.process(text)
            
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
        
        if is_final and stable_text:
            # Buffer for sentence-level translation (wait for complete sentence)
            if self.do_translate:
                self._mt_buffer.append((stable_text, self.segment_id))
                self._mt_flush_time = time.time()
                combined = " ".join(t for t, _ in self._mt_buffer)
                if self._is_sentence_end(combined):
                    self._create_tracked_task(self._flush_translation())

    async def _translate(self, text: str, seg_id: int, source_display: str = None):
        """Translate text and emit result to client"""
        loop = asyncio.get_event_loop()
        
        try:
            start = time.time()
            translated = await loop.run_in_executor(
                None,
                partial(self.service.translator.translate,
                        text,
                        src_lang=self.src_lang_nllb,
                        tgt_lang=self.tgt_lang_nllb)
            )
            duration = time.time() - start
            
            if translated:
                print(f"[MT] #{seg_id} ({duration:.1f}s): {translated[:60]}...")
                await self.out_queue.put(json.dumps({
                    "type": "transcript",
                    "segment_id": seg_id,
                    "source": source_display or text,
                    "target": translated,
                    "is_final": True,
                    "confidence": 1.0
                }))
        except Exception as e:
            print(f"[MT] Error: {e}")

    async def _flush_translation(self):
        """Flush sentence buffer — translate accumulated segments as one unit"""
        if not self._mt_buffer:
            return
        
        items = list(self._mt_buffer)
        self._mt_buffer.clear()
        self._mt_flush_time = None
        
        combined_text = " ".join(t for t, _ in items)
        last_seg_id = items[-1][1]
        last_source = items[-1][0]
        
        if len(items) > 1:
            print(f"[MT] Sentence buffer: merged {len(items)} segments \u2192 translate as one")
        
        await self._translate(combined_text, last_seg_id, source_display=last_source)

    @staticmethod
    def _is_sentence_end(text: str) -> bool:
        """Check if accumulated text ends with sentence-ending punctuation"""
        text = text.rstrip()
        if not text:
            return False
        # Don't treat '...' or '\u2026' as sentence end
        if text.endswith('...') or text.endswith('\u2026'):
            return False
        return text[-1] in '.?!\u3002\uff1f\uff01'

    async def _handle_stop(self):
        """Stop recording session"""
        print("[Session] STOP")
        
        self.is_recording = False
        
        # Flush any remaining partial + sentence buffer before stopping
        if self.pending_partial_text:
            await self._finalize_pending_partial()
        if self._mt_buffer:
            await self._flush_translation()
        
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
            self._create_tracked_task(self._generate_summary())

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
        stable_text = self.pending_partial_text
        self.last_stable = stable_text
    
        await self.out_queue.put(json.dumps({
            "type": "transcript",
            "segment_id": self.segment_id,
            "source": stable_text,
            "target": "",
            "is_final": True,  
            "confidence": 0.8,
            "timestamp": self._get_timestamp()
        }))
    
        # Add to sentence translation buffer
        if self.do_translate:
            self._mt_buffer.append((stable_text, self.segment_id))
            self._mt_flush_time = time.time()
            combined = " ".join(t for t, _ in self._mt_buffer)
            if self._is_sentence_end(combined):
                self._create_tracked_task(self._flush_translation())
    
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
                _whisper_executor,
                partial(self.service.asr.transcribe,
                        audio, prompt,
                        language=self.src_lang_whisper)
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