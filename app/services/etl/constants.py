"""Constantes compartidas entre las capas de rutas ETL."""
from __future__ import annotations

# Jobs que aparecen en el menú 'load' pero son técnicamente jobs ETL.
# Se excluyen del listado principal de ETL para evitar duplicación.
ETL_LOAD_EXTRA_IDS: frozenset[str] = frozenset({
    "load_process_guarde",
    "load_process_siembras",
    "load_siembras_teo_real",
})

# Flujo semanal de proyecciones, EN EL ORDEN EN QUE SE EJECUTA. El modulo
# 'Proyecciones' (dentro de ETL) lista estos jobs en este orden y numera los
# pasos a partir de aqui, en vez de ordenarlos alfabeticamente, para que el
# operador siga la secuencia sin tener que recordarla. Los pasos manuales
# intercalados (descargar la consulta de Tika, subir archivos al sistema de
# cultivo, etc.) viven en manual_before/manual_after de cada job en catalog.py.
PROYECCIONES_JOB_ORDER: tuple[str, ...] = (
    "quipus_vs_proy",
    "planos_proyeccion",
    "planos_proyeccion_hoja1",
    "proyecciones_csv",
)

PROYECCIONES_JOB_IDS: frozenset[str] = frozenset(PROYECCIONES_JOB_ORDER)

# De los jobs del flujo, solo estos se quitan del listado principal de ETL
# Jobs: existen unicamente para proyecciones. quipus_vs_proy y proyecciones_csv
# se quedan tambien en ETL Jobs porque otros flujos (produccion_picos,
# comparaciones Tika, etc.) los consumen y los operadores ya los buscan alli.
PROYECCIONES_ONLY_JOB_IDS: frozenset[str] = frozenset({
    "planos_proyeccion",
    "planos_proyeccion_hoja1",
})
