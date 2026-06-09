# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="MRDTech"
LABEL description="NOC Dashboard v2 — interactive React + FastAPI homelab NOC dashboard"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY collectors/ ./collectors/
COPY themes/ ./themes/
COPY dashboard.yaml .

# Bake in the default layout (seeded on first run if state volume is empty)
COPY state/layout.json /app/default_layout.json

# Pull built React app from stage 1
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

RUN mkdir -p /app/state /app/output

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
