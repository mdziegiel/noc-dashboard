FROM python:3.12-slim

LABEL maintainer="MRDTech"
LABEL description="NOC 2 — static homelab dashboard on port 9900, 15-min cron regen + http.server"

WORKDIR /app

# Generator deps
RUN pip install --no-cache-dir requests pyyaml pywinrm

COPY generate_dashboard.py /app/generate_dashboard.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /app/output

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
