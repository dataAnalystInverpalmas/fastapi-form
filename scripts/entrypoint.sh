#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/app/logs"
mkdir -p "$LOG_DIR"
# El contenedor arranca como root y uvicorn corre como appuser (ver
# start_app): los logs son un bind mount del host, asi que hay que asegurar
# que el usuario final pueda escribir en ellos.
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R "${APP_USER:-appuser}" "$LOG_DIR" 2>/dev/null || true
fi

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

# Shares del servidor de archivos que la app necesita. Debe coincidir con
# settings.SMB_SHARES: la app traduce \\<servidor>\<share>\... al montaje
# local usando esa lista, asi que un share que no se monte aqui hace fallar
# a los jobs que lo leen (antes solo se montaba "produc" y las rutas de
# Usuarios/newfact fallaban en silencio).
SMB_SHARES="${SMB_SHARES:-produc,Usuarios,newfact}"

# Un share por linea. SMB_SHARES la comparten este script y settings.py, y
# pydantic lee las listas del .env en JSON (["produc","Usuarios"]), asi que
# aqui se aceptan las dos formas: con corchetes/comillas o separada por comas.
list_shares() {
  echo "$SMB_SHARES" | tr -d '[]"'"'" | tr ', ' '\n\n' | sed '/^$/d'
}

# Punto de montaje de un share: el principal (SMB_SHARE) respeta
# SMB_MOUNT_PATH; el resto va a SMB_MOUNT_ROOT/<share>. Misma regla que
# pathing.get_share_mount_path.
share_mount_path() {
  local share="$1"
  local mount_root="${SMB_MOUNT_ROOT:-/mnt/smb}"
  local primary="${SMB_SHARE:-produc}"

  if [[ "${share,,}" == "${primary,,}" && -n "${SMB_MOUNT_PATH:-}" ]]; then
    echo "$SMB_MOUNT_PATH"
  else
    echo "$mount_root/$share"
  fi
}

write_credentials() {
  local credentials_file="$1"
  local username="${SMB_USERNAME:-}"
  local password="${SMB_PASSWORD:-}"
  local domain="${SMB_DOMAIN:-}"

  : > "$credentials_file"
  chmod 600 "$credentials_file"
  if [[ -n "$username" ]]; then
    printf 'username=%s\npassword=%s\ndomain=%s\n' "$username" "$password" "$domain" > "$credentials_file"
  fi
}

mount_share() {
  local share="$1"
  local credentials_file="$2"
  local server="${SMB_SERVER:-172.10.18.2}"
  # nocase: las rutas de settings.py mezclan mayusculas en carpetas
  # (produc/LD_BCULT vs produc/ld_bcult, basetdinamica vs BASETDINAMICA).
  # En Windows es indistinto; en el cliente CIFS de Linux, sin nocase, esas
  # rutas no se encuentran.
  # vers=2.1: dialecto maximo que habla el servidor (con 3.0 devuelve
  # "Operation not supported"). Sin sec=: el usuario y la clave van por el
  # archivo de credenciales, y sec=ntlm (NTLMv1) ya no lo acepta el kernel.
  local options="${SMB_OPTIONS:-uid=1000,gid=1000,vers=2.1,iocharset=utf8,nocase}"
  local mount_path
  mount_path="$(share_mount_path "$share")"

  mkdir -p "$mount_path"

  if mountpoint -q "$mount_path"; then
    log "El share $share ya estaba montado en $mount_path"
    return 0
  fi

  log "Intentando montar //$server/$share en $mount_path"
  if mount -t cifs -o "credentials=$credentials_file,$options" "//$server/$share" "$mount_path"; then
    log "Montaje de $share completado correctamente"
    return 0
  fi

  log "El montaje de $share fallo"
  return 1
}

mount_all_shares() {
  local mount_root="${SMB_MOUNT_ROOT:-/mnt/smb}"
  local credentials_file="/tmp/.smbcredentials"
  local failed=()
  local mounted=()

  mkdir -p "$mount_root"
  write_credentials "$credentials_file"

  local share
  while IFS= read -r share; do
    if mount_share "$share" "$credentials_file"; then
      mounted+=("$share")
    else
      failed+=("$share")
    fi
  done < <(list_shares)

  if [[ ${#mounted[@]} -gt 0 ]]; then
    log "Shares montados: ${mounted[*]}"
  fi
  if [[ ${#failed[@]} -gt 0 ]]; then
    log "Shares NO montados: ${failed[*]}; los jobs que lean esas rutas fallaran"
    return 1
  fi
  return 0
}

healthcheck_mounts() {
  local share mount_path
  local missing=()

  while IFS= read -r share; do
    mount_path="$(share_mount_path "$share")"
    if mountpoint -q "$mount_path"; then
      log "OK: $share montado en $mount_path"
    else
      log "FALTA: $share no esta montado en $mount_path"
      missing+=("$share")
    fi
  done < <(list_shares)

  [[ ${#missing[@]} -eq 0 ]]
}

# Arranca uvicorn como appuser. El contenedor entra como root (montar CIFS
# necesita CAP_SYS_ADMIN, ver Dockerfile), pero la aplicacion no debe correr
# con privilegios: se bajan aqui, despues de montar.
start_app() {
  local run_user="${APP_USER:-appuser}"
  local cmd=(uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2)

  if [[ "$(id -u)" -ne 0 ]]; then
    log "Iniciando FastAPI como $(id -un)"
    exec "${cmd[@]}"
  fi

  if id "$run_user" >/dev/null 2>&1 && command -v setpriv >/dev/null 2>&1; then
    log "Bajando privilegios a $run_user para iniciar FastAPI"
    exec setpriv --reuid "$run_user" --regid "$run_user" --init-groups "${cmd[@]}"
  fi

  log "No se pudo bajar a $run_user; se inicia FastAPI como root"
  exec "${cmd[@]}"
}

mount_all_shares || true

if healthcheck_mounts; then
  log "Todos los shares verificados; se procede a iniciar FastAPI"
else
  log "Faltan shares por montar; se inicia la aplicacion de todas formas (los jobs que dependan de esas rutas fallaran con mensajes claros). Revisa /health para ver cual falta."
fi

start_app
