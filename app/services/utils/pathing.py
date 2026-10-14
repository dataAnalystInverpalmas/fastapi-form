from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from app.core.settings import settings

logger = logging.getLogger(__name__)


def is_docker_runtime() -> bool:
    # APP_ENV se lee del entorno del proceso en vivo (no de settings.APP_ENV,
    # que es un valor cacheado al arrancar) porque esto decide como se
    # resuelven las rutas de red segun el runtime real (Windows local vs
    # contenedor Linux) -- no es una preferencia de negocio editable desde
    # /config, es un hecho de infraestructura del proceso actual.
    return os.getenv("APP_ENV", "").lower() in {"docker", "container"} or os.path.exists("/.dockerenv")


def get_smb_mount_root() -> Path:
    return Path(settings.SMB_MOUNT_ROOT).expanduser()


def get_configured_servers() -> set[str]:
    """Nombres (en minusculas) con los que se conoce al servidor de archivos."""
    servers = {settings.SMB_SERVER.strip().lower()}
    servers.update(
        alias.strip().lower() for alias in (settings.SMB_SERVER_ALIASES or []) if str(alias).strip()
    )
    return {server for server in servers if server}


def get_configured_shares() -> list[str]:
    """Shares que se montan, con el nombre exacto del directorio de montaje.

    SMB_SHARES es texto separado por comas porque la comparte con bash (ver
    settings.SMB_SHARES). Se aceptan igual una lista (si alguien la guarda asi
    desde /config) y la forma JSON ["a","b"], que es como la escribiria quien
    asuma que sigue siendo un campo lista.
    """
    raw = settings.SMB_SHARES
    if isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = str(raw or "").strip().strip("[]").replace(";", ",").split(",")

    return [share for share in (str(value).strip().strip('"').strip("'") for value in values) if share]


def resolve_share_dir(share: str) -> Optional[str]:
    """Traduce el share de una ruta UNC al nombre de su directorio de montaje.

    Compara sin distinguir mayusculas porque las rutas de settings.py mezclan
    'Usuarios' y 'usuarios' (en Windows da igual, en Linux no) y devuelve el
    nombre configurado, que es como entrypoint.sh crea el directorio.
    """
    target = (share or "").strip().lower()
    if not target:
        return None
    for configured in get_configured_shares():
        if configured.lower() == target:
            return configured
    return None


def get_share_mount_path(share: str, *, mount_root: Optional[Path] = None) -> Path:
    """Punto de montaje local de un share del servidor.

    El share principal (SMB_SHARE) respeta SMB_MOUNT_PATH; el resto se monta
    en SMB_MOUNT_ROOT/<share>, igual que en entrypoint.sh.
    """
    mount_root_path = mount_root or get_smb_mount_root()
    share_dir = resolve_share_dir(share) or (share or "").strip()
    if share_dir.lower() == settings.SMB_SHARE.strip().lower() and settings.SMB_MOUNT_PATH:
        return Path(settings.SMB_MOUNT_PATH)
    return mount_root_path / share_dir


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

    mount_root_path = mount_root or get_smb_mount_root()

    if server.lower() in get_configured_servers():
        # Share conocido o no, se resuelve al mismo esquema de montaje: asi una
        # ruta a un share que todavia no esta en SMB_SHARES falla apuntando al
        # lugar correcto (y basta con montarlo) en vez de a una ruta inventada.
        base_path = get_share_mount_path(share, mount_root=mount_root_path)
    else:
        # Otro servidor: se preserva servidor/share bajo la raiz de montajes.
        base_path = mount_root_path / server / share

    resolved_path = base_path.joinpath(*relative_parts) if relative_parts else base_path

    resolved = resolved_path.as_posix()
    logger.info("Resolved network path %s -> %s", candidate, resolved)
    return resolved


def normalize_path_for_runtime(file_path: str) -> str:
    """Normaliza rutas de forma compatible con Windows y Linux."""
    candidate = (file_path or "").strip()
    if not candidate:
        return candidate

    # Rutas UNC en cualquiera de los dos estilos: settings.py mezcla
    # \\servidor\share\... y //servidor/share/... (en Windows ambos sirven,
    # pero en el contenedor las dos tienen que pasar por el montaje).
    if candidate.startswith("\\\\"):
        return resolve_network_path(candidate)
    if candidate.startswith("//"):
        return resolve_network_path("\\\\" + candidate[2:].replace("/", "\\"))

    if is_docker_runtime():
        return candidate.replace("\\", "/")

    return candidate.replace("/", "\\")
