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

# Install system dependencies (network tools + nginx)
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
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from build stage
COPY --from=backend-build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-build /usr/local/bin /usr/local/bin

# Remove pip's speedtest wrapper (conflicts with Ookla binary)
RUN rm -f /usr/local/bin/speedtest /usr/local/bin/speedtest-cli

# Install official Ookla Speedtest CLI
RUN curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash && \
    apt-get install -y speedtest && \
    rm -rf /var/lib/apt/lists/* && \
    speedtest --version && \
    echo "Ookla Speedtest CLI installed"

# Setup backend
WORKDIR /app
COPY docker/backend/*.py .
COPY docker/backend/requirements.txt .

# Setup frontend
COPY nettools/ /usr/share/nginx/html/

# Nginx configuration (template - port replaced at runtime by entrypoint)
COPY docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf.template
# Remove default nginx site to avoid conflicts
RUN rm -f /etc/nginx/sites-enabled/default /etc/nginx/conf.d/default.conf

# Create data directory
RUN mkdir -p /data

# Copy entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Environment variables
ENV NETTOOLS_DB_PATH=/data/nettools.db
ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Madrid
ENV NETTOOLS_PORT=8080
ENV NETTOOLS_BACKEND_PORT=8000

# Expose port (nginx - configurable via NETTOOLS_PORT)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:${NETTOOLS_BACKEND_PORT}/api/health || exit 1

# Volume for persistent data
VOLUME ["/data"]

ENTRYPOINT ["/entrypoint.sh"]
