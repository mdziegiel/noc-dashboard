FROM python:3.12-slim

LABEL maintainer="MRDTech"
LABEL description="NOC 1 — static homelab dashboard, 15-min cron regen + http.server"

WORKDIR /app

# Generator deps (requests for HTTP collectors, pyyaml for any yaml use, pywinrm for Hyper-V)
RUN pip install --no-cache-dir requests pyyaml pywinrm

# Copy the patched generator (ENV_PATH + OUT_DIR/OUT_FILE override via env vars)
COPY generate_dashboard.py /app/generate_dashboard.py

RUN mkdir -p /app/output

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
