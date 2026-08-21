"""FastAPI application factory shared by local and Modal runtimes."""

from __future__ import annotations

import asyncio
import os
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

import backend.config as cfg
from backend.realtime.webrtc import WebRTCTransport


def create_web_app(
    service,
    frontend_dir: str | os.PathLike[str],
    deployment: str,
    compute_label: str,
) -> FastAPI:
    """Create the HTTP/WebSocket app around an initialized ASR service."""

    deployment_name = deployment.strip().lower() or "unknown"
    web_app = FastAPI(
        title=f"TheDuo Edge - {deployment_name.title()}",
        version=f"7.0-{deployment_name}",
        description="Real-time bilingual speech-to-text",
    )

    class NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            if request.url.path.endswith((".js", ".css", ".html")):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            return response

    web_app.add_middleware(NoCacheMiddleware)
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    start_time = time.time()
    connection_count = 0

    def groq_available() -> bool:
        return bool(service.groq and service.groq.is_available)

    @web_app.get("/api/status")
    async def status():
        webrtc_available = deployment_name == "local" and WebRTCTransport.is_available()
        features = [
            "faster_whisper",
            "adaptive_energy_vad",
            "segment_buffering",
            "local_agreement",
            "hallucination_filter",
            "opus_mt_translation",
            "webrtc_local" if webrtc_available else "websocket_media",
            "groq_extras" if groq_available() else "offline_core",
        ]
        return JSONResponse(
            {
                "status": "online",
                "version": f"7.0-{deployment_name}",
                "deployment": deployment_name,
                "architecture": "segment-based",
                "model": cfg.WHISPER_MODEL,
                "asr_device": cfg.ASR_DEVICE,
                "asr_compute_type": cfg.ASR_COMPUTE_TYPE,
                "translation_models": {
                    "vi_en": cfg.TRANSLATION_MODEL_VI_EN,
                    "en_vi": cfg.TRANSLATION_MODEL_EN_VI,
                },
                "translation_device": cfg.TRANSLATION_DEVICE,
                "sample_rate": cfg.SAMPLE_RATE,
                "audio_send_interval_ms": cfg.AUDIO_SEND_INTERVAL_MS,
                "compute": compute_label,
                "webrtc_available": webrtc_available,
                "uptime_seconds": int(time.time() - start_time),
                "features": features,
            }
        )

    @web_app.post("/api/expand-keywords")
    async def expand_keywords(request: Request):
        try:
            body = await request.json()
            topic = body.get("topic", "").strip()
            if not topic:
                return JSONResponse({"error": "No topic provided"}, status_code=400)
            if not groq_available():
                return JSONResponse({"error": "Groq service not available"}, status_code=503)

            keywords = await service.groq.expand_keywords(topic)
            return JSONResponse({"keywords": keywords, "topic": topic})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @web_app.post("/api/generate-context")
    async def generate_context(request: Request):
        try:
            body = await request.json()
            topic = body.get("topic", "").strip()
            if not topic:
                return JSONResponse({"error": "No topic provided"}, status_code=400)
            if not groq_available():
                return JSONResponse({"error": "Groq service not available"}, status_code=503)

            result = await service.groq.generate_context(topic)
            return JSONResponse({**result, "topic": topic})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @web_app.post("/api/summarize")
    async def summarize(request: Request):
        try:
            body = await request.json()
            text = body.get("text", "").strip()
            topic = body.get("topic", "").strip()
            language = body.get("language", "en").strip()
            if not text:
                return JSONResponse({"error": "No text provided"}, status_code=400)
            if not groq_available():
                return JSONResponse({"error": "Groq service not available"}, status_code=503)

            summary = await service.groq.summarize_lecture(text, topic, language=language)
            return JSONResponse({"summary": summary.strip(), "topic": topic})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @web_app.post("/api/qa")
    async def qa(request: Request):
        try:
            body = await request.json()
            question = body.get("question", "").strip()
            transcript = body.get("transcript", "").strip()
            topic = body.get("topic", "").strip()
            if not question or not transcript:
                return JSONResponse(
                    {"error": "Question and transcript required"},
                    status_code=400,
                )
            if not groq_available():
                return JSONResponse({"error": "Groq service not available"}, status_code=503)

            answer = await service.groq.answer_question(transcript, question, topic)
            return JSONResponse({"answer": answer})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @web_app.post("/api/translate")
    async def translate_text(request: Request):
        try:
            body = await request.json()
            text = body.get("text", "").strip()
            src_lang = body.get("src_lang", "eng_Latn").strip()
            tgt_lang = body.get("tgt_lang", "vie_Latn").strip()
            if not text:
                return JSONResponse({"error": "No text provided"}, status_code=400)
            if not service.translator or not service.translator.is_loaded:
                return JSONResponse(
                    {"error": "Translation model not available"},
                    status_code=503,
                )

            loop = asyncio.get_running_loop()
            translated = await loop.run_in_executor(
                None,
                lambda: service.translator.translate(
                    text,
                    src_lang=src_lang,
                    tgt_lang=tgt_lang,
                ),
            )
            return JSONResponse({"translated": translated})
        except Exception as exc:
            return JSONResponse({"error": str(exc)}, status_code=500)

    @web_app.websocket("/ws/transcribe")
    async def websocket_endpoint(websocket: WebSocket):
        nonlocal connection_count
        connection_count += 1
        connection_id = connection_count

        await websocket.accept()
        print(f"[WS #{connection_id}] connected")
        session = service.create_session()

        async def receive_messages():
            try:
                while True:
                    message = await websocket.receive_text()
                    await session.handle_incoming(message)
            except WebSocketDisconnect:
                print(f"[WS #{connection_id}] client disconnected")
            except Exception as exc:
                print(f"[WS #{connection_id}] receive error: {exc}")

        async def send_messages():
            try:
                while True:
                    message = await session.out_queue.get()
                    await websocket.send_text(message)
            except Exception as exc:
                print(f"[WS #{connection_id}] send error: {exc}")

        receive_task = asyncio.create_task(receive_messages())
        send_task = asyncio.create_task(send_messages())

        try:
            done, pending = await asyncio.wait(
                [receive_task, send_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await asyncio.gather(*done, return_exceptions=True)
        except Exception as exc:
            print(f"[WS #{connection_id}] error: {exc}")
        finally:
            await session.close()
            print(f"[WS #{connection_id}] closed")

    frontend_path = os.fspath(frontend_dir)
    if os.path.isdir(frontend_path):
        web_app.mount(
            "/",
            StaticFiles(directory=frontend_path, html=True),
            name="frontend",
        )

    return web_app
