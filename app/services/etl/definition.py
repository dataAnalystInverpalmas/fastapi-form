from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ETLJobDefinition:
    job_id: str
    name: str
    description: str
    allows_parallel: bool
    timeout_seconds: int
    runner: Callable[..., str]
    supports_params: bool = False
    default_params: dict[str, Any] | None = None
    depends_on: list[str] = field(default_factory=list)
    dependency_note: str | None = None
    dependency_group: str | None = None
    flow_group: str | None = None
    weekly_dates: bool = False
    # Pasos manuales que rodean al job (descargar una consulta de Tika,
    # subir un archivo al sistema de cultivo, borrar datos antes de cargar...).
    # El modulo Proyecciones los muestra en el listado y en el modal de
    # ejecucion para que el operador no dependa de recordarlos.
    manual_before: list[str] = field(default_factory=list)
    manual_after: list[str] = field(default_factory=list)
