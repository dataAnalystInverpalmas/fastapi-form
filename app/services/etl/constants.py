"""Constantes compartidas entre las capas de rutas ETL."""
from __future__ import annotations

# Jobs que aparecen en el menú 'load' pero son técnicamente jobs ETL.
# Se excluyen del listado principal de ETL para evitar duplicación.
ETL_LOAD_EXTRA_IDS: frozenset[str] = frozenset({
    "load_process_guarde",
    "load_process_siembras",
    "load_siembras_teo_real",
})

# Jobs que se agrupan en el modulo 'Proyecciones' (dentro de ETL) para
# trabajarlos aparte del listado general de Jobs ETL. Por ahora solo
# planos_proyeccion vive aqui; el resto de jobs relacionados con
# proyecciones (proyecciones_csv, produccion_picos, quipus_vs_proy, etc.)
# se deja en el listado principal de ETL Jobs por ahora.
PROYECCIONES_JOB_IDS: frozenset[str] = frozenset({
    "planos_proyeccion",
})
