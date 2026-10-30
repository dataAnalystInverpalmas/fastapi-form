#!/usr/bin/env bash
set -euo pipefail

MOUNT_PATH="${SMB_MOUNT_PATH:-/mnt/smb/produc}"
LOG_FILE="/app/logs/smb-monitor.log"
mkdir -p /app/logs

if mountpoint -q "$MOUNT_PATH"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Share activo en $MOUNT_PATH" | tee -a "$LOG_FILE"
  ls -la "$MOUNT_PATH" 2>/dev/null | head -20 | tee -a "$LOG_FILE"
else
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] Share NO disponible en $MOUNT_PATH" | tee -a "$LOG_FILE"
  exit 1
fi
