# Lightweight CPU runtime for Faster-Whisper + OPUS-MT.
#
# Build the default WebSocket image:
#   docker build -t theduo-edge .
#
# Python slim avoids CUDA libraries, Conda, and training-only packages.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

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
    && python -m pip check \
    && python -c "import ctranslate2, torch; assert torch.version.cuda is None; print(torch.__version__, ctranslate2.__version__)"

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY main.py ./

RUN mkdir -p /app/model_cache

VOLUME ["/app/model_cache"]
EXPOSE 8000

ENTRYPOINT ["python", "main.py"]
