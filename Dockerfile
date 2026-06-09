FROM python:3.12-slim

LABEL maintainer="MRDTech"
LABEL description="NOC Dashboard — YAML-configurable homelab NOC dashboard"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Output directory
RUN mkdir -p /app/output /app/state

# Entrypoint script
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8081

ENTRYPOINT ["/entrypoint.sh"]
