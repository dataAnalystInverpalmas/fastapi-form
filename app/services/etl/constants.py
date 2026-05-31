"""Constantes compartidas entre las capas de rutas ETL."""
from __future__ import annotations

# Jobs que aparecen en el menú 'load' pero son técnicamente jobs ETL.
# Se excluyen del listado principal de ETL para evitar duplicación.
ETL_LOAD_EXTRA_IDS: frozenset[str] = frozenset({
    "load_process_guarde",
    "load_process_siembras",
    "load_siembras_teo_real",
})
