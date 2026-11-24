# Multi-stage Dockerfile for NexusOps Control Plane
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root system user for security
RUN groupadd -r nexus && useradd -r -g nexus nexus

# Copy installed wheels and dependencies from builder stage
COPY --from=builder /root/.local /home/nexus/.local
COPY . /app

RUN chown -R nexus:nexus /app /home/nexus
USER nexus

ENV PATH=/home/nexus/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    NEXUSOPS_HOST=0.0.0.0 \
    NEXUSOPS_PORT=8000

EXPOSE 8000

# Healthcheck verifying control plane REST API
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status')" || exit 1

ENTRYPOINT ["python", "-m", "nexusops.main"]
