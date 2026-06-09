# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

# Install deps first (cache layer)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --silent

# Copy source and build
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.12-slim

LABEL maintainer="MRDTech"
LABEL description="NOC Dashboard — interactive React + FastAPI homelab NOC dashboard"

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY server.py .
COPY collectors/ ./collectors/
COPY themes/ ./themes/
COPY dashboard.yaml .

# Pull in the built React app from stage 1
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# State + output dirs
RUN mkdir -p /app/state /app/output

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
