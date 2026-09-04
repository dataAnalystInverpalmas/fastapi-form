#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/app/logs"
mkdir -p "$LOG_DIR"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

mount_smb() {
  local server="${SMB_SERVER:-172.10.18.2}"
  local share="${SMB_SHARE:-produc}"
  local mount_root="${SMB_MOUNT_ROOT:-/mnt/smb}"
  local mount_path="${SMB_MOUNT_PATH:-$mount_root/$share}"
  local username="${SMB_USERNAME:-}"
  local password="${SMB_PASSWORD:-}"
  local domain="${SMB_DOMAIN:-}"
  local options="${SMB_OPTIONS:-username=,uid=1000,gid=1000,vers=3.0,iocharset=utf8,sec=ntlm}"

  mkdir -p "$mount_root" "$mount_path"
  log "Intentando montar $server/$share en $mount_path"

  local credentials_file="/tmp/.smbcredentials"
  : > "$credentials_file"
  chmod 600 "$credentials_file"

  if [[ -n "$username" ]]; then
    printf 'username=%s\npassword=%s\ndomain=%s\n' "$username" "$password" "$domain" > "$credentials_file"
  fi

  if mount -t cifs -o "credentials=$credentials_file,$options" "//$server/$share" "$mount_path"; then
    log "Montaje SMB completado correctamente"
    return 0
  fi

  log "El montaje SMB falló; se continuará con la ejecución local" 
  return 1
}

healthcheck_mount() {
  local mount_path="${SMB_MOUNT_PATH:-/mnt/smb/produc}"
  if mountpoint -q "$mount_path"; then
    log "El share sigue montado en $mount_path"
    return 0
  fi
  log "El share NO está montado en $mount_path"
  return 1
}

mount_smb || true

if healthcheck_mount; then
  log "Montaje verificado; se procede a iniciar FastAPI"
else
  log "No se pudo verificar el montaje; se inicia la aplicación en modo local (si los archivos no están disponibles, fallarán con mensajes claros)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
