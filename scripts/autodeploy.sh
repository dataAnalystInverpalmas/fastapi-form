#!/usr/bin/env bash
# Despliegue automatico desde la rama main.
#
# Lo corre cron en el servidor (Ubuntu/WSL) cada pocos minutos. Si hay
# commits nuevos en origin/main:
#   1. actualiza el clon del codigo (solo fast-forward),
#   2. compila una imagen nueva,
#   3. corre las pruebas del backend dentro de esa imagen (sin red),
#   4. espera a que no haya jobs ETL en curso,
#   5. publica la imagen y reinicia la app,
#   6. revisa /health; si la app no responde, vuelve a la imagen anterior.
# Si algo falla, la app sigue con la version que tenia.
#
# Instalacion y uso: deploy/windows-server/LEEME-INSTALACION.md
# ("Despliegue automatico").
set -uo pipefail

REPO_DIR="${REPO_DIR:-$HOME/fastapi-form}"
APP_DIR="${APP_DIR:-$HOME/inverpalmas-portal}"
BRANCH="${BRANCH:-main}"
IMAGE="${IMAGE:-inverpalmas-portal}"
SERVICE="${SERVICE:-fastapi-app}"          # servicio en el docker-compose.yml de APP_DIR
CONTAINER="${CONTAINER:-inverpalmas-portal}"  # su container_name
PORT="${PORT:-8000}"
LOG_FILE="${LOG_FILE:-$APP_DIR/logs/autodeploy.log}"
STATE_DIR="${STATE_DIR:-$APP_DIR/.autodeploy}"

mkdir -p "$(dirname "$LOG_FILE")" "$STATE_DIR"
log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >>"$LOG_FILE"; }

# Una sola ejecucion a la vez (una compilacion puede tardar mas que el intervalo de cron).
exec 9>"$STATE_DIR/lock"
flock -n 9 || exit 0

cd "$REPO_DIR" || { log "ERROR: no existe $REPO_DIR"; exit 1; }

if ! git fetch --quiet origin "$BRANCH" 2>>"$LOG_FILE"; then
  log "ERROR: git fetch fallo (red o credenciales de GitHub)"
  exit 1
fi

target="$(git rev-parse "origin/$BRANCH")"
deployed="$(cat "$STATE_DIR/deployed" 2>/dev/null || true)"
failed="$(cat "$STATE_DIR/failed" 2>/dev/null || true)"

# Nada nuevo, o este mismo commit ya fallo (se reintenta con el siguiente push).
[[ "$target" == "$deployed" ]] && exit 0
[[ "$target" == "$failed" ]] && exit 0

short="${target:0:7}"
fail() { log "FALLO $short: $*"; echo "$target" >"$STATE_DIR/failed"; exit 1; }

log "Nuevo commit en $BRANCH: $short ($(git log -1 --format=%s "$target"))"

# Jobs en curso: no se reinicia (cortaria la corrida). Se intenta en la siguiente vuelta.
if runs="$(curl -fsS --max-time 10 "http://localhost:$PORT/api/etl/runs" 2>/dev/null)"; then
  if grep -Eq '"status": ?"(running|queued)"' <<<"$runs"; then
    log "Hay jobs en curso; se espera a la siguiente vuelta"
    exit 0
  fi
fi

# Actualizar el codigo sin pisar cambios locales del servidor.
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  fail "hay cambios sin commit en $REPO_DIR; revisarlos a mano (git status)"
fi
if [[ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCH" ]]; then
  git checkout --quiet "$BRANCH" 2>>"$LOG_FILE" || fail "no se pudo cambiar a la rama $BRANCH"
fi
git merge --quiet --ff-only "origin/$BRANCH" 2>>"$LOG_FILE" \
  || fail "la rama local $BRANCH se separo de origin; revisarla a mano"

log "Compilando imagen $IMAGE:$short"
docker build --quiet -t "$IMAGE:$short" "$REPO_DIR" >>"$LOG_FILE" 2>&1 || fail "la compilacion fallo"

log "Corriendo pruebas"
if ! docker run --rm --network none --entrypoint python "$IMAGE:$short" \
    -m unittest discover -s app/services/tests -p "test_*.py" >"$STATE_DIR/tests.log" 2>&1; then
  tail -n 40 "$STATE_DIR/tests.log" >>"$LOG_FILE"
  docker rmi "$IMAGE:$short" >/dev/null 2>&1
  fail "fallaron las pruebas (no se desplego)"
fi
log "Pruebas OK: $(grep -E '^Ran ' "$STATE_DIR/tests.log")"

# Guardar la imagen actual para poder volver atras.
docker image inspect "$IMAGE:latest" >/dev/null 2>&1 && docker tag "$IMAGE:latest" "$IMAGE:anterior"
docker tag "$IMAGE:$short" "$IMAGE:latest"

restart_app() {
  (cd "$APP_DIR" && docker compose up -d --force-recreate --no-deps "$SERVICE") >>"$LOG_FILE" 2>&1
}
wait_health() {
  for _ in $(seq 1 36); do
    curl -fsS --max-time 5 "http://localhost:$PORT/health" >/dev/null 2>&1 && return 0
    sleep 5
  done
  return 1
}

log "Reiniciando la app"
restart_app
if wait_health; then
  echo "$target" >"$STATE_DIR/deployed"
  rm -f "$STATE_DIR/failed"
  log "DESPLEGADO $short"
  # Limpiar imagenes de versiones viejas (se conservan latest, anterior y la actual).
  docker images "$IMAGE" --format '{{.Tag}}' \
    | grep -vxE "latest|anterior|$short" \
    | xargs -r -I{} docker rmi "$IMAGE:{}" >/dev/null 2>&1
  exit 0
fi

log "La app no respondio /health; volviendo a la imagen anterior"
docker logs --tail 40 "$CONTAINER" >>"$LOG_FILE" 2>&1
if docker image inspect "$IMAGE:anterior" >/dev/null 2>&1; then
  docker tag "$IMAGE:anterior" "$IMAGE:latest"
  restart_app
  wait_health && log "Version anterior restaurada" || log "ERROR: la version anterior tampoco responde"
fi
fail "la app no arranco con la version nueva"
