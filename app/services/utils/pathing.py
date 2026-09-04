from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_docker_runtime() -> bool:
    return os.getenv("APP_ENV", "").lower() in {"docker", "container"} or os.path.exists("/.dockerenv")


def get_smb_mount_root() -> Path:
    return Path(os.getenv("SMB_MOUNT_ROOT", "/mnt/smb")).expanduser()


def resolve_network_path(file_path: str, *, mount_root: Optional[Path] = None) -> str:
    """Resuelve rutas UNC de red a un punto de montaje local cuando el contenedor corre en Linux."""
    candidate = (file_path or "").strip()
    if not candidate:
        return candidate

    if not candidate.startswith("\\\\"):
        return candidate.replace("\\", "/") if is_docker_runtime() else candidate

    if not is_docker_runtime():
        return candidate

    parts = [part for part in candidate.split("\\") if part]
    if len(parts) < 2:
        return candidate

    server = parts[0]
    share = parts[1]
    relative_parts = parts[2:]

    configured_server = os.getenv("SMB_SERVER", "172.10.18.2").strip().lower()
    configured_share = os.getenv("SMB_SHARE", "produc").strip().lower()
    mount_root_path = mount_root or get_smb_mount_root()

    if server.lower() == configured_server and share.lower() == configured_share:
        base_path = Path(os.getenv("SMB_MOUNT_PATH", str(mount_root_path / configured_share)))
        resolved_path = base_path.joinpath(*relative_parts) if relative_parts else base_path
    elif share.lower() == configured_share or server.lower() == configured_server:
        resolved_path = mount_root_path.joinpath(*relative_parts) if relative_parts else mount_root_path
    else:
        resolved_path = mount_root_path.joinpath(server, share, *relative_parts)

    resolved = resolved_path.as_posix()
    logger.info("Resolved network path %s -> %s", candidate, resolved)
    return resolved


def normalize_path_for_runtime(file_path: str) -> str:
    """Normaliza rutas de forma compatible con Windows y Linux."""
    candidate = (file_path or "").strip()
    if not candidate:
        return candidate

    if candidate.startswith("\\\\"):
        return resolve_network_path(candidate)

    if is_docker_runtime():
        return candidate.replace("\\", "/")

    return candidate.replace("/", "\\")
