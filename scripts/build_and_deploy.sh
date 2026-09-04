#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "No se encontró .env. Crea uno con SMB_USERNAME, SMB_PASSWORD y variables de base de datos."
  exit 1
fi

docker compose build --no-cache

docker compose up -d --remove-orphans

docker compose ps
