import os
import sys
import pathlib

sys.path.append(str(pathlib.Path(__file__).parent))
from backend.torch_patch import apply_torch_load_patch
apply_torch_load_patch()

from dotenv import load_dotenv
load_dotenv()  
from transformers import logging
logging.set_verbosity_error()
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
    .pip_install(
        "ctranslate2>=4.5.0",
        "whisperx",
        "lightning",
        "python-dotenv",
        "transformers>=4.35.0",
        "accelerate>=0.25.0",
        "sentencepiece>=0.1.99",
        "safetensors>=0.4.0",
        "protobuf>=3.20.0",
        "peft>=0.7.0",
        "groq>=0.4.0",
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "websockets>=12.0",
        "aiofiles>=23.0.0",
        "numpy>=1.24.0",
        "scipy>=1.11.0",
        "soundfile>=0.12.0",
    )
    .env({
        "LD_LIBRARY_PATH": "/usr/local/lib/python3.11/site-packages/nvidia/cudnn/lib:"
                           "/usr/local/lib/python3.11/site-packages/nvidia/cublas/lib:"
                           "/usr/local/lib/python3.11/site-packages/nvidia/cuda_runtime/lib",
    })
    .run_commands(
        "pip uninstall -y torchcodec 2>/dev/null || true",
        # Run Lightning checkpoint upgrade directly, patching torch.load to bypass weights_only=True
        "python -c \""
        "import torch, sys; "
        "orig_load = torch.load; "
        "torch.load = lambda *a, **k: orig_load(*a, **{**k, 'weights_only': False}); "
        "sys.argv = ['upgrade', '--map-to-cpu', '/usr/local/lib/python3.11/site-packages/whisperx/assets/pytorch_model.bin']; "
        "from lightning.pytorch.utilities.upgrade_checkpoint import main; "
        "main()"
        "\"",
    )
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
    secrets=[Secret.from_dotenv()],  
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
        import warnings

        warnings.filterwarnings("ignore", message=".*not sharded.*")

        sys.path.append("/root")
        os.environ["HF_HOME"] = "/cache/huggingface"

        # Debug: verify secrets are injected
        has_groq = bool(os.environ.get("GROQ_API_KEY"))
        has_hf = bool(os.environ.get("HF_TOKEN"))
        print(f"[Container] Secrets: GROQ_API_KEY={'✓' if has_groq else '✗'} | HF_TOKEN={'✓' if has_hf else '✗'}")

        print("[Container] Initializing ASR system (WhisperX)...")
        start = time.time()

        from backend.handler import ASRService
        self.service = ASRService()
        asyncio.run(self.service.init())

        elapsed = time.time() - start
        print(f"[Container] ✓ Ready in {elapsed:.1f}s | {WHISPER_MODEL} | {MODAL_GPU}")

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
        
        # Middleware
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

        # Server state
        start_time = time.time()
        conn_count = [0]  

        # REST API Endpoints
        
        @web_app.get("/api/status")
        async def status():
            """Health check and system info"""
            return JSONResponse({
                "status": "online",
                "model": WHISPER_MODEL,
                "gpu": MODAL_GPU,
                "uptime_seconds": int(time.time() - start_time),
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

        # WebSocket Endpoint
        
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

            # Run both tasks concurrently
            try:
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(recv()),
                        asyncio.create_task(send())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    
            except Exception as e:
                print(f"[WS #{cid}] Error: {e}")
            finally:
                print(f"[WS #{cid}] ✗ Closed")

        # Static Files (Frontend)
        web_app.mount(
            "/", 
            StaticFiles(directory="/root/frontend", html=True), 
            name="frontend"
        )
        return web_app