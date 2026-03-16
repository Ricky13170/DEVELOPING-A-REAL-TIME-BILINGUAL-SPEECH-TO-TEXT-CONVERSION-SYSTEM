import json
import base64
import asyncio
import numpy as np
import time
import re
from datetime import datetime

import difflib
from backend.config import (
    SAMPLE_RATE, MAX_SEGMENT_SEC, OVERLAP_SEC, SILENCE_LIMIT,
    MIN_DECODE_SEC, AGREEMENT_N, HALLUCINATION_HISTORY_SIZE,
    ENABLE_BARTPHO, BARTPHO_ADAPTER, BARTPHO_DEVICE,
    GROQ_API_KEY, AUTO_SUMMARY_MIN_DURATION, OVERLAP_THRESHOLD_DIFF,
    RETRANSLATE_BATCH_SIZE, RETRANSLATE_DELAY_SEC
)
from backend.asr import WhisperASR, StreamingASRProcessor
from backend.translation import NLLBTranslator
from backend.bartpho_corrector import BARTphoCorrector
from backend.groq_service import GroqService
from backend.vad import VADManager
from backend.audio_normalizer import DeepFilterNormalizer
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
        self.denoiser = DeepFilterNormalizer(sample_rate=SAMPLE_RATE)
        
        # Session state
        self.is_recording = False
        self.session_start = None
        self.segment_id = 0
        self.last_stable = ""
        self.pending_partial_text = None      
        self.pending_partial_time = None      
        self.PARTIAL_FINALIZE_TIMEOUT = 3.0
        
        # Overlap deduplication tracking
        self.prev_final_text = None
        self.prev_final_segment_id = None
        self.prev_final_words = []  
        self.prev_final_duration = 0.0 
        
        # Language config
        self.do_translate = True
        self.src_whisper_lang = getattr(self.service.asr, "language", "vi")
        self.src_nllb_lang = getattr(self.service.translator, "src_lang", "vie_Latn")
        self.tgt_nllb_lang = getattr(self.service.translator, "tgt_lang", "eng_Latn")
        
        # Second-pass re-translation buffer
        self._retranslate_buffer = []   
        self._retranslate_task = None 
        
        # Context priming (Groq)
        self.topic = ""
        self.initial_prompt = ""
        self.all_transcripts = [] 
        
        self.transcript_history = [] 
        
        print("[Session] Initialized with segment-based architecture")

    def _apply_language_settings(self, data: dict):
        """Apply runtime language choices from the client without resetting shared models."""
        src_whisper = data.get("srcLang")
        src_nllb = data.get("srcNllb")
        tgt_nllb = data.get("tgtNllb")

        if src_whisper:
            self.src_whisper_lang = src_whisper
        if src_nllb:
            self.src_nllb_lang = src_nllb
        if tgt_nllb:
            self.tgt_nllb_lang = tgt_nllb

        if "translate" in data:
            self.do_translate = bool(data.get("translate"))

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

        # Handle keywords
        if isinstance(keywords, list):
            keywords = ", ".join(keywords)

        parts = []
        if keywords:
            parts.append(keywords)
        if context:
            parts.append(context)
        if self.topic and not parts:

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

    async def _handle_lang_change(self, data):
        """Handle mid-session language change from client"""
        self._apply_language_settings(data)
        
        print(
            f"[Session] Language changed: {self.src_whisper_lang or 'default'} | "
            f"{self.src_nllb_lang} → {self.tgt_nllb_lang}"
        )
        await self.out_queue.put(json.dumps({
            "type": "log", "level": "info",
            "message": f"Language switched in UI."
        }))

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
        self._apply_language_settings(data)
        self.is_recording = True
        self.session_start = datetime.now()
        self.segment_id = 0
        self.last_stable = ""
        self.all_transcripts = []
        self.initial_prompt = ""
        self.prev_final_text = None
        self.prev_final_segment_id = None
        self.prev_final_words = []
        self.prev_final_duration = 0.0
        
        # Reset all components
        self.vad.reset()
        self.segmenter.reset()
        self.agreement.reset()
        self.hallucination_filter.reset()
        self.transcript_history = []
        self._retranslate_buffer = []
        self._retranslate_task = None
        
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
        

        denoised_audio = audio
        if len(audio) >= SAMPLE_RATE * 0.1:
            denoised_audio, stats = self.denoiser.normalize(audio)
            
        # Re-calc RMS on denoised audio
        rms = np.sqrt(np.mean(denoised_audio ** 2))
        
        if rms < 0.003:
            is_speech = False
            speech_prob = 0.0
        else:
            is_speech, speech_prob = self.vad.detect(denoised_audio)
            
        audio = denoised_audio

        now_ts = (datetime.now() - self.session_start).total_seconds()
        result = self.segmenter.process(audio, is_speech, now_ts, speech_prob)
        
        if result is None:

            buffer_duration = self.segmenter.get_current_duration()
            
            if (buffer_duration >= 1.0 and 
                now_ts - getattr(self, '_last_intermediate_decode', 0) > 0.8):
                
                self._last_intermediate_decode = now_ts
                current_audio = self.segmenter.get_current_audio()
                
                if len(current_audio) > 16000:
                    asyncio.create_task(
                        self._decode_intermediate(current_audio)
                    )
            
            return 
        
        kind, chunk = result
        duration = len(chunk) / SAMPLE_RATE
        
        print(f"\n🧩 Segment → {kind.upper()} | {duration:.2f}s | prob={speech_prob:.2f}")
        
        await self._decode_segment(chunk, is_final=(kind == "final"))

    async def _decode_segment(self, audio: np.ndarray, is_final: bool):
        """Decode audio segment with hallucination filtering and local agreement"""
        
        duration = len(audio) / SAMPLE_RATE
        
        if not is_final and duration < MIN_DECODE_SEC:
            print("⚠️ Skip PARTIAL (too short)")
            return
        
        loop = asyncio.get_event_loop()
        start = time.time()
        
        if is_final and self.pending_partial_text:
            self.pending_partial_text = None
            self.pending_partial_time = None
        
        prompt = self._build_prompt()
        
        text, conf, words = await loop.run_in_executor(
            None,
            self.service.asr.transcribe,
            audio,
            prompt,
            None,
            True,
            self.src_whisper_lang,
        )
        
        inference_ms = int((time.time() - start) * 1000)
        
        if not text:
            return

        audio_rms = np.sqrt(np.mean(audio ** 2))
        
        # Log raw Whisper output BEFORE filtering
        print(f"\n🔍 RAW {'FINAL' if is_final else 'PARTIAL'} [conf={conf:.2f} rms={audio_rms:.4f} {inference_ms}ms]: {text}")
        
        is_hallu, reason = self.hallucination_filter.is_hallucination(
            text, audio_rms, conf, is_final=is_final
        )
        
        if is_hallu:
            if reason == "repetition":
                print(f"♻️ Overlap echo detected (reason=repetition). Dropping segment to avoid hallucination loop.")
                return
                
            print(f"⚠️ Hallucination detected: reason={reason} | text='{text[:80]}'")
            
            # Fallback Retry Strategy (Increasing temperatures + No context)
            fallback_temperatures = [0.2, 0.4, 0.6]
            retry_success = False
            
            for i, temp in enumerate(fallback_temperatures):
                print(f"🔄 Retry #{i+1} with temp={temp}, no prompt, no context...")
                retry_start = time.time()
                
                text, conf, words = await loop.run_in_executor(
                    None,
                    self.service.asr.transcribe,
                    audio,
                    None,   
                    temp,    
                    False,
                    self.src_whisper_lang,
                )
                
                retry_ms = int((time.time() - retry_start) * 1000)
                inference_ms += retry_ms
                
                if not text:
                    print(f"🔄 Retry #{i+1}: empty result")
                    continue
                    
                print(f"🔄 Retry #{i+1} [{retry_ms}ms]: {text}")
                
                is_hallu_retry, reason_retry = self.hallucination_filter.is_hallucination(
                    text, audio_rms, conf, is_final=is_final
                )
                
                if not is_hallu_retry:
                    print(f"✅ Retry #{i+1} successful! Escaped hallucination.")
                    retry_success = True
                    break
                else:
                    print(f"⚠️ Retry #{i+1} also hallucinated: {reason_retry}")
            
            if not retry_success:
                keyword_prompt = self._extract_top_keywords(self.prev_final_words, top_k=3)
                if keyword_prompt:
                    print(f"🔄 Retry #4 (keyword-seeded) temp=0.6, prompt='{keyword_prompt}'")
                    retry_start = time.time()
                    
                    text, conf, words = await loop.run_in_executor(
                        None,
                        self.service.asr.transcribe,
                        audio,
                        keyword_prompt,  
                        0.6,            
                        False,
                        self.src_whisper_lang,
                    )
                    
                    retry_ms = int((time.time() - retry_start) * 1000)
                    inference_ms += retry_ms
                    
                    if text:
                        print(f"🔄 Retry #4 [{retry_ms}ms]: {text}")
                        is_hallu_retry, reason_retry = self.hallucination_filter.is_hallucination(
                            text, audio_rms, conf, is_final=is_final
                        )
                        if not is_hallu_retry:
                            print(f"✅ Retry #4 (keyword-seeded) successful!")
                            retry_success = True
                        else:
                            print(f"⚠️ Retry #4 also hallucinated: {reason_retry}")
                    else:
                        print(f"🔄 Retry #4: empty result")
                else:
                    print(f"🔄 Retry #4 skipped: no keywords available from prev final")
                    
            if not retry_success:
                print(f"❌ All fallbacks failed (Hallucination loop). Dropping segment.")
                return
        
        print(f"📝 {'FINAL' if is_final else 'PARTIAL'} [VI] {text}")
        
        if is_final:

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
            
            # Overlap deduplication
            stable_text = await self._trim_overlap_by_threshold(stable_text, words, duration)
            
            # Collect transcript for summary
            self.all_transcripts.append(stable_text)
            
            self.transcript_history.append(stable_text)
            if len(self.transcript_history) > 3:
                self.transcript_history.pop(0)

            # Store for next iteration
            self.prev_final_words = words
            self.prev_final_duration = duration
        else:
            # Apply local agreement
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
        
        # Track this final for overlap dedup with next segment
        if is_final:
            self.prev_final_text = stable_text
            self.prev_final_segment_id = self.segment_id
        
        if is_final and self.do_translate and stable_text:
            asyncio.create_task(self._translate(stable_text, self.segment_id))
            # Queue for second-pass re-translation
            self._queue_retranslate(self.segment_id, stable_text)

    async def _translate(self, text: str, seg_id: int):
        """Translate Vietnamese to English"""
        loop = asyncio.get_event_loop()
        
        try:
            start = time.time()
            translated = await loop.run_in_executor(
                None,
                self.service.translator.translate,
                text,
                self.src_nllb_lang,
                self.tgt_nllb_lang,
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

    def _queue_retranslate(self, seg_id: int, source_text: str):
        """Queue a segment for second-pass batch re-translation."""
        self._retranslate_buffer.append((seg_id, source_text))
        
        # Cancel any pending delayed task
        if self._retranslate_task and not self._retranslate_task.done():
            self._retranslate_task.cancel()
        
        if len(self._retranslate_buffer) >= RETRANSLATE_BATCH_SIZE:
            # Enough segments → schedule after short delay
            self._retranslate_task = asyncio.create_task(
                self._delayed_retranslate(RETRANSLATE_DELAY_SEC)
            )
    
    async def _delayed_retranslate(self, delay: float):
        """Wait then run batch re-translation."""
        try:
            await asyncio.sleep(delay)
            await self._retranslate_batch()
        except asyncio.CancelledError:
            pass
    
    async def _retranslate_batch(self):
        """Second-pass: re-translate buffered segments as a single block for better context."""
        if len(self._retranslate_buffer) < 2:
            return
        
        batch = list(self._retranslate_buffer)
        self._retranslate_buffer.clear()
        
        separator = " ||| "
        seg_ids = [item[0] for item in batch]
        sources = [item[1] for item in batch]
        combined = separator.join(sources)
        
        print(f"\n🔄 [MT-Refine] Re-translating {len(batch)} segments: IDs {seg_ids}")
        
        loop = asyncio.get_event_loop()
        try:
            start = time.time()
            translated_combined = await loop.run_in_executor(
                None,
                self.service.translator.translate,
                combined,
                self.src_nllb_lang,
                self.tgt_nllb_lang,
            )
            duration = time.time() - start
            
            if not translated_combined:
                print(f"[MT-Refine] Empty result, skipping")
                return
            
            # Split back by separator
            parts = translated_combined.split("|||")
            parts = [p.strip() for p in parts if p.strip()]
            
            if len(parts) != len(seg_ids):
                print(f"[MT-Refine] Split mismatch: {len(parts)} parts vs {len(seg_ids)} segments. "
                      f"Falling back to per-segment.")
                # Fallback: if split fails, try to distribute evenly
                if len(parts) == 1:
                    print(f"[MT-Refine] Separator lost in translation. Skipping.")
                    return

                parts = parts[:len(seg_ids)]
            
            print(f"[MT-Refine] Done in {duration:.1f}s:")
            for i, (sid, src) in enumerate(batch):
                if i < len(parts):
                    refined = parts[i]
                    print(f"  #{sid}: {refined[:60]}")
                    await self.out_queue.put(json.dumps({
                        "type": "transcript",
                        "segment_id": sid,
                        "source": src,
                        "target": refined,
                        "is_final": True,
                        "confidence": 1.0,
                        "refined": True
                    }))
                    
        except Exception as e:
            print(f"[MT-Refine] Error: {e}")

    async def _handle_stop(self):
        """Stop recording session"""
        print("[Session] STOP")
        
        self.is_recording = False
        session_duration = (datetime.now() - self.session_start).total_seconds() if self.session_start else 0
        
        # Flush remaining re-translation buffer
        if self.do_translate and len(self._retranslate_buffer) >= 2:
            if self._retranslate_task and not self._retranslate_task.done():
                self._retranslate_task.cancel()
            await self._retranslate_batch()
        
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
    
        # Add to context history so subsequent segments have this context
        self.transcript_history.append(self.pending_partial_text)
        if len(self.transcript_history) > 3:
            self.transcript_history.pop(0)
        self.all_transcripts.append(self.pending_partial_text)
    
        await self.out_queue.put(json.dumps({
            "type": "transcript",
            "segment_id": self.segment_id,
            "source": self.pending_partial_text,
            "target": "",
            "is_final": True,  
            "confidence": 0.8,
            "timestamp": self._get_timestamp()
        }))
    
        # Track for overlap dedup
        self.prev_final_text = self.pending_partial_text
        self.prev_final_segment_id = self.segment_id
    
        # Trigger translation
        if self.do_translate:
            asyncio.create_task(self._translate(self.pending_partial_text, self.segment_id))
            # Queue for second-pass re-translation
            self._queue_retranslate(self.segment_id, self.pending_partial_text)
    
        # Clear pending
        self.pending_partial_text = None
        self.pending_partial_time = None
        self.agreement.reset()

    async def close(self):
        """Release session-level async work on disconnect."""
        self.is_recording = False
        if self._retranslate_task and not self._retranslate_task.done():
            self._retranslate_task.cancel()
            try:
                await self._retranslate_task
            except asyncio.CancelledError:
                pass

    async def _trim_overlap_by_threshold(self, current_text: str, current_words: list, current_duration: float) -> str:
        """Trim overlap by comparing word-level confidence and text similarity in the shared 0.5s window.
           Falls back to string-based trimming if word timestamps are unavailable."""
        if not self.prev_final_text or not current_text:
            return current_text
            

        if not self.prev_final_words or not current_words:

            prev_words_str = self.prev_final_text.split()
            curr_words_str = current_text.split()
            
            max_check = min(6, len(prev_words_str), len(curr_words_str))
            best_overlap_len = 0
            
            for i in range(1, max_check + 1):
                tail = prev_words_str[-i:]
                head = curr_words_str[:i]
                
                # Clean punctuation and lowercase
                tail_clean = [re.sub(r'[^\w\s]', '', w).lower() for w in tail]
                head_clean = [re.sub(r'[^\w\s]', '', w).lower() for w in head]
                
                if tail_clean == head_clean:
                    best_overlap_len = i
            
            if best_overlap_len > 0:
                print(f"[Overlap] Text-based trim. Matched {best_overlap_len} words: {curr_words_str[:best_overlap_len]}")
                new_curr_text = " ".join(curr_words_str[best_overlap_len:]).strip()
                return new_curr_text
            return current_text


        prev_overlap_start = max(0, self.prev_final_duration - OVERLAP_SEC - 0.1)
        curr_overlap_end = OVERLAP_SEC + 0.1
        
        prev_overlap_words = [
            w for w in self.prev_final_words 
            if w.get('end', 0) > prev_overlap_start
        ]
        
        curr_overlap_words = [
            w for w in current_words 
            if w.get('start', 0) < curr_overlap_end
        ]
        
        def calc_avg_conf(word_list):
            if not word_list: return 0.0
            total = sum(w.get('score', 0) for w in word_list if 'score' in w)
            count = sum(1 for w in word_list if 'score' in w)
            return total / count if count > 0 else 0.0
            
        conf_prev = calc_avg_conf(prev_overlap_words)
        conf_curr = calc_avg_conf(curr_overlap_words)
        
        print(f"[Overlap] Threshold check: Prev({len(prev_overlap_words)}w)=C{conf_prev:.2f} vs Curr({len(curr_overlap_words)}w)=C{conf_curr:.2f}")
        
        if not prev_overlap_words or not curr_overlap_words:
            return current_text
            
        prev_str = "".join([w.get('word', '') for w in prev_overlap_words]).strip().lower()
        curr_str = "".join([w.get('word', '') for w in curr_overlap_words]).strip().lower()
        
        similarity = difflib.SequenceMatcher(None, prev_str, curr_str).ratio()
        print(f"[Overlap] Match ratio '{prev_str}' vs '{curr_str}': {similarity:.2f}")
        
        if similarity < 0.4:
            print("[Overlap] Skipped trim: text sequences are too different (not true duplicates).")
            return current_text

        if conf_curr >= conf_prev + OVERLAP_THRESHOLD_DIFF:

            words_to_drop = len(prev_overlap_words)
            prev_text_parts = self.prev_final_text.split()
            
            if words_to_drop < len(prev_text_parts):
                new_prev_text = " ".join(prev_text_parts[:-words_to_drop]).strip()
            else:
                new_prev_text = ""
            
            if new_prev_text and new_prev_text != self.prev_final_text:
                print(f"[Overlap] Prev trimmed (Curr is better). Old: '{self.prev_final_text}' -> New: '{new_prev_text}'")
                
                # Update histories with trimmed version
                if self.all_transcripts and self.all_transcripts[-1] == self.prev_final_text:
                    self.all_transcripts[-1] = new_prev_text
                if self.transcript_history and self.transcript_history[-1] == self.prev_final_text:
                    self.transcript_history[-1] = new_prev_text
                    
                self.prev_final_text = new_prev_text
                
                # Transmit UI rewrite for previous segment
                await self.out_queue.put(json.dumps({
                    "type": "transcript",
                    "segment_id": self.prev_final_segment_id,
                    "source": new_prev_text,
                    "target": "",
                    "is_final": True,
                    "confidence": 1.0, 
                    "timestamp": self._get_timestamp()
                }))
            
            return current_text 
            
        else:
            words_to_drop = len(curr_overlap_words)
            curr_text_parts = current_text.split()
            
            if words_to_drop < len(curr_text_parts):
                new_curr_text = " ".join(curr_text_parts[words_to_drop:]).strip()
            else:
                new_curr_text = ""
            
            if new_curr_text != current_text:
                print(f"[Overlap] Curr trimmed (Prev is better). Old: '{current_text}' -> New: '{new_curr_text}'")
            else:
                 print(f"[Overlap] Curr unchanged.")
                 
            return new_curr_text

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
        Build Whisper initial_prompt with segment-based strategy:
        - First 3 segments: use Groq keywords (vocabulary priming)
        - After that: use transcript context only (more accurate)
        - Always include pending_partial_text for mid-sentence continuity
        """
        # Phase 1: Keywords for vocabulary priming (early segments)
        if self.segment_id < 3:
            parts = []
            if self.initial_prompt:
                parts.append(self.initial_prompt)
            if self.transcript_history:
                recent = " ".join(self.transcript_history[-3:])
                if len(recent) > 400:
                    recent = recent[-400:]
                parts.append(recent)
            return ", ".join(parts) if parts else None
        
        # Phase 2: Context-only (after enough transcripts accumulated)
        context_parts = []
        
        if self.transcript_history:
            recent = " ".join(self.transcript_history[-3:])
            if len(recent) > 400:
                recent = recent[-400:]
            context_parts.append(recent)
        
        # Include pending partial for mid-sentence continuity
        if self.pending_partial_text:
            context_parts.append(self.pending_partial_text)
        
        return " ".join(context_parts) if context_parts else None
    
    def _extract_top_keywords(self, words: list, top_k: int = 3) -> str:
        """Extract top-K highest confidence keywords from word list.
        Falls back to last words from prev_final_text if word-level scores unavailable.
        Used as initial_prompt for keyword-seeded retry to break hallucination loops.
        """
        # Primary: use word-level confidence scores
        if words:
            scored = [w for w in words if 'score' in w and w.get('word', '').strip()]
            if scored:
                scored.sort(key=lambda w: w['score'], reverse=True)
                keywords = [w['word'].strip() for w in scored[:top_k]]
                return ", ".join(keywords)
        
        # Fallback: extract last N words from prev_final_text
        if self.prev_final_text:
            text_words = self.prev_final_text.strip().split()
            if text_words:
                # Take last top_k words as context hint
                keywords = text_words[-top_k:]
                return ", ".join(keywords)
        
        return ""
    
    async def _decode_intermediate(self, audio: np.ndarray):
        """
        Intermediate partial decode for live feedback.
        Less strict filtering than regular partials.
        """
        loop = asyncio.get_event_loop()
        
        try:
            prompt = self._build_prompt()
            text, conf, _ = await loop.run_in_executor(
                None,
                self.service.asr.transcribe,
                audio,
                prompt,
                None,
                True,
                self.src_whisper_lang,
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
