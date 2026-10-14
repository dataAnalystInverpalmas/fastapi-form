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

# Un directorio por share de SMB_SHARES (ver settings.SMB_SHARES y
# scripts/entrypoint.sh). Se crean aqui y se ceden a appuser para que el
# montaje quede con su uid/gid (SMB_OPTIONS usa uid=1000,gid=1000) y para
# que la app pueda escribir en los shares de salida.
RUN mkdir -p /app/logs /mnt/smb/produc /mnt/smb/Usuarios /mnt/smb/newfact \
    && chown -R appuser:appuser /app /mnt/smb

# NO se fija USER appuser: el contenedor arranca como root porque montar CIFS
# requiere CAP_SYS_ADMIN (docker-compose ya lo concede con cap_add) y un
# usuario sin privilegios no puede hacerlo. scripts/entrypoint.sh monta los
# shares y luego baja a appuser con setpriv para ejecutar uvicorn, asi que la
# aplicacion sigue corriendo sin privilegios.

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["bash", "-lc", "./scripts/entrypoint.sh"]
