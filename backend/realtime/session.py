import json
import base64
import asyncio
import numpy as np
import time
import re
import os
from typing import Optional
from datetime import datetime

import difflib
from backend.config import (
    SAMPLE_RATE, MAX_SEGMENT_SEC, OVERLAP_SEC, SILENCE_LIMIT,
    MIN_DECODE_SEC, AGREEMENT_N, HALLUCINATION_HISTORY_SIZE,
    AUTO_SUMMARY_MIN_DURATION, OVERLAP_THRESHOLD_DIFF,
    ENABLE_GROQ, ENABLE_PARTIAL_TRANSCRIPTS, MAX_HALLUCINATION_RETRIES,
    WHISPER_MODEL, WHISPER_LANGUAGE, ASR_DEVICE, ASR_COMPUTE_TYPE,
    TRANSLATION_MODEL_VI_EN, TRANSLATION_MODEL_EN_VI,
    TRANSLATION_SRC_LANG, TRANSLATION_TGT_LANG, TRANSLATION_DEVICE
)
from backend.speech.asr import WhisperASR
from backend.translation import MarianTranslator
from backend.groq_service import GroqService
from backend.speech.vad import VADManager
from backend.speech.speech_segment_buffer import SpeechSegmentBuffer
from backend.speech.local_agreement import LocalAgreement
from backend.speech.hallucination_filter import HallucinationFilter
from backend.realtime.webrtc import WebRTCTransport


class ASRService:
    """Service manages shared models across sessions"""
    def __init__(self):
        self.asr = None
        self.translator = None
        self.groq = None
        self.is_initialized = False

    async def init(self):
        loop = asyncio.get_event_loop()
        
        # Read from config after main.py applies command-line overrides.
        cache_base = os.environ.get("HF_HOME", "/cache/huggingface")
        cache_parent = os.path.dirname(cache_base) if cache_base != "/cache/huggingface" else "/cache"

        print("[Model] Loading Whisper...")
        self.asr = WhisperASR(
            model_size=WHISPER_MODEL,
            language=WHISPER_LANGUAGE,
            device=ASR_DEVICE,
            cache_dir=os.path.join(cache_parent, "whisper"),
            compute_type=ASR_COMPUTE_TYPE,
        )
        self.asr.load_model()
        
        print("[Model] Loading lightweight OPUS-MT translator...")
        self.translator = MarianTranslator(
            vi_en_model=TRANSLATION_MODEL_VI_EN,
            en_vi_model=TRANSLATION_MODEL_EN_VI,
            src_lang=TRANSLATION_SRC_LANG,
            tgt_lang=TRANSLATION_TGT_LANG,
            device=TRANSLATION_DEVICE,
            cache_dir=os.path.join(cache_parent, "translation")
        )
        await loop.run_in_executor(None, self.translator.load_model)
        
        print(f"[Model] Groq extras: {'enabled' if ENABLE_GROQ else 'disabled'}")
        self.groq = GroqService()
        if ENABLE_GROQ:
            self.groq.init()
        
        self.is_initialized = True
        print("[Model] All models ready")

    def create_session(self):
        return ASRSession(self)


class ASRSession:
    
    def __init__(self, service: ASRService):
        self.service = service
        self.out_queue = asyncio.Queue()
        self.vad = VADManager()
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
        # WebRTC transport (initialized on first offer)
        self.webrtc: Optional[WebRTCTransport] = None
        self._background_tasks = set()
        self._translation_tasks = set()
        self._audio_queue = asyncio.Queue(maxsize=128)
        self._audio_worker_task = None
        self._recording_generation = 0
        self._draining_generation = None
        self._audio_drain_timeout = 5.0
        self._translation_drain_timeout = 8.0
        
        # Session state
        self.is_recording = False
        self.session_start = None
        self._processed_samples = 0
        self.segment_id = 0
        self.last_stable = ""
        self.pending_partial_text = None      
        self.pending_partial_time = None      
        self._pending_partial_asr_ms = None
        self._pending_partial_audio_duration_ms = None
        self.PARTIAL_FINALIZE_TIMEOUT = 3.0
        
        # Overlap deduplication tracking
        self.prev_final_text = None
        self.prev_final_segment_id = None
        self.prev_final_words = []  
        self.prev_final_duration = 0.0 
        
        # Language config
        self.do_translate = True
        self.src_whisper_lang = getattr(self.service.asr, "language", "vi")
        self.src_translation_lang = getattr(self.service.translator, "src_lang", "vie_Latn")
        self.tgt_translation_lang = getattr(self.service.translator, "tgt_lang", "eng_Latn")
        
        # Context priming (Groq)
        self.topic = ""
        self.initial_prompt = ""
        self.all_transcripts = [] 
        
        self.transcript_history = [] 
        
        print("[Session] Initialized with segment-based architecture")

    def _create_background_task(self, coro, *, translation: bool = False):
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        if translation:
            self._translation_tasks.add(task)
            task.add_done_callback(self._translation_tasks.discard)
        return task

    async def _cancel_result_tasks(self):
        """Cancel wrappers whose results belong to the previous recording."""
        tasks = set(self._translation_tasks)
        intermediate = getattr(self, "_intermediate_task", None)
        if intermediate and not intermediate.done():
            tasks.add(intermediate)

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._translation_tasks.clear()
        self._intermediate_task = None

    async def _wait_for_translation_tasks(self):
        """Give final translation updates a short, bounded delivery window."""
        tasks = {task for task in self._translation_tasks if not task.done()}
        if not tasks:
            return

        _, pending = await asyncio.wait(
            tasks,
            timeout=self._translation_drain_timeout,
        )
        if pending:
            print(
                f"[MT] {len(pending)} translation(s) still running after "
                f"{self._translation_drain_timeout:.2f}s; dropping their late UI updates"
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await self.out_queue.put(json.dumps({
                "type": "log",
                "level": "warning",
                "message": "Translation timed out for one or more final segments.",
            }))

    def _generation_is_active(self, generation: int) -> bool:
        return generation == self._recording_generation and (
            self.is_recording or self._draining_generation == generation
        )

    def _discard_queued_audio(self):
        """Drop queued chunks while keeping Queue.join accounting balanced."""
        while True:
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                self._audio_queue.task_done()

    def _ensure_audio_worker(self):
        if self._audio_worker_task is None or self._audio_worker_task.done():
            self._audio_worker_task = self._create_background_task(self._audio_worker())

    async def _audio_worker(self):
        while True:
            generation, audio = await self._audio_queue.get()
            try:
                if self._generation_is_active(generation):
                    await self._process_audio_chunk(audio, generation)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # One malformed chunk or failed inference must not kill the
                # worker, otherwise Queue.join() can wait forever on stop.
                print(f"[AudioWorker] Chunk failed: {exc}")
            finally:
                self._audio_queue.task_done()

    async def _enqueue_audio(self, audio: np.ndarray):
        if self.is_recording and len(audio):
            self._ensure_audio_worker()
            generation = self._recording_generation
            await self._audio_queue.put((generation, audio))

    def _apply_language_settings(self, data: dict):
        """Apply runtime language choices from the client without resetting shared models."""
        src_whisper = data.get("srcLang")
        src_translation = data.get("srcTranslation")
        tgt_translation = data.get("tgtTranslation")

        if src_whisper:
            self.src_whisper_lang = src_whisper
        if src_translation:
            self.src_translation_lang = src_translation
        if tgt_translation:
            self.tgt_translation_lang = tgt_translation

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
            elif msg_type == "webrtc_offer":
                await self._handle_webrtc_offer(data)
            elif msg_type == "webrtc_ice":
                await self._handle_webrtc_ice(data)
            elif msg_type == "ping":
                await self.out_queue.put(json.dumps({"type": "pong"}))
                
        except Exception as e:
            print(f"[Handler] Error: {e}")

    # ── WebRTC Signaling ──────────────────────────────────────────

    async def _handle_webrtc_offer(self, data):
        """Handle WebRTC SDP offer from client"""
        sdp = data.get("sdp", "")
        if not sdp:
            return

        if not WebRTCTransport.is_available():
            await self.out_queue.put(json.dumps({
                "type": "webrtc_error",
                "message": "WebRTC not available on server"
            }))
            return

        # Close any existing WebRTC connection
        if self.webrtc:
            await self.webrtc.close()

        self.webrtc = WebRTCTransport(on_audio=self._handle_webrtc_audio)

        try:
            answer_sdp = await self.webrtc.handle_offer(sdp)
            await self.out_queue.put(json.dumps({
                "type": "webrtc_answer",
                "sdp": answer_sdp
            }))
            print("[WebRTC] Offer accepted, answer sent")
        except Exception as e:
            print(f"[WebRTC] Offer handling failed: {e}")
            await self.out_queue.put(json.dumps({
                "type": "webrtc_error",
                "message": str(e)
            }))

    async def _handle_webrtc_ice(self, data):
        """Handle ICE candidate from client"""
        candidate = data.get("candidate")
        if self.webrtc and candidate:
            await self.webrtc.add_ice_candidate(candidate)

    async def _handle_webrtc_audio(self, audio: np.ndarray):
        """Forward normalized WebRTC PCM into the shared ingest path."""
        await self._enqueue_audio(audio.astype(np.float32, copy=False))

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
            f"{self.src_translation_lang} → {self.tgt_translation_lang}"
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

        # Invalidate results from the previous recording before resetting
        # shared session state. Executor work may keep running after cancel,
        # so every result is also guarded by this generation token.
        self.is_recording = False
        self._recording_generation += 1
        self._draining_generation = None
        await self._cancel_result_tasks()
        self._discard_queued_audio()

        self.topic = self._sanitize_topic(data.get("topic", ""))
        self._apply_language_settings(data)
        self.is_recording = True
        self.session_start = datetime.now()
        self._processed_samples = 0
        self.segment_id = 0
        self.last_stable = ""
        self.all_transcripts = []
        self.initial_prompt = ""
        self.prev_final_text = None
        self.prev_final_segment_id = None
        self.prev_final_words = []
        self.prev_final_duration = 0.0
        self.pending_partial_text = None
        self.pending_partial_time = None
        self._pending_partial_asr_ms = None
        self._pending_partial_audio_duration_ms = None
        self._last_intermediate_decode = 0.0
        self._intermediate_task = None
        
        # Reset all components
        self.vad.reset()
        self.segmenter.reset()
        self.agreement.reset()
        self.hallucination_filter.reset()
        self.transcript_history = []
        self._ensure_audio_worker()
        base_prompt = (
            "Vietnamese, English, workplace communication, safety instruction, "
            "emergency, stop, danger, fire, evacuate, PPE, factory, warehouse, "
            "maintenance, inspection, machine, equipment, valve, pump, motor, "
            "sensor, conveyor, PLC, pressure, temperature, voltage, circuit breaker, "
            "dừng lại, nguy hiểm, khẩn cấp, cháy, sơ tán, bảo hộ lao động, "
            "bảo trì, kiểm tra, van, máy bơm, động cơ, cảm biến, băng chuyền"
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
        """Decode WebSocket PCM and forward it into the shared ingest path."""
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

        await self._enqueue_audio(audio)

    async def _process_audio_chunk(self, audio: np.ndarray, generation: int = None):
        """Single VAD/segmentation path shared by WebRTC and WebSocket."""
        generation = self._recording_generation if generation is None else generation
        if (
            not self._generation_is_active(generation)
            or len(audio) == 0
        ):
            return

        if self.pending_partial_text and self.pending_partial_time:
            if time.time() - self.pending_partial_time > self.PARTIAL_FINALIZE_TIMEOUT:
                await self._finalize_pending_partial(generation)

        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.003:
            is_speech, speech_prob = False, 0.0
        else:
            is_speech, speech_prob = self.vad.detect(audio)

        # Drive endpointing from audio time, not wall time. ASR/MT can block the
        # worker while frames queue up; wall time would turn that backlog into
        # fake silence and split otherwise continuous speech.
        self._processed_samples += len(audio)
        now_ts = self._processed_samples / SAMPLE_RATE
        result = self.segmenter.process(audio, is_speech, now_ts, speech_prob)

        if result is None:
            if ENABLE_PARTIAL_TRANSCRIPTS:
                buffer_duration = self.segmenter.get_current_duration()
                previous = getattr(self, "_intermediate_task", None)
                if (
                    buffer_duration >= 1.0
                    and now_ts - getattr(self, "_last_intermediate_decode", 0) > 1.2
                    and (previous is None or previous.done())
                ):
                    self._last_intermediate_decode = now_ts
                    current_audio = self.segmenter.get_current_audio()
                    if len(current_audio) > SAMPLE_RATE:
                        self._intermediate_task = self._create_background_task(
                            self._decode_intermediate(current_audio, generation)
                        )
            return

        kind, chunk = result
        if kind == "partial" and not ENABLE_PARTIAL_TRANSCRIPTS:
            return
        duration = len(chunk) / SAMPLE_RATE
        print(f"\n🧩 Segment → {kind.upper()} | {duration:.2f}s | prob={speech_prob:.2f}")
        await self._decode_segment(
            chunk,
            is_final=(kind == "final"),
            generation=generation,
        )

    async def _decode_segment(
        self,
        audio: np.ndarray,
        is_final: bool,
        generation: int = None,
    ):
        """Decode audio segment with hallucination filtering and local agreement"""
        generation = self._recording_generation if generation is None else generation
        if generation != self._recording_generation:
            return
        
        duration = len(audio) / SAMPLE_RATE
        
        if not is_final and duration < MIN_DECODE_SEC:
            print("⚠️ Skip PARTIAL (too short)")
            return
        
        loop = asyncio.get_event_loop()
        start = time.time()
        
        if is_final and self.pending_partial_text:
            self.pending_partial_text = None
            self.pending_partial_time = None
            self._pending_partial_asr_ms = None
            self._pending_partial_audio_duration_ms = None
        
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

        if generation != self._recording_generation:
            return
        
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
                print("♻️ Repeated output dropped")
                return

            print(f"⚠️ Confidence gate: reason={reason} | text='{text[:80]}'")
            fallback_temperatures = [0.2, 0.4, 0.6][:MAX_HALLUCINATION_RETRIES]
            retry_success = False

            for i, temp in enumerate(fallback_temperatures):
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
                if generation != self._recording_generation:
                    return
                retry_ms = int((time.time() - retry_start) * 1000)
                inference_ms += retry_ms
                if not text:
                    continue

                is_hallu_retry, reason_retry = self.hallucination_filter.is_hallucination(
                    text, audio_rms, conf, is_final=is_final
                )
                if not is_hallu_retry:
                    retry_success = True
                    break

            if not retry_success:
                await self.out_queue.put(json.dumps({
                    "type": "log",
                    "level": "warning",
                    "message": "Low-confidence speech ignored; please repeat.",
                }))
                return
        
        print(f"📝 {'FINAL' if is_final else 'PARTIAL'} [VI] {text}")
        
        if is_final:

            stable_text = text
            unstable_text = ""
            self.segment_id += 1
            self.last_stable = stable_text
            self.agreement.reset()
            
            # Repeated safety commands are intentional; overlap trimming must
            # not erase a second "stop" / "dừng lại" after the filter kept it.
            if not self.hallucination_filter.is_safety_command(stable_text):
                stable_text = await self._trim_overlap_by_threshold(
                    stable_text,
                    words,
                    duration,
                )
            
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
            self.pending_partial_text = f"{stable_text} {unstable_text}".strip()
            self.pending_partial_time = time.time()
            self._pending_partial_asr_ms = inference_ms
            self._pending_partial_audio_duration_ms = int(round(duration * 1000))

        display_text = f"{stable_text} {unstable_text}".strip()
        
        transcript_payload = {
            "type": "transcript",
            "segment_id": self.segment_id + (0 if is_final else 1),
            "source": display_text,
            "target": "",
            "is_final": is_final,
            "confidence": conf,
            "processing_ms": inference_ms,
            "timestamp": self._get_timestamp()
        }
        if is_final:
            transcript_payload["audio_duration_ms"] = int(round(duration * 1000))
            transcript_payload["asr_ms"] = inference_ms
        await self.out_queue.put(json.dumps(transcript_payload))
        
        # Track this final for overlap dedup with next segment
        if is_final:
            self.prev_final_text = stable_text
            self.prev_final_segment_id = self.segment_id
        
        if is_final and self.do_translate and stable_text:
            self._create_background_task(
                self._translate(
                    stable_text,
                    self.segment_id,
                    generation=generation,
                    src_lang=self.src_translation_lang,
                    tgt_lang=self.tgt_translation_lang,
                    asr_ms=inference_ms,
                ),
                translation=True,
            )

    async def _translate(
        self,
        text: str,
        seg_id: int,
        generation: int = None,
        src_lang: str = None,
        tgt_lang: str = None,
        asr_ms: int = None,
    ):
        """Translate Vietnamese to English"""
        generation = self._recording_generation if generation is None else generation
        src_lang = src_lang or self.src_translation_lang
        tgt_lang = tgt_lang or self.tgt_translation_lang
        loop = asyncio.get_event_loop()
        
        try:
            start = time.time()
            translated = await loop.run_in_executor(
                None,
                self.service.translator.translate,
                text,
                src_lang,
                tgt_lang,
            )
            duration = time.time() - start

            if generation != self._recording_generation:
                return

            if translated:
                print(f"[MT] #{seg_id} ({duration:.1f}s): {translated[:60]}...")
                payload = {
                    "type": "transcript",
                    "segment_id": seg_id,
                    "source": text,
                    "target": translated,
                    "is_final": True,
                    "confidence": 1.0,
                    "translation_ms": int(round(duration * 1000)),
                }
                if asr_ms is not None:
                    payload["asr_ms"] = asr_ms
                await self.out_queue.put(json.dumps(payload))
        except Exception as e:
            print(f"[MT] Error: {e}")

    async def _handle_stop(self):
        """Stop recording session"""
        print("[Session] STOP")

        # The WebRTC aggregator may still hold less than one 160 ms chunk.
        # Queue that tail while this recording still accepts audio.
        if self.webrtc:
            await self.webrtc.flush_pending_audio()

        # Stop accepting new frames while allowing already queued frames from
        # this generation to drain in order.
        generation = self._recording_generation
        self.is_recording = False
        self._draining_generation = generation
        try:
            await asyncio.wait_for(
                self._audio_queue.join(),
                timeout=self._audio_drain_timeout,
            )
        except asyncio.TimeoutError:
            print(
                f"[AudioWorker] Drain timed out after {self._audio_drain_timeout:.1f}s; "
                "dropping the remaining queued audio"
            )
            await self.out_queue.put(json.dumps({
                "type": "log",
                "level": "warning",
                "message": "Audio drain timed out; the last queued frames were skipped.",
            }))

            # Invalidate any in-flight result before cancelling its wrapper.
            self._recording_generation += 1
            generation = self._recording_generation
            self._draining_generation = None
            worker = self._audio_worker_task
            if worker and not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
            self._audio_worker_task = None
            self._discard_queued_audio()
            # A worker that died before task_done() can leave Queue.join's
            # private counter poisoned. A fresh queue makes later sessions safe.
            self._audio_queue = asyncio.Queue(maxsize=128)
        else:
            self._draining_generation = None

        # Force the tail still held by the segmenter through one final decode.
        final_audio = self.segmenter.flush()
        if final_audio is not None and len(final_audio) >= SAMPLE_RATE // 2:
            await self._decode_segment(
                final_audio,
                is_final=True,
                generation=generation,
            )

        await self._wait_for_translation_tasks()
        session_duration = (datetime.now() - self.session_start).total_seconds() if self.session_start else 0
        
        await self.out_queue.put(json.dumps({
            "type": "status",
            "status": "stopped",
            "segments": self.segment_id
        }))
        
        # Auto Summary via Groq (if session > 2 minutes)
        if (AUTO_SUMMARY_MIN_DURATION > 0
            and session_duration >= AUTO_SUMMARY_MIN_DURATION
            and self.all_transcripts
            and self.service.groq
            and self.service.groq.is_available):
            await self.out_queue.put(json.dumps({
                "type": "log", "level": "info",
                "message": "Generating lecture summary..."
            }))
            self._create_background_task(self._generate_summary())

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

    async def _finalize_pending_partial(self, generation: int = None):
        """Auto-finalize pending partial after timeout"""
        generation = self._recording_generation if generation is None else generation
        if not self._generation_is_active(generation) or not self.pending_partial_text:
            return
    
        print(f"⏰ Auto-finalize pending partial: {self.pending_partial_text[:50]}...")
    
        self.segment_id += 1
        self.last_stable = self.pending_partial_text
    
        # Add to context history so subsequent segments have this context
        self.transcript_history.append(self.pending_partial_text)
        if len(self.transcript_history) > 3:
            self.transcript_history.pop(0)
        self.all_transcripts.append(self.pending_partial_text)
    
        payload = {
            "type": "transcript",
            "segment_id": self.segment_id,
            "source": self.pending_partial_text,
            "target": "",
            "is_final": True,  
            "confidence": 0.8,
            "timestamp": self._get_timestamp()
        }
        if self._pending_partial_audio_duration_ms is not None:
            payload["audio_duration_ms"] = self._pending_partial_audio_duration_ms
        if self._pending_partial_asr_ms is not None:
            payload["asr_ms"] = self._pending_partial_asr_ms
        await self.out_queue.put(json.dumps(payload))
    
        # Track for overlap dedup
        self.prev_final_text = self.pending_partial_text
        self.prev_final_segment_id = self.segment_id
    
        # Trigger translation
        if self.do_translate:
            self._create_background_task(
                self._translate(
                    self.pending_partial_text,
                    self.segment_id,
                    generation=generation,
                    src_lang=self.src_translation_lang,
                    tgt_lang=self.tgt_translation_lang,
                    asr_ms=self._pending_partial_asr_ms,
                ),
                translation=True,
            )
    
        # Clear pending
        self.pending_partial_text = None
        self.pending_partial_time = None
        self._pending_partial_asr_ms = None
        self._pending_partial_audio_duration_ms = None
        self.agreement.reset()

    async def close(self):
        """Release session-level async work on disconnect."""
        self.is_recording = False
        self._draining_generation = None
        self._recording_generation += 1
        if self.webrtc:
            await self.webrtc.close()
            self.webrtc = None

        tasks = set(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._discard_queued_audio()
        self._background_tasks.clear()
        self._translation_tasks.clear()
        self._audio_worker_task = None

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
    
    async def _decode_intermediate(self, audio: np.ndarray, generation: int = None):
        """
        Intermediate partial decode for live feedback.
        Less strict filtering than regular partials.
        """
        generation = self._recording_generation if generation is None else generation
        if generation != self._recording_generation or not self.is_recording:
            return

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

            if generation != self._recording_generation or not self.is_recording:
                return
            
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
