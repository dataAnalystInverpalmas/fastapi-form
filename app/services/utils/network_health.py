from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.core.settings import settings
from app.services.utils.pathing import (
    get_configured_shares,
    get_share_mount_path,
    is_docker_runtime,
)

logger = logging.getLogger(__name__)


def is_mounted(mount_path: str) -> tuple[bool, str]:
    """Dice si mount_path es realmente un punto de montaje activo.

    No se disimula un montaje faltante (la version anterior devolvia "ok"
    en Docker aunque no hubiera nada montado): es lo que hace util el
    detalle por share en /health.
    """
    path = Path(mount_path)
    if not path.exists():
        return False, f"No existe el punto de montaje {mount_path}"

    try:
        result = subprocess.run(
            ["mountpoint", "-q", str(path)], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        # Sin el binario 'mountpoint' (p. ej. Windows) no se puede confirmar;
        # que el directorio exista es lo unico verificable.
        logger.warning("mountpoint no está disponible; se omite la verificación de %s", mount_path)
        return True, f"{mount_path} existe (no se pudo verificar el montaje)"

    if result.returncode == 0:
        return True, f"Montado en {mount_path}"
    return False, f"El directorio {mount_path} existe pero no hay un share montado alli"


def check_all_shares() -> tuple[bool, list[dict[str, object]]]:
    """Estado de acceso a cada share de SMB_SHARES.

    Retorna (todos_accesibles, detalle). Se usa en /health para que se vea cual
    share falta cuando un job falla por no encontrar un archivo: antes solo se
    revisaba el share principal (SMB_MOUNT_PATH) y los demas, que ni se
    montaban, fallaban en silencio.

    Que se revisa depende del runtime, porque el acceso es distinto: en el
    contenedor cada share es un montaje CIFS local, y en Windows se llega
    directo por UNC sin montar nada (revisar /mnt/smb alli daria siempre
    "degraded" en una instalacion perfectamente sana).
    """
    detalle: list[dict[str, object]] = []
    todos_ok = True
    en_docker = is_docker_runtime()

    for share in get_configured_shares():
        if en_docker:
            ruta = get_share_mount_path(share).as_posix()
            ok, message = is_mounted(ruta)
        else:
            ruta = f"\\\\{settings.SMB_SERVER}\\{share}"
            ok = Path(ruta).exists()
            message = f"Accesible en {ruta}" if ok else f"No se puede acceder a {ruta}"
        detalle.append({"share": share, "path": ruta, "ok": ok, "message": message})
        todos_ok = todos_ok and ok

    return todos_ok, detalle
