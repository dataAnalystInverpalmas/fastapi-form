FROM node:20-bullseye AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/. ./
RUN npm run build

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=docker \
    PYTHONPATH=/app \
    SMB_MOUNT_ROOT=/mnt/smb \
    SMB_MOUNT_PATH=/mnt/smb/produc

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cifs-utils \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p /app/logs /mnt/smb/produc && chown -R appuser:appuser /app /mnt/smb/produc

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["bash", "-lc", "./scripts/entrypoint.sh"]
