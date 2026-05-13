from __future__ import annotations

import os
from typing import Optional, Tuple, Dict, Any, List

from dbfread import DBF

from app.core.settings import settings


def normalize_path(file_path: str) -> str:
    """
    Normaliza la ruta del archivo, especialmente para rutas UNC de red.

    - Recorta espacios
    - Si viene como `\servidor\share\...` lo convierte a `\\servidor\share\...`
    - Normaliza `/` a `\` cuando aplica
    """
    file_path = (file_path or "").strip()

    # Si parece UNC pero solo trae un "\" inicial, lo convertimos a "\\"
    if file_path.startswith("\\") and not file_path.startswith("\\\\"):
        file_path = "\\" + file_path

    # Para rutas no-UNC, convertir "/" a "\"
    if not file_path.startswith("\\\\"):
        file_path = file_path.replace("/", "\\")

    return file_path


def read_dbf_file(file_path: str, limit: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Lee un archivo DBF y retorna:
    - data: dict con fields/records/total_records/displayed_records
    - error: str (si hubo error)
    """
    try:
        file_path = normalize_path(file_path)

        if not os.path.exists(file_path):
            if file_path.startswith("\\\\"):
                dir_path = os.path.dirname(file_path)
                if not os.path.exists(dir_path):
                    return None, (
                        f"El directorio no es accesible: {dir_path}. "
                        "Verifique la conexión de red y los permisos."
                    )
                return None, (
                    f"El archivo no existe en: {file_path}. "
                    "Verifique que el archivo esté disponible en la red."
                )
            return None, f"El archivo no existe: {file_path}"

        encodings = settings.DBF_ENCODINGS
        table = None
        encoding_used = "latin1"
        last_error = None

        for encoding in encodings:
            try:
                table = DBF(file_path, encoding=encoding)
                encoding_used = encoding
                break
            except Exception as e:
                last_error = e

        if table is None:
            return None, f"Error al leer el archivo DBF. Último error: {last_error}"

        field_names = [field.name for field in table.fields]

        records: List[Dict[str, Any]] = []
        for i, record in enumerate(table):
            if limit and i >= limit:
                break
            records.append(dict(record))

        # Contar total: re-iteramos la tabla
        total_table = DBF(file_path, encoding=encoding_used)
        total_count = sum(1 for _ in total_table)

        return {
            "fields": field_names,
            "records": records,
            "total_records": total_count,
            "displayed_records": len(records),
        }, None

    except Exception as e:
        return None, f"Error al leer el archivo: {e}. Ruta intentada: {file_path}"

