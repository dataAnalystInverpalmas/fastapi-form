from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryProcessDefinition:
    process_id: str
    name: str
    description: str


QUERY_PROCESSES: list[QueryProcessDefinition] = [
    QueryProcessDefinition(
        process_id="exporta_cortes_lonas",
        name="Exporta Cortes (ld_lonas)",
        description="Exporta a Excel los cortes agrupados por variedad/finca/bloque y semana en un rango de fechas.",
    ),
    QueryProcessDefinition(
        process_id="aportes_ponderados_problemas",
        name="Aportes Ponderados de Problemas",
        description="Calcula aportes ponderados por problema usando ld_lonas y ld_nacional en un rango de fechas.",
    ),
]


def list_query_processes() -> list[QueryProcessDefinition]:
    return QUERY_PROCESSES
