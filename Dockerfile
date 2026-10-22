# One container = the whole RoadPulse website (dashboard + API + models).
# Build:  docker build -t roadpulse .
# Run:    docker run -p 7860:7860 roadpulse   ->  http://localhost:7860

# ---- 1. build the React dashboard
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python backend serving the built dashboard
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
# CPU-only PyTorch keeps the image ~1.5 GB smaller than the default CUDA build
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt
COPY backend/ backend/
COPY scripts/ scripts/
COPY models/ models/
COPY sample_data/ sample_data/
COPY data/eval/ data/eval/
COPY --from=web /web/dist frontend/dist
ENV PORT=7860 YOLO_CONFIG_DIR=/tmp/Ultralytics
EXPOSE 7860
# Seed demo data on start (skipped if already seeded), then serve everything on one port
CMD python scripts/seed.py && cd backend && uvicorn app.main:asgi --host 0.0.0.0 --port ${PORT}
