FROM python:3.12-slim

LABEL maintainer="MRDTech"
LABEL description="NOC Dashboard — self-hosted homelab NOC with multi-user auth and TOTP 2FA"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py generate_dashboard.py ./
COPY themes/ ./themes/

RUN mkdir -p /app/output /app/state

ENV PORT=8081 \
    NOC_STATE_DIR=/app/state

EXPOSE 8081

CMD ["python", "server.py"]
