from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def ensure_mount_ready(mount_path: str | None = None) -> tuple[bool, str]:
    target = mount_path or os.getenv("SMB_MOUNT_PATH", "/mnt/smb/produc")
    path = Path(target)
    app_env = os.getenv("APP_ENV", "local").lower()

    if not path.exists():
        if app_env == "docker":
            return True, f"El montaje SMB no está activo; la aplicación sigue operando en modo local Docker en {target}"
        return False, f"El punto de montaje no existe: {target}"

    try:
        result = subprocess.run(["mountpoint", "-q", str(path)], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return True, f"El share sigue montado en {target}"

        if app_env == "docker":
            return True, f"No hay montaje activo en {target}; la aplicación sigue operando en modo local Docker"
        return False, f"No hay montaje activo en {target}"
    except FileNotFoundError:
        logger.warning("mountpoint no está disponible; se omite la verificación")
        return True, "mountpoint no está disponible"
