from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import (
    dataframe_to_sql,
    execute_query,
    normalize_finca_series,
    read_many_dbf,
    safe_int_series,
    validate_columns,
)


def _ajustar_a_lunes(fecha: pd.Timestamp) -> pd.Timestamp:
    if pd.isnull(fecha):
        return fecha
    return fecha - pd.Timedelta(days=int(fecha.weekday()))


def _max_fecha_por_tipo(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty or "tipo" not in frame.columns or "fecha" not in frame.columns:
        return {}

    temp = frame[["tipo", "fecha"]].copy()
    temp["fecha"] = pd.to_datetime(temp["fecha"], errors="coerce")
    temp = temp[temp["fecha"].notna()].copy()
    if temp.empty:
        return {}

    result = temp.groupby("tipo", dropna=False)["fecha"].max().sort_index()
    return {str(tipo): pd.Timestamp(value).strftime("%Y-%m-%d") for tipo, value in result.items()}


def _compare_common_tipo_max_fecha(raw_frame: pd.DataFrame, final_frame: pd.DataFrame) -> dict[str, dict[str, str]]:
    raw_max = _max_fecha_por_tipo(raw_frame)
    final_max = _max_fecha_por_tipo(final_frame)
    common_types = sorted(set(raw_max) & set(final_max))
    comparison = {
        "raw": {tipo: raw_max[tipo] for tipo in common_types},
        "final": {tipo: final_max[tipo] for tipo in common_types},
        "match": all(raw_max[tipo] == final_max[tipo] for tipo in common_types),
    }
    return comparison


def _load_proyecciones_dbf() -> pd.DataFrame:
    df_proy = read_many_dbf(settings.PROYECCIONES_BASE_DIR, settings.PROYECCIONES_DBF_FILES)
    if df_proy.empty:
        raise RuntimeError("No se encontraron datos en archivos Proyecciones*.dbf.")

    required = {
        "finca",
        "flor",
        "bloque",
        "nvari",
        "cosecha",
        "fecha",
        "matas",
        "edad",
        "tipo",
        "tallos",
    }
    validate_columns(df_proy, required, "proyecciones*.dbf")

    df_proy = df_proy[
        ["finca", "flor", "bloque", "nvari", "cosecha", "fecha", "matas", "edad", "tipo", "tallos"]
    ].copy()
    df_proy = df_proy.rename(columns={"nvari": "variedad"})
    df_proy["fecha"] = pd.to_datetime(df_proy["fecha"], errors="coerce")

    return df_proy


def _load_db_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sql_pto = f"""
        SELECT
            pto.finca,
            pto.flor,
            pto.bloque,
            pto.variedad,
            pto.cosecha,
            pto.fecha,
            pto.edad,
            c.nombre AS ncolor,
            SUM(pto.tallos) AS tallos,
            SUM(pto.matas) AS matas
        FROM ld_proyeccion_anual AS pto
        LEFT JOIN ld_variedades AS v
            ON v.nombre = pto.variedad
            AND v.codflor = pto.flor
        LEFT JOIN ld_colores AS c
            ON c.codigo = v.codgcol
        WHERE pto.fecha >= '{settings.PROYECCIONES_BUDGET_START_DATE}'
            AND pto.flor IN ({", ".join(f"'{flor}'" for flor in settings.PROYECCIONES_FLOR_FILTER)})
        GROUP BY 1,2,3,4,5,6,7,8
    """

    rows_pto = execute_query(sql_pto) or []
    df_pto = pd.DataFrame(
        rows_pto,
        columns=["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "edad", "ncolor", "tallos", "matas"],
    )

    rows_vari = execute_query(
        """
        SELECT
            v.nombre AS variedad,
            c.nombre AS ncolor
        FROM ld_variedades AS v
        LEFT JOIN ld_colores AS c ON c.codigo = v.codgcol
        """
    ) or []
    df_vari = pd.DataFrame(rows_vari, columns=["variedad", "ncolor"])

    rows_fiestas = execute_query(
        """
        SELECT
            cod_temporada AS cosecha,
            CONCAT(fiesta, RIGHT(YEAR(fecha_pico), 2)) AS ncosecha
        FROM seasons
        """
    ) or []
    df_fiestas = pd.DataFrame(rows_fiestas, columns=["cosecha", "ncosecha"])

    return df_pto, df_vari, df_fiestas


def generate_proyecciones_csv(debug: bool = False) -> str | tuple[str, dict[str, int]]:
    df_proy = _load_proyecciones_dbf()
    df_pto, df_vari, df_fiestas = _load_db_data()
    audit: dict[str, object] = {}
    audit["dbf_loaded_rows"] = int(len(df_proy))
    audit["tipo_counts_dbf"] = df_proy["tipo"].value_counts(dropna=False).to_dict()
    audit["raw_tipo_max_fecha"] = _max_fecha_por_tipo(df_proy)

    df_proy = pd.merge(df_proy, df_vari, how="left", on="variedad")
    audit["dbf_after_merge_rows"] = int(len(df_proy))

    if not df_pto.empty:
        df_pto["tipo"] = "PT"
        df_pto = df_pto[["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "tipo", "ncolor", "tallos"]]
    audit["db_rows"] = int(len(df_pto))

    df = pd.concat([df_proy, df_pto], ignore_index=True)
    audit["combined_rows"] = int(len(df))

    if df.empty:
        raise RuntimeError("No hay datos para generar proyecciones.csv.")

    df["matas"] = safe_int_series(df["matas"])
    df["tallos"] = safe_int_series(df["tallos"])
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    before_date_filter = int(len(df))
    df = df[df["fecha"].notna()].copy()
    audit["date_valid_rows"] = int(len(df))
    audit["invalid_date_rows_dropped"] = before_date_filter - int(len(df))
    df["fecha"] = df["fecha"].apply(_ajustar_a_lunes)

    for col in ["flor", "variedad", "cosecha", "tipo", "ncolor"]:
        df[col] = df[col].astype(str).str.strip()

    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce").fillna(0).astype("Int64")
    df["finca"] = normalize_finca_series(df["finca"].fillna("000"))
    audit["after_normalization_rows"] = int(len(df))

    group_cols = ["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "edad", "ncolor", "tipo"]
    df_final = (
        df.groupby(group_cols, dropna=False, as_index=False)
        .agg(
            matas=("matas", "sum"),
            tallos=("tallos", "sum"),
        )
        .reset_index(drop=True)
    )
    df_final["matas"] = safe_int_series(df_final["matas"]).round().astype("Int64")
    df_final["tallos"] = safe_int_series(df_final["tallos"]).round().astype("Int64")
    df_final["finca"] = df_final["finca"].astype(str).str.strip()
    df_final["bloque"] = df_final["bloque"].astype(str).str.strip()
    audit["pre_export_rows"] = int(len(df_final))

    df_final = pd.merge(df_final, df_fiestas, on="cosecha", how="left")

    output_path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(output_path, index=False)

    dataframe_to_sql(df_final, "ld_proyecciones", if_exists="replace")

    audit["final_rows"] = int(len(df_final))
    audit["tipo_counts_final"] = df_final["tipo"].value_counts(dropna=False).to_dict()
    audit["final_tipo_max_fecha"] = _max_fecha_por_tipo(df_final)
    audit["common_tipo_max_fecha_compare"] = _compare_common_tipo_max_fecha(df_proy, df_final)

    if debug:
        return str(output_path), audit
    return str(output_path)
