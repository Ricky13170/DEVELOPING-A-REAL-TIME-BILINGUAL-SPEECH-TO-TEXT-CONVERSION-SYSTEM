import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).parent))

from modal import App, Image, asgi_app, Volume, enter, Secret
from backend.config import (
    MODAL_APP_NAME, 
    MODAL_GPU, 
    MODAL_MEMORY, 
    MODAL_TIMEOUT, 
    MODAL_CONTAINER_IDLE_TIMEOUT, 
    WHISPER_MODEL
)

app = App(MODAL_APP_NAME)

image = (
    Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1")
    .pip_install(
        "torch>=2.0.0",
        "torchaudio>=2.0.0",
        extra_options="--index-url https://download.pytorch.org/whl/cu124"
    )
    # Transformers ecosystem
    .pip_install(
        "transformers>=4.35.0",
        "accelerate>=0.25.0",
        "sentencepiece>=0.1.99",
    )
    # WhisperX (includes faster-whisper + pyannote VAD)
    .pip_install("whisperx")
    # Web server
    .pip_install(
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "websockets>=12.0",
        "aiofiles>=23.0.0",
    )

    .pip_install(
        "numpy>=1.24.0",
        "scipy>=1.11.0",
        "soundfile>=0.12.0",
    )
    # Utilities
    .pip_install("safetensors>=0.4.0", "protobuf>=3.20.0")
    # Post-processing (BARTpho syllable correction)
    .pip_install("peft>=0.7.0")
    # LLM (Groq API for context priming + summary)
    .pip_install("groq>=0.4.0")
    # Add project files
    .add_local_dir("backend", remote_path="/root/backend")
    .add_local_dir("frontend", remote_path="/root/frontend")
)

cache = Volume.from_name("asr-model-cache", create_if_missing=True)


@app.cls(
    gpu=MODAL_GPU,
    memory=MODAL_MEMORY,
    timeout=MODAL_TIMEOUT,
    scaledown_window=MODAL_CONTAINER_IDLE_TIMEOUT,
    image=image,
    volumes={"/cache": cache},
    secrets=[Secret.from_name("groq-api-key")],
)
class ASR:
    @enter()
    def setup(self):
        """
        Container initialization.
        Loads models on container startup for zero cold-start latency.
        """
        import sys
        import os
        import time
        import asyncio
        
        sys.path.append("/root")
        os.environ["HF_HOME"] = "/cache/huggingface"
        
        # Apply PyTorch patches for WhisperX/pyannote compatibility
        from backend.torch_patch import apply_torch_load_patch
        apply_torch_load_patch()
        
        print("[Container] Initializing segment-based ASR system (WhisperX)...")
        start = time.time()
        
        from backend.handler import ASRService
        
        self.service = ASRService()
        asyncio.run(self.service.init())
        
        elapsed = time.time() - start
        print(f"[Container] ✓ Ready in {elapsed:.1f}s")
        print(f"[Container] Model: {WHISPER_MODEL} | GPU: {MODAL_GPU}")
        print(f"[Container] Architecture: Segment-based with adaptive VAD")

    @asgi_app()
    def app(self):
        """
        ASGI application factory.
        Creates FastAPI app with WebSocket support for real-time ASR.
        """
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import JSONResponse
        from starlette.middleware.base import BaseHTTPMiddleware
        import time
        import asyncio

        web_app = FastAPI(
            title="ASR Streaming System",
            version="6.0",  
            description="Real-time Vietnamese ASR with segment-based architecture"
        )
        
        
        class NoCacheMiddleware(BaseHTTPMiddleware):
            """Prevent browser caching of frontend assets"""
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                if request.url.path.endswith(('.js', '.css', '.html')):
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                    response.headers["Pragma"] = "no-cache"
                    response.headers["Expires"] = "0"
                return response
        
        web_app.add_middleware(NoCacheMiddleware)
        web_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ============================
        # Server state
        # ============================
        
        start_time = time.time()
        conn_count = [0]  

        # ============================
        # REST API Endpoints
        # ============================
        
        @web_app.get("/api/status")
        async def status():
            """Health check and system info"""
            return JSONResponse({
                "status": "online",
                "version": "6.1",
                "architecture": "segment-based",
                "model": WHISPER_MODEL,
                "gpu": MODAL_GPU,
                "uptime_seconds": int(time.time() - start_time),
                "features": [
                    "adaptive_vad",
                    "segment_buffering",
                    "local_agreement",
                    "hallucination_filter",
                    "bartpho_correction",
                    "groq_llm"
                ]
            })

        @web_app.post("/api/expand-keywords")
        async def expand_keywords(request: Request):
            """Expand lecture topic into keywords using Groq LLM"""
            try:
                body = await request.json()
                topic = body.get("topic", "").strip()
                
                if not topic:
                    return JSONResponse({"error": "No topic provided"}, status_code=400)
                
                if not self.service.groq or not self.service.groq.is_available:
                    return JSONResponse({"error": "Groq service not available"}, status_code=503)
                
                keywords = await self.service.groq.expand_keywords(topic)
                return JSONResponse({"keywords": keywords, "topic": topic})
                
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        @web_app.post("/api/generate-context")
        async def generate_context(request: Request):
            """Generate keywords + context paragraph from topic using Groq LLM"""
            try:
                body = await request.json()
                topic = body.get("topic", "").strip()
                
                if not topic:
                    return JSONResponse({"error": "No topic provided"}, status_code=400)
                
                if not self.service.groq or not self.service.groq.is_available:
                    return JSONResponse({"error": "Groq service not available"}, status_code=503)
                
                result = await self.service.groq.generate_context(topic)
                return JSONResponse({**result, "topic": topic})
                
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        @web_app.post("/api/summarize")
        async def summarize(request: Request):
            """Summarize transcript text using Groq LLM"""
            try:
                body = await request.json()
                text = body.get("text", "").strip()
                topic = body.get("topic", "").strip()
                language = body.get("language", "en").strip()

                if not text:
                    return JSONResponse({"error": "No text provided"}, status_code=400)

                if not self.service.groq or not self.service.groq.is_available:
                    return JSONResponse({"error": "Groq service not available"}, status_code=503)

                summary_raw = await self.service.groq.summarize_lecture(text, topic, language=language)
                return JSONResponse({"summary": summary_raw.strip(), "topic": topic})

            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        @web_app.post("/api/qa")
        async def qa(request: Request):
            """Answer questions about transcript using Groq LLM"""
            try:
                body = await request.json()
                question = body.get("question", "").strip()
                transcript = body.get("transcript", "").strip()
                topic = body.get("topic", "").strip()

                if not question or not transcript:
                    return JSONResponse({"error": "Question and transcript required"}, status_code=400)

                if not self.service.groq or not self.service.groq.is_available:
                    return JSONResponse({"error": "Groq service not available"}, status_code=503)

                answer = await self.service.groq.answer_question(transcript, question, topic)
                return JSONResponse({"answer": answer})

            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        @web_app.post("/api/translate")
        async def translate_text(request: Request):
            """Translate text using NLLB model"""
            try:
                body = await request.json()
                text = body.get("text", "").strip()
                src_lang = body.get("src_lang", "eng_Latn").strip()
                tgt_lang = body.get("tgt_lang", "vie_Latn").strip()

                if not text:
                    return JSONResponse({"error": "No text provided"}, status_code=400)

                if not self.service.translator or not self.service.translator.is_loaded:
                    return JSONResponse({"error": "Translation model not available"}, status_code=503)

                import asyncio
                loop = asyncio.get_event_loop()
                translated = await loop.run_in_executor(
                    None,
                    lambda: self.service.translator.translate(text, src_lang=src_lang, tgt_lang=tgt_lang)
                )
                return JSONResponse({"translated": translated})

            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=500)

        # ============================
        # WebSocket Endpoint
        # ============================
        
        @web_app.websocket("/ws/transcribe")
        async def websocket_endpoint(websocket: WebSocket):
            """
            Real-time ASR WebSocket endpoint.
            
            Protocol:
            - Client → Server: {"type": "start|audio|stop|ping"}
            - Server → Client: {"type": "transcript|status|pong"}
            """
            conn_count[0] += 1
            cid = conn_count[0]
            
            await websocket.accept()
            print(f"[WS #{cid}] ✓ Connected")
            
            session = self.service.create_session()
            
            async def recv():
                """Receive messages from client"""
                try:
                    while True:
                        msg = await websocket.receive_text()
                        await session.handle_incoming(msg)
                except WebSocketDisconnect:
                    print(f"[WS #{cid}] Client disconnected")
                except Exception as e:
                    print(f"[WS #{cid}] Recv error: {e}")

            async def send():
                """Send messages to client"""
                try:
                    while True:
                        msg = await session.out_queue.get()
                        await websocket.send_text(msg)
                except Exception as e:
                    print(f"[WS #{cid}] Send error: {e}")

            try:
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(recv()),
                        asyncio.create_task(send())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in pending:
                    task.cancel()
                    
            except Exception as e:
                print(f"[WS #{cid}] Error: {e}")
            finally:
                print(f"[WS #{cid}] ✗ Closed")

        # ============================
        # Static Files (Frontend)
        # ============================
        
        web_app.mount(
            "/", 
            StaticFiles(directory="/root/frontend", html=True), 
            name="frontend"
        )
        
        return web_app
