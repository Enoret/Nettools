# =========================================
#  NetTools - All-in-One Docker Image
#  Backend (FastAPI) + Frontend (Nginx)
# =========================================

FROM python:3.12-slim AS backend-build

WORKDIR /app

# Install Python dependencies first (cacheable layer)
COPY docker/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =========================================
FROM python:3.12-slim

LABEL maintainer="NetTools"
LABEL description="NetTools - Network Monitor & Speed Test"
LABEL org.opencontainers.image.source="https://github.com/mbraut/nettools"

# Install system dependencies (network tools + nginx + Ookla speedtest)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    arp-scan \
    nmap \
    iputils-ping \
    net-tools \
    traceroute \
    dnsutils \
    curl \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install official Ookla Speedtest CLI
RUN ARCH=$(dpkg --print-architecture) && \
    case "$ARCH" in \
        amd64) OOKLA_ARCH="x86_64" ;; \
        arm64) OOKLA_ARCH="aarch64" ;; \
        armhf) OOKLA_ARCH="armhf" ;; \
        i386)  OOKLA_ARCH="i386" ;; \
        *)     OOKLA_ARCH="x86_64" ;; \
    esac && \
    curl -sL "https://install.speedtest.net/app/cli/ookla-speedtest-1.2.0-linux-${OOKLA_ARCH}.tgz" -o /tmp/speedtest.tgz && \
    tar xzf /tmp/speedtest.tgz -C /tmp/ && \
    cp /tmp/speedtest /usr/local/bin/speedtest && \
    chmod +x /usr/local/bin/speedtest && \
    rm -rf /tmp/speedtest* && \
    echo "Ookla Speedtest CLI installed"

# Copy Python packages from build stage
COPY --from=backend-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-build /usr/local/bin /usr/local/bin

# Setup backend
WORKDIR /app
COPY docker/backend/*.py .
COPY docker/backend/requirements.txt .

# Setup frontend
COPY nettools/ /usr/share/nginx/html/

# Nginx configuration
COPY docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf
# Remove default nginx site to avoid conflicts
RUN rm -f /etc/nginx/sites-enabled/default

# Create data directory
RUN mkdir -p /data

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables
ENV NETTOOLS_DB_PATH=/data/nettools.db
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Madrid

# Expose port (nginx)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

# Volume for persistent data
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
