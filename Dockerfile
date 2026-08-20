# Lightweight CPU runtime for Faster-Whisper + OPUS-MT.
#
# Build the default WebSocket image:
#   docker build -t theduo-edge .
#
# Add optional WebRTC or Groq packages only when required:
#   docker build --build-arg INSTALL_WEBRTC=1 -t theduo-edge:webrtc .
#   docker build --build-arg INSTALL_GROQ=1 -t theduo-edge:groq .

# Python slim avoids CUDA libraries, Conda, and training-only packages.
FROM python:3.11-slim-bookworm

ARG INSTALL_WEBRTC=0
ARG INSTALL_GROQ=0

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/app/model_cache/huggingface \
    TOKENIZERS_PARALLELISM=false \
    ENABLE_GROQ=0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

# Pin the CPU wheel explicitly so this image never pulls CUDA libraries.
RUN python -m pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==2.8.0" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_WEBRTC" = "1" ]; then \
         python -m pip install --no-cache-dir "aiortc>=1.14,<1.16"; \
       fi \
    && if [ "$INSTALL_GROQ" = "1" ]; then \
         python -m pip install --no-cache-dir "groq>=1,<2"; \
       fi \
    && python -m pip check \
    && python -c "import ctranslate2, torch; assert torch.version.cuda is None; print(torch.__version__, ctranslate2.__version__)"

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY main.py ./

RUN mkdir -p /app/model_cache

VOLUME ["/app/model_cache"]
EXPOSE 8000

ENTRYPOINT ["python", "main.py", "--cache-dir", "/app/model_cache"]
