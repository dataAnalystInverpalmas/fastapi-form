from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

from dbfread import DBF

from app.core.settings import settings
from app.services.utils.pathing import normalize_path_for_runtime


def normalize_path(file_path: str) -> str:
    """Normaliza la ruta del archivo para Windows o para un contenedor Linux."""
    return normalize_path_for_runtime(file_path)


def _open_dbf_table(file_path: str):
    """Abre un archivo DBF con una de las codificaciones soportadas."""
    encodings = settings.DBF_ENCODINGS
    last_error = None
    for encoding in encodings:
        try:
            return DBF(file_path, encoding=encoding), encoding
        except Exception as exc:  # pragma: no cover - manejo de prueba
            last_error = exc
    raise RuntimeError(f"Error al leer el archivo DBF. Último error: {last_error}")


def export_dbf_to_csv(file_path: str, output_dir: str | None = None, limit: Optional[int] = None) -> str:
    """Exporta cualquier DBF a CSV con el nombre del archivo base en la carpeta de Outputs."""
    resolved_path = normalize_path(file_path)
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(f"El archivo no existe: {resolved_path}")

    table, _ = _open_dbf_table(resolved_path)
    field_names = [field.name for field in table.fields]

    target_dir = Path(output_dir or settings.EXCEL_OUTPUT_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    csv_name = f"{Path(resolved_path).stem}.csv"
    output_path = target_dir / csv_name

    with open(output_path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=field_names)
        writer.writeheader()
        for i, record in enumerate(table):
            if limit and i >= limit:
                break
            writer.writerow({key: record.get(key, "") for key in field_names})

    return str(output_path)


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

        table, encoding_used = _open_dbf_table(file_path)
        field_names = [field.name for field in table.fields]

        records: List[Dict[str, Any]] = []
        for i, record in enumerate(table):
            if limit and i >= limit:
                break
            records.append(dict(record))

        total_table, _ = _open_dbf_table(file_path)
        total_count = sum(1 for _ in total_table)

        return {
            "fields": field_names,
            "records": records,
            "total_records": total_count,
            "displayed_records": len(records),
        }, None

    except Exception as e:
        return None, f"Error al leer el archivo: {e}. Ruta intentada: {file_path}"

