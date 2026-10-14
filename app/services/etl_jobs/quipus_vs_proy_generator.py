from __future__ import annotations

from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd

from app.core.mail import MailNotConfiguredError, send_email
from app.core.settings import settings
from app.services.utils.date_service import date_to_yyww, get_current_iso_week, get_dates_dimension, yyww_to_date
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import (
    dataframe_to_sql,
    execute_query,
    normalize_finca_series,
    safe_int_series,
    validate_columns,
)

logger = logging.getLogger(__name__)

_CUMPLIMIENTO_EMAIL_SUBJECT = "Subir a cumplimiento de proyecciones"
# Guarda la semana (YYWW) del ultimo correo de cumplimiento enviado.
_CUMPLIMIENTO_MARKER_FILENAME = "cumplimiento_khipus_enviado.txt"


def _normalize_column_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_normalize_column_name(col) for col in df.columns]
    return df


def _to_int(series: pd.Series) -> pd.Series:
    return safe_int_series(series).round().astype(int)


def _normalize_text_key(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(" ", "_", regex=False)


def _normalize_nullable_int_key(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def _normalize_finca_code(series: pd.Series) -> pd.Series:
    return normalize_finca_series(series).astype(str)


def _normalize_merge_keys(df: pd.DataFrame, *, int_cols: list[str] | None = None, text_cols: list[str] | None = None) -> pd.DataFrame:
    normalized = df.copy()
    for col in text_cols or []:
        if col in normalized.columns:
            if col == "finca":
                normalized[col] = _normalize_finca_code(normalized[col])
            else:
                normalized[col] = _normalize_text_key(normalized[col])
    for col in int_cols or []:
        if col in normalized.columns:
            normalized[col] = _normalize_nullable_int_key(normalized[col])
    return normalized


def _extract_first_existing(df: pd.DataFrame, candidates: list[str]) -> str:
    for col in candidates:
        if col in df.columns:
            return col
    raise ValueError(f"No se encontro ninguna columna esperada: {candidates}")


def _extraer_dos_digitos(cosecha: str) -> str:
    numeros = re.findall(r"\d+", str(cosecha))
    if not numeros:
        return "00"
    numero = numeros[0]
    if len(numero) == 2:
        return numero
    if len(numero) == 4:
        return numero[:2]
    return "00"


def _load_reference_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sql_variedades = """
        SELECT
            REPLACE(v.nombre, ' ', '_') AS variedad,
            c.nombre AS color
        FROM ld_variedades v
        INNER JOIN ld_colores c ON v.codgcol = c.codigo
        WHERE v.activo = 1
          AND v.codflor IN ('CLA', 'CM0')
    """

    sql_cosechas = """
        SELECT
            c.codigo AS cosecha,
            f.codigo AS fiesta
        FROM ld_cosechas c
        INNER JOIN ld_fiestas f ON f.codigo = c.fiesta
    """

    sql_duplicados = """
        SELECT *
        FROM (
            SELECT
                p.finca,
                p.bloque,
                REPLACE(p.variedad, ' ', '_') AS variedad,
                DATE_FORMAT(p.fecha_siembra, '%y%v') AS semana,
                s.cod_temporada AS cosecha
            FROM plane p
            LEFT JOIN seasons s ON p.temporada = s.nombre
            INNER JOIN (
                SELECT
                    finca,
                    bloque,
                    variedad,
                    DATE_FORMAT(fecha_siembra, '%y%v') AS semana
                FROM plane
                GROUP BY finca, bloque, variedad, DATE_FORMAT(fecha_siembra, '%y%v')
                HAVING COUNT(DISTINCT temporada) > 1
            ) dup ON p.finca = dup.finca
               AND p.bloque = dup.bloque
               AND p.variedad = dup.variedad
               AND DATE_FORMAT(p.fecha_siembra, '%y%v') = dup.semana
            ORDER BY p.finca, p.bloque, p.variedad, semana, s.cod_temporada
        ) subquery
        GROUP BY 1,2,3,4,5
    """

    df_vari = pd.DataFrame(execute_query(sql_variedades) or [], columns=["variedad", "color"])
    df_cose = pd.DataFrame(execute_query(sql_cosechas) or [], columns=["cosecha", "fiesta"])

    duplicated_rows = execute_query(sql_duplicados) or []
    df_dup = pd.DataFrame(
        duplicated_rows,
        columns=["finca", "bloque", "variedad", "semana", "cosecha"],
    )
    if not df_dup.empty:
        df_dup["semana"] = pd.to_numeric(df_dup["semana"], errors="coerce")
        df_dup["bloque"] = pd.to_numeric(df_dup["bloque"], errors="coerce")
        df_dup = _normalize_merge_keys(
            df_dup,
            int_cols=["semana", "bloque"],
            text_cols=["finca", "variedad", "cosecha"],
        )
    return df_vari, df_cose, df_dup


def _load_calendar_mondays() -> pd.DataFrame:
    dates = get_dates_dimension(settings.QUIPUS_DATE_START, settings.QUIPUS_DATE_END)
    mondays = dates[dates["fecha"].dt.dayofweek == 0][["fecha", "aass"]].copy()
    mondays["aass"] = pd.to_numeric(mondays["aass"], errors="coerce").astype("Int64")
    return mondays


def _load_plano_data(semana_actual: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    plano_path = Path(normalize_path(settings.QUIPUS_PLANO_PATH))
    if not plano_path.exists():
        raise FileNotFoundError(f"No existe el archivo de plano: {plano_path}")

    df_plano = pd.read_csv(plano_path, thousands=",", sep=",", low_memory=False)
    df_plano = _normalize_columns(df_plano)

    block_col = _extract_first_existing(df_plano, ["bloque"])
    state_col = _extract_first_existing(df_plano, ["estado"])
    finca_col = _extract_first_existing(df_plano, ["finca"])
    variedad_col = _extract_first_existing(df_plano, ["variedad"])
    semana_col = _extract_first_existing(df_plano, ["semana_siembra", "semana"])

    if block_col != "bloque":
        df_plano = df_plano.rename(columns={block_col: "bloque"})
    if state_col != "estado":
        df_plano = df_plano.rename(columns={state_col: "estado"})
    if finca_col != "finca":
        df_plano = df_plano.rename(columns={finca_col: "finca"})
    if variedad_col != "variedad":
        df_plano = df_plano.rename(columns={variedad_col: "variedad"})
    if semana_col != "semana":
        df_plano = df_plano.rename(columns={semana_col: "semana"})

    df_plano["bloque"] = df_plano["bloque"].astype(str).str.strip()
    df_plano = df_plano[df_plano["bloque"].str.lower() != "confinados"].copy()
    df_plano = _normalize_merge_keys(df_plano, text_cols=["finca", "variedad", "flor"])

    arrancada_calc_col = _extract_first_existing(
        df_plano,
        [
            "s_arranque_calculada",
            "arranque_calculada",
            "s_arranque_programada",
            "arranque_programada",
            "s. arranque programada",
            "s_ arranque programada",
        ],
    )
    arrancada_real_col = _extract_first_existing(
        df_plano,
        [
            "s_arranque_real",
            "arranque_real",
            "s. arranque real",
            "s_arranque_rea_l",
        ],
    )
    pico_col = _extract_first_existing(
        df_plano,
        [
            "fiesta_pico",
            "pico",
            "fiesta_pico",
            "fiesta (pico)",
            "semana_primer_pico",
        ],
    )
    esquejes_col = _extract_first_existing(df_plano, ["esquejes_sembrados", "esquejes_sembrados_", "esquejes sembrados"])

    df_plano["semana"] = pd.to_numeric(df_plano["semana"], errors="coerce")

    df_plano_s = df_plano[df_plano["estado"].astype(str).str.lower() == "sembrada"].copy()
    df_plano_group_s = (
        df_plano_s.groupby(["finca", "bloque", "variedad", "semana"], dropna=False)[arrancada_calc_col]
        .max()
        .reset_index()
        .rename(columns={arrancada_calc_col: "farranque"})
    )
    df_plano_group_s[["semana", "farranque"]] = (
        df_plano_group_s[["semana", "farranque"]].apply(pd.to_numeric, errors="coerce")
    )
    df_plano_group_s = df_plano_group_s.dropna(subset=["semana"]).copy()
    df_plano_group_s["semana"] = _to_int(df_plano_group_s["semana"])
    df_plano_group_s["farranque"] = pd.to_numeric(df_plano_group_s["farranque"], errors="coerce")
    df_plano_group_s.loc[
        df_plano_group_s["farranque"].isna() | (df_plano_group_s["farranque"] < semana_actual),
        "farranque",
    ] = semana_actual
    df_plano_group_s["farranque"] = _to_int(df_plano_group_s["farranque"])
    df_plano_group_s = _normalize_merge_keys(
        df_plano_group_s,
        int_cols=["semana", "farranque", "bloque"],
        text_cols=["finca", "variedad"],
    )

    df_plano_a = df_plano[df_plano["estado"].astype(str).str.lower() == "arrancada"].copy()
    df_plano_group_a = (
        df_plano_a.groupby(["finca", "bloque", "variedad", "semana"], dropna=False)[arrancada_real_col]
        .max()
        .reset_index()
        .rename(columns={arrancada_real_col: "farranque"})
    )
    df_plano_group_a[["semana", "farranque"]] = (
        df_plano_group_a[["semana", "farranque"]].apply(pd.to_numeric, errors="coerce")
    )
    df_plano_group_a = df_plano_group_a.dropna(subset=["semana", "farranque"]).copy()
    df_plano_group_a["semana"] = _to_int(df_plano_group_a["semana"])
    df_plano_group_a["farranque"] = _to_int(df_plano_group_a["farranque"])
    df_plano_group_a = _normalize_merge_keys(
        df_plano_group_a,
        int_cols=["semana", "farranque", "bloque"],
        text_cols=["finca", "variedad"],
    )

    df_plano_final = (
        df_plano[["finca", "bloque", "variedad", "semana", pico_col]]
        .dropna()
        .rename(columns={pico_col: "pico"})
        .groupby(["finca", "bloque", "variedad", "semana", "pico"], dropna=False)
        .size()
        .reset_index(name="count")
        .drop(columns=["count"])
    )
    df_plano_final["semana"] = pd.to_numeric(
        df_plano_final["semana"].astype(str).str[:4], errors="coerce"
    ).astype("Int64")
    df_plano_final = _normalize_merge_keys(
        df_plano_final,
        int_cols=["semana", "bloque"],
        text_cols=["finca", "variedad", "pico"],
    )

    df_nplantas = (
        df_plano[["finca", "flor", "bloque", "semana", "variedad", pico_col, esquejes_col]]
        .dropna()
        .groupby(["finca", "flor", "bloque", "semana", "variedad", pico_col], dropna=False)[esquejes_col]
        .sum()
        .reset_index()
        .rename(columns={pico_col: "cosecha", esquejes_col: "esquejes_sembrados"})
    )
    df_nplantas = _normalize_merge_keys(
        df_nplantas,
        int_cols=["semana", "bloque"],
        text_cols=["finca", "flor", "variedad", "cosecha"],
    )
    df_nplantas["esquejes_sembrados"] = pd.to_numeric(
        df_nplantas["esquejes_sembrados"], errors="coerce"
    ).astype("Int64")

    return df_plano_group_s, df_plano_group_a, df_plano_final, df_nplantas


def _load_quipus_data(semana_actual: int) -> pd.DataFrame:
    quipus_file = Path(
        normalize_path(
            f"{settings.QUIPUS_TIKA_DIR}/{settings.QUIPUS_TIKA_FILE_PREFIX}{semana_actual}.csv"
        )
    )
    if not quipus_file.exists():
        raise FileNotFoundError(f"No existe el archivo Quipus semanal: {quipus_file}")

    df_quipus = pd.read_csv(quipus_file, thousands=",", sep=",", low_memory=False)
    df_quipus = _normalize_columns(df_quipus)

    if "semana_de_siembra" in df_quipus.columns:
        df_quipus = df_quipus.rename(columns={"semana_de_siembra": "semana"})
    if "cantidad" not in df_quipus.columns:
        # El proveedor renombra la columna de cantidad entre semanas:
        # "Producción tika" -> "produccion_tika", "Proyección khipus" -> "proyeccion_khipus".
        for alias in ("produccion_tika", "proyeccion_khipus"):
            if alias in df_quipus.columns:
                df_quipus = df_quipus.rename(columns={alias: "cantidad"})
                break

    required = {
        "finca",
        "variedad",
        "color",
        "flor",
        "estado",
        "semana",
        "semana_de_produccion",
        "bloque",
        "edad",
        "cantidad",
    }
    validate_columns(df_quipus, required, quipus_file.name)

    df_quipus["bloque"] = df_quipus["bloque"].astype(str).str.strip()
    df_quipus = df_quipus[df_quipus["bloque"].str.lower() != "confinados"].copy()
    df_quipus = _normalize_merge_keys(df_quipus, text_cols=["finca", "variedad", "flor", "color", "estado"])

    df_quipus["semana"] = pd.to_numeric(df_quipus["semana"], errors="coerce")
    df_quipus["semana_de_produccion"] = pd.to_numeric(df_quipus["semana_de_produccion"], errors="coerce")
    df_quipus["edad"] = pd.to_numeric(df_quipus["edad"], errors="coerce")
    df_quipus["cantidad"] = pd.to_numeric(df_quipus["cantidad"], errors="coerce")
    df_quipus = df_quipus.dropna(
        subset=["semana", "semana_de_produccion", "edad", "cantidad", "bloque", "finca", "variedad"]
    ).copy()

    df_quipus["semana"] = _to_int(df_quipus["semana"])
    df_quipus["semana_de_produccion"] = _to_int(df_quipus["semana_de_produccion"])
    df_quipus["bloque"] = _normalize_nullable_int_key(df_quipus["bloque"])

    df_quipus = (
        df_quipus.groupby(
            [
                "finca",
                "variedad",
                "color",
                "flor",
                "estado",
                "semana",
                "semana_de_produccion",
                "bloque",
                "edad",
            ],
            dropna=False,
        )["cantidad"]
        .sum()
        .reset_index()
    )
    df_quipus = _normalize_merge_keys(
        df_quipus,
        int_cols=["semana", "semana_de_produccion", "bloque"],
        text_cols=["finca", "variedad", "flor", "color", "estado"],
    )
    return df_quipus


def _build_quipus_projection(
    df_quipus: pd.DataFrame,
    df_plano_group_s: pd.DataFrame,
    df_plano_group_a: pd.DataFrame,
    df_plano_final: pd.DataFrame,
    df_nplantas: pd.DataFrame,
    df_dup: pd.DataFrame,
    df_cose: pd.DataFrame,
) -> pd.DataFrame:
    df_quipus1 = df_quipus[df_quipus["estado"].astype(str).str.lower() == "sembrada"].copy()
    df_quipus2 = df_quipus[df_quipus["estado"].astype(str).str.lower() == "arrancada"].copy()

    df_quipus4 = pd.merge(
        df_quipus1,
        df_plano_group_s,
        on=["finca", "bloque", "variedad", "semana"],
        how="left",
    )

    missing_farranque = df_quipus4["farranque"].isna()
    if missing_farranque.any():
        df_quipus4.loc[missing_farranque, "farranque"] = (
            df_quipus4.loc[missing_farranque, "semana"]
            .apply(int)
            .apply(yyww_to_date)
            .apply(lambda x: x + pd.DateOffset(weeks=66))
            .apply(date_to_yyww)
        )

    df_quipus4["farranque"] = _to_int(df_quipus4["farranque"])
    df_quipus4 = df_quipus4[df_quipus4["semana_de_produccion"] <= df_quipus4["farranque"]].copy()

    df_quipus3 = pd.merge(
        df_quipus2,
        df_plano_group_a,
        on=["finca", "bloque", "variedad", "semana"],
        how="inner",
    )
    df_quipus3["farranque"] = _to_int(df_quipus3["farranque"])
    df_quipus3 = df_quipus3[df_quipus3["semana_de_produccion"] <= df_quipus3["farranque"]].copy()

    df_quipus_mix = pd.concat([df_quipus4, df_quipus3], axis=0, ignore_index=True)
    df_quipus_mix = _normalize_merge_keys(
        df_quipus_mix,
        int_cols=["semana", "semana_de_produccion", "bloque", "farranque"],
        text_cols=["finca", "variedad", "flor", "color", "estado"],
    )

    if not df_dup.empty:
        df_proy_cos_dup = pd.merge(
            df_nplantas,
            df_dup,
            on=["finca", "variedad", "semana", "bloque", "cosecha"],
            how="right",
        )
        if not df_proy_cos_dup.empty:
            df_proy_cos_dup["aporte"] = (
                df_proy_cos_dup.groupby(["finca", "flor", "bloque", "variedad", "semana"])["esquejes_sembrados"]
                .transform(lambda x: x / x.sum())
            )
            df_proy_cos_dup = df_proy_cos_dup.drop(columns=["esquejes_sembrados"])

            base_q = (
                df_quipus_mix.groupby(
                    ["finca", "bloque", "variedad", "semana", "semana_de_produccion", "edad", "color"],
                    dropna=False,
                )["cantidad"]
                .sum()
                .reset_index()
            )
            df_quipus_cfalt = pd.merge(
                df_proy_cos_dup,
                base_q,
                on=["finca", "bloque", "variedad", "semana"],
                how="left",
            ).rename(columns={"cosecha": "pico", "cantidad": "q"})
            df_quipus_cfalt["cantidad"] = pd.to_numeric(
                df_quipus_cfalt["q"] * df_quipus_cfalt["aporte"], errors="coerce"
            ).fillna(0)
            df_quipus_plano_cfalt = (
                df_quipus_cfalt.groupby(
                    [
                        "finca",
                        "flor",
                        "bloque",
                        "pico",
                        "variedad",
                        "semana_de_produccion",
                        "edad",
                        "color",
                    ],
                    dropna=False,
                )["cantidad"]
                .sum()
                .reset_index()
            )
        else:
            df_quipus_plano_cfalt = pd.DataFrame()
    else:
        df_quipus_plano_cfalt = pd.DataFrame()

    df_plano_final_local = _normalize_merge_keys(
        df_plano_final,
        int_cols=["semana", "bloque"],
        text_cols=["finca", "variedad", "pico"],
    )
    df_quipus_plano0 = pd.merge(
        df_quipus_mix,
        df_plano_final_local,
        on=["finca", "bloque", "variedad", "semana"],
        how="left",
    )

    df_quipus_plano = (
        df_quipus_plano0.groupby(
            [
                "finca",
                "flor",
                "bloque",
                "pico",
                "variedad",
                "semana",
                "semana_de_produccion",
                "edad",
                "color",
            ],
            dropna=False,
        )["cantidad"]
        .sum()
        .reset_index()
    )

    if not df_dup.empty:
        combinaciones_duplicadas = df_dup[["finca", "bloque", "variedad", "semana"]].drop_duplicates()
        mascara = (
            df_quipus_plano.merge(
                combinaciones_duplicadas,
                on=["finca", "bloque", "variedad", "semana"],
                how="left",
                indicator=True,
            )["_merge"]
            == "both"
        )
        df_quipus_plano_limpio = df_quipus_plano[~mascara].copy()
    else:
        df_quipus_plano_limpio = df_quipus_plano.copy()

    if df_quipus_plano_cfalt.empty:
        df_khipus = df_quipus_plano_limpio.drop(columns=["semana"], errors="ignore").copy()
    else:
        df_khipus = pd.concat(
            [df_quipus_plano_limpio.drop(columns=["semana"], errors="ignore"), df_quipus_plano_cfalt],
            ignore_index=True,
        )

    df_khipus = df_khipus.rename(
        columns={"semana_de_produccion": "sem_prod", "pico": "cosecha"}
    )
    df_khipus["fuente"] = "quipus"
    df_khipus["tipo"] = "proyección"
    df_khipus["finca"] = df_khipus["finca"].replace(settings.QUIPUS_FARM_MAP)
    df_khipus["flor"] = df_khipus["flor"].replace(settings.QUIPUS_FLOWER_MAP)
    df_khipus["finca"] = _normalize_finca_code(df_khipus["finca"])

    df_quipus_proyeccion = pd.merge(df_khipus, df_cose, on="cosecha", how="left")
    df_quipus_proyeccion["cosecha_ultimos_dos"] = df_quipus_proyeccion["cosecha"].apply(_extraer_dos_digitos)
    df_quipus_proyeccion["nfiesta"] = (
        df_quipus_proyeccion["fiesta"].fillna("")
        + df_quipus_proyeccion["cosecha_ultimos_dos"].astype(str)
    )

    df_quipus_proyeccion = df_quipus_proyeccion[
        ["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod", "cantidad", "tipo", "fuente", "nfiesta"]
    ].copy()

    df_quipus_proyeccion["sem_prod"] = _to_int(df_quipus_proyeccion["sem_prod"])
    df_quipus_proyeccion["cantidad"] = _to_int(df_quipus_proyeccion["cantidad"])
    return df_quipus_proyeccion


def _load_proyecciones() -> pd.DataFrame:
    path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError(
            "No existe proyecciones.csv. Ejecuta primero el job 'proyecciones_csv'."
        )

    df = pd.read_csv(path, low_memory=False)
    df = _normalize_columns(df)

    if "nvari" not in df.columns and "variedad" in df.columns:
        df = df.rename(columns={"variedad": "nvari"})

    required = {"finca", "bloque", "tipo", "nvari", "cosecha", "flor", "fecha", "tallos", "matas"}
    validate_columns(df, required, path.name)

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    df["finca"] = _normalize_finca_code(df["finca"])
    df["nvari"] = df["nvari"].astype(str).str.replace(" ", "_", regex=False)
    return df


def _get_recent_completed_weeks(
    df_fechas_lunes: pd.DataFrame,
    semana_actual: int,
    *,
    count: int = None,
) -> list[int]:
    if count is None:
        count = settings.QUIPUS_VS_PROY_SEMANAS_RECIENTES
    semanas = (
        pd.to_numeric(df_fechas_lunes["aass"], errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values(ascending=False)
    )
    return semanas[semanas < semana_actual].head(count).sort_values().tolist()


def _build_cumplimiento_resumen(
    df_mysql: pd.DataFrame,
    df_fechas_lunes: pd.DataFrame,
    semana_actual: int,
) -> pd.DataFrame:
    resumen_base = df_mysql.copy()
    resumen_base["finca"] = _normalize_finca_code(resumen_base["finca"])
    resumen_base["sem_prod"] = pd.to_numeric(resumen_base["sem_prod"], errors="coerce").astype("Int64")

    for column in ["inverpalmas-real", "quipus-proyección"]:
        if column not in resumen_base.columns:
            resumen_base[column] = pd.NA
        resumen_base[column] = pd.to_numeric(resumen_base[column], errors="coerce")

    semanas_recientes = _get_recent_completed_weeks(
        df_fechas_lunes=df_fechas_lunes,
        semana_actual=semana_actual,
        count=settings.QUIPUS_VS_PROY_SEMANAS_RECIENTES,
    )
    df_10 = resumen_base[resumen_base["sem_prod"].isin(semanas_recientes)].copy()

    df_resumen = (
        df_10.groupby(["finca", "bloque", "cosecha", "variedad"], as_index=False)
        .agg(
            {
                "inverpalmas-real": lambda series: series.sum(min_count=1),
                "quipus-proyección": lambda series: series.sum(min_count=1),
            }
        )
    )

    df_resumen["Cumplimiento Khipus"] = df_resumen.apply(
        lambda row: 0
        if pd.notna(row["inverpalmas-real"]) and pd.isna(row["quipus-proyección"])
        else (
            row["quipus-proyección"] / row["inverpalmas-real"]
            if pd.notna(row["inverpalmas-real"]) and row["inverpalmas-real"] != 0
            else pd.NA
        ),
        axis=1,
    )
    df_resumen["Cumplimiento Khipus"] = pd.to_numeric(
        df_resumen["Cumplimiento Khipus"],
        errors="coerce",
    ).round(2)

    df_resumen = df_resumen.rename(columns={"Cumplimiento Khipus": "Cumple%"})
    df_resumen["variedad"] = df_resumen["variedad"].astype(str).str.replace("_", " ", regex=False)
    df_resumen = df_resumen[["finca", "bloque", "variedad", "cosecha", "Cumple%"]].copy()
    df_resumen = df_resumen.query("cosecha != 'VITRI'").copy()

    return df_resumen.sort_values(["finca", "bloque", "variedad", "cosecha"]).reset_index(drop=True)

def _build_matas(df_proyecciones: pd.DataFrame, df_fechas_lunes: pd.DataFrame) -> pd.DataFrame:
    lunes_actual = pd.Timestamp(datetime.now() - timedelta(days=datetime.now().weekday())).normalize()

    df_matas_re = df_proyecciones[(df_proyecciones["tipo"] == "Real") & (df_proyecciones["fecha"] < lunes_actual)].copy()
    df_matas_re["fecha"] = df_matas_re["fecha"].apply(lambda x: x - timedelta(days=x.weekday()))
    df_matas_re = (
        df_matas_re.groupby(["finca", "bloque", "nvari", "cosecha", "fecha"], dropna=False)["matas"]
        .mean()
        .reset_index()
    )

    df_matas_aj = df_proyecciones[(df_proyecciones["tipo"] == "Proy_Aj") & (df_proyecciones["fecha"] >= lunes_actual)].copy()
    df_matas_aj["fecha"] = df_matas_aj["fecha"].apply(lambda x: x - timedelta(days=x.weekday()))
    df_matas_aj = (
        df_matas_aj.groupby(["finca", "bloque", "nvari", "cosecha", "fecha"], dropna=False)["matas"]
        .mean()
        .reset_index()
    )

    df_matas = pd.concat([df_matas_re, df_matas_aj], ignore_index=True)
    df_matas = pd.merge(df_matas, df_fechas_lunes, on="fecha", how="left")
    df_matas = df_matas.rename(columns={"aass": "sem_prod", "nvari": "variedad"})
    df_matas["variedad"] = df_matas["variedad"].astype(str).str.replace(" ", "_", regex=False)
    df_matas["finca"] = _normalize_finca_code(df_matas["finca"])
    df_matas = df_matas.drop(columns=["fecha"])
    df_matas = df_matas.dropna(subset=["sem_prod"])
    df_matas["sem_prod"] = _to_int(df_matas["sem_prod"])
    return df_matas


def _build_report_frames(
    df_proyecciones: pd.DataFrame,
    df_quipus_proyeccion: pd.DataFrame,
    df_fechas_lunes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lunes_corte = pd.Timestamp(datetime.now() - timedelta(days=datetime.now().weekday()) - timedelta(days=1)).normalize()

    tipo_map = {
        "AJ": "Proy_Aj",
        "IN": "Proy_In",
        "RE": "Real",
        "PT": "PT",
    }
    df_proyecciones = df_proyecciones.copy()
    df_proyecciones["tipo"] = df_proyecciones["tipo"].astype(str).str.strip().replace(tipo_map)
    df_proyecciones["finca"] = _normalize_finca_code(df_proyecciones["finca"])
    df_quipus_proyeccion = df_quipus_proyeccion.copy()
    df_quipus_proyeccion["finca"] = _normalize_finca_code(df_quipus_proyeccion["finca"])

    df_proyecciones_aj = df_proyecciones[df_proyecciones["tipo"] == "Proy_Aj"].copy()
    df_proyecciones_in = df_proyecciones[df_proyecciones["tipo"] == "Proy_In"].copy()
    df_proyecciones_re = df_proyecciones[df_proyecciones["tipo"] == "Real"].copy()

    df_proyecciones_re["fecha"] = df_proyecciones_re["fecha"].apply(lambda x: x - timedelta(days=x.weekday()))
    df_proyecciones_re = df_proyecciones_re[df_proyecciones_re["fecha"] < lunes_corte].copy()

    df_proy_a = pd.merge(df_proyecciones_aj, df_fechas_lunes, on="fecha", how="left")
    df_proy_a = df_proy_a.rename(columns={"aass": "sem_prod", "nvari": "variedad", "tallos": "cantidad"})
    df_proy_a["tipo"] = "proyección"

    df_proy_i = pd.merge(df_proyecciones_in, df_fechas_lunes, on="fecha", how="left")
    df_proy_i = df_proy_i.rename(columns={"aass": "sem_prod", "nvari": "variedad", "tallos": "cantidad"})
    df_proy_i["tipo"] = "proy-inicial"

    df_proy = pd.concat([df_proy_i, df_proy_a], ignore_index=True)
    df_proy = (
        df_proy.groupby(["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod", "tipo"], dropna=False)["cantidad"]
        .sum()
        .reset_index()
    )
    df_proy["fuente"] = "inverpalmas"

    df_real = pd.merge(df_proyecciones_re, df_fechas_lunes, on="fecha", how="left")
    df_real = df_real.rename(columns={"nvari": "variedad", "aass": "sem_prod", "tallos": "cantidad"})
    df_real = (
        df_real.groupby(["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod"], dropna=False)["cantidad"]
        .sum()
        .reset_index()
    )
    df_real["tipo"] = "real"
    df_real["fuente"] = "inverpalmas"

    for frame in [df_proy, df_real, df_quipus_proyeccion]:
        frame["sem_prod"] = _to_int(frame["sem_prod"])
        frame["cantidad"] = _to_int(frame["cantidad"])

    df_proy = df_proy[["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod", "cantidad", "tipo", "fuente"]]
    df_real = df_real[["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod", "cantidad", "tipo", "fuente"]]
    df_quipus_report = df_quipus_proyeccion[["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod", "cantidad", "tipo", "fuente"]]

    return df_proy, df_real, df_quipus_report


def _cumplimiento_marker_path(excel_path: Path) -> Path:
    return excel_path.parent / _CUMPLIMIENTO_MARKER_FILENAME


def _cumplimiento_ya_enviado(excel_path: Path, semana: int) -> bool:
    try:
        return _cumplimiento_marker_path(excel_path).read_text(encoding="utf-8").strip() == str(semana)
    except OSError:
        return False


def _notify_cumplimiento_khipus(*, excel_path: Path, row_count: int, enviar_email: bool, semana: int) -> None:
    """Envía por correo el reporte filtrado de cumplimiento de Khipus.

    Se envía una sola vez por semana (semana = YYWW de la corrida): el paso 1
    se vuelve a ejecutar después de subir los ajustes a Tika (paso 2), y esa
    segunda corrida no debe repetir el correo. La semana enviada queda en
    _CUMPLIMIENTO_MARKER_FILENAME junto al Excel; borrarlo fuerza el reenvío.

    Los destinatarios salen de settings.QUIPUS_CUMPLIMIENTO_EMAILS (grupo
    "Quipus" en Ajustes). Nunca lanza excepción: el archivo en
    EXCEL_OUTPUT_DIR ya quedó generado de todas formas, así que un problema
    de envío se registra en el log pero no debe tumbar la corrida del ETL.
    """
    if not enviar_email:
        logger.info("quipus_vs_proy: envío de correo omitido (enviar_email=False).")
        return
    if _cumplimiento_ya_enviado(excel_path, semana):
        logger.info("quipus_vs_proy: el correo de cumplimiento de la semana %s ya se envió; no se repite.", semana)
        return
    if row_count == 0:
        logger.info("quipus_vs_proy: sin filas con Cumple mayor a 0 tras filtrar; no se envía correo.")
        return

    destinatarios = [addr.strip() for addr in (settings.QUIPUS_CUMPLIMIENTO_EMAILS or []) if str(addr).strip()]
    if not destinatarios:
        logger.warning(
            "quipus_vs_proy: enviar_email=True pero QUIPUS_CUMPLIMIENTO_EMAILS esta "
            "vacio (Ajustes > Quipus). No se envia correo."
        )
        return

    try:
        send_email(
            to=destinatarios,
            subject=_CUMPLIMIENTO_EMAIL_SUBJECT,
            body=(
                f"{_CUMPLIMIENTO_EMAIL_SUBJECT}.\n\n"
                "El archivo adjunto hay que subirlo en el sistema de cultivo, "
                "menu Produccion, submenu Importar cumplimiento proyecciones.\n\n"
                "Es importante hacerlo antes de actualizar el Excel donde "
                "proyectan los agronomos.\n\n"
                f"Se adjunta el archivo con los {row_count} registro(s) con Cumple% mayor "
                "a 0 de las ultimas semanas."
            ),
            attachments=[excel_path],
        )
    except MailNotConfiguredError as exc:
        logger.warning("quipus_vs_proy: no se envio el correo de cumplimiento: %s", exc)
        return
    except Exception:  # noqa: BLE001
        logger.exception("quipus_vs_proy: fallo inesperado enviando el correo de cumplimiento.")
        return

    try:
        _cumplimiento_marker_path(excel_path).write_text(str(semana), encoding="utf-8")
    except OSError:
        logger.exception("quipus_vs_proy: no se pudo registrar la semana del correo de cumplimiento.")


def _load_variedad_codigos() -> pd.DataFrame:
    """Mapeo codigo/nombre de ld_variedades para enriquecer quipus.csv."""
    sql = """
        SELECT v.codigo, v.nombre
        FROM ld_variedades v
    """
    rows = execute_query(sql) or []
    return pd.DataFrame(rows, columns=["codigo", "nombre"])


def _build_quipus_export(
    df_quipus_proyeccion: pd.DataFrame,
    df_codigos: pd.DataFrame,
) -> pd.DataFrame:
    """Prepara quipus.csv: agrega el codigo de variedad y exporta el nombre con espacios.

    Usa inner join sobre v.nombre = replace(q.variedad, '_', ' '); las variedades
    sin codigo en ld_variedades quedan fuera del CSV.
    """
    if df_codigos.empty:
        raise RuntimeError("No se pudo cargar ld_variedades para enriquecer quipus.csv.")

    df_export = df_quipus_proyeccion.copy()
    df_export["variedad_nombre"] = (
        df_export["variedad"].astype(str).str.strip().str.replace("_", " ", regex=False)
    )
    df_export = pd.merge(
        df_export,
        df_codigos[["codigo", "nombre"]],
        left_on="variedad_nombre",
        right_on="nombre",
        how="inner",
    )
    df_export["variedad"] = df_export["variedad_nombre"]
    df_export = df_export.drop(columns=["variedad_nombre", "nombre"])
    return df_export[
        ["finca", "flor", "bloque", "cosecha", "variedad", "codigo", "sem_prod", "cantidad", "tipo", "fuente", "nfiesta"]
    ].copy()


def _persist_outputs(
    df_report: pd.DataFrame,
    df_mysql: pd.DataFrame,
    df_matas: pd.DataFrame,
    df_quipus_export: pd.DataFrame,
    df_resumen: pd.DataFrame,
    *,
    enviar_email: bool = True,
    semana_actual: int,
) -> str:
    quipus_output_path = Path(normalize_path(settings.QUIPUS_OUTPUT_PATH))
    quipus_output_path.parent.mkdir(parents=True, exist_ok=True)
    df_quipus_export.to_csv(quipus_output_path, index=False, encoding="utf-8-sig")

    report_output_path = Path(normalize_path(settings.QUIPUS_VS_PROY_OUTPUT_PATH))
    report_output_path.parent.mkdir(parents=True, exist_ok=True)
    df_report.to_csv(report_output_path, index=False, encoding="utf-8-sig")

    excel_output_path = Path(normalize_path(settings.QUIPUS_EXCEL_OUTPUT_PATH))
    excel_output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(excel_output_path, engine="openpyxl") as writer:
        df_mysql.to_excel(writer, index=False, sheet_name="datos")

    # Solo se envía/queda en este reporte lo que realmente cumple: Cumple%
    # mayor a cero y no vacío (filas sin dato de proyección/real quedan NA).
    df_cumplimiento = df_resumen[
        df_resumen["Cumple%"].notna() & (df_resumen["Cumple%"] > 0)
    ].copy()

    outputs_summary_path = Path(normalize_path(settings.EXCEL_OUTPUT_DIR)) / "cumplimiento_khipus_10_semanas.xlsx"
    outputs_summary_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(outputs_summary_path, engine="openpyxl") as writer:
        df_cumplimiento.to_excel(writer, index=False, sheet_name="cumplimiento_10s")

    dataframe_to_sql(df_mysql, "quipus_vs_proy", if_exists="replace")
    dataframe_to_sql(df_matas, "quipus_vs_proy_matas", if_exists="replace")

    _notify_cumplimiento_khipus(
        excel_path=outputs_summary_path,
        row_count=len(df_cumplimiento),
        enviar_email=enviar_email,
        semana=semana_actual,
    )

    return str(report_output_path)


def generate_quipus_vs_proy_artifacts(params: dict[str, Any] | None = None) -> str:
    params = params or {}
    semana_actual = int(params.get("semana_actual") or get_current_iso_week())
    enviar_email = bool(params.get("enviar_email", True))

    df_vari, df_cose, df_dup = _load_reference_data()
    df_codigos = _load_variedad_codigos()
    df_fechas_lunes = _load_calendar_mondays()

    df_plano_group_s, df_plano_group_a, df_plano_final, df_nplantas = _load_plano_data(semana_actual)
    df_quipus_raw = _load_quipus_data(semana_actual)

    df_quipus_proyeccion = _build_quipus_projection(
        df_quipus=df_quipus_raw,
        df_plano_group_s=df_plano_group_s,
        df_plano_group_a=df_plano_group_a,
        df_plano_final=df_plano_final,
        df_nplantas=df_nplantas,
        df_dup=df_dup,
        df_cose=df_cose,
    )
    df_quipus_export = _build_quipus_export(
        df_quipus_proyeccion=df_quipus_proyeccion,
        df_codigos=df_codigos,
    )

    df_proyecciones = _load_proyecciones()
    df_matas = _build_matas(df_proyecciones=df_proyecciones, df_fechas_lunes=df_fechas_lunes)

    df_proy, df_real, df_quipus_report = _build_report_frames(
        df_proyecciones=df_proyecciones,
        df_quipus_proyeccion=df_quipus_proyeccion,
        df_fechas_lunes=df_fechas_lunes,
    )

    df_report = pd.concat([df_quipus_report, df_proy, df_real], axis=0, ignore_index=True)
    df_report["finca"] = _normalize_finca_code(df_report["finca"])
    df_report["ntipo"] = df_report["fuente"] + "-" + df_report["tipo"]

    df_mysql = (
        df_report.pivot_table(
            index=["finca", "flor", "bloque", "cosecha", "variedad", "sem_prod"],
            columns=["ntipo"],
            values="cantidad",
            aggfunc=np.sum,
        )
        .reset_index()
    )

    df_mysql = pd.merge(df_mysql, df_vari, on="variedad", how="left")
    df_mysql = pd.merge(df_mysql, df_cose, on="cosecha", how="left")
    df_mysql["cosecha_ultimos_dos"] = df_mysql["cosecha"].apply(_extraer_dos_digitos)
    df_mysql["nfiesta"] = df_mysql["fiesta"].fillna("") + df_mysql["cosecha_ultimos_dos"].astype(str)
    df_mysql = df_mysql.drop(columns=["cosecha_ultimos_dos"]) 
    df_mysql["finca"] = _normalize_finca_code(df_mysql["finca"])
    df_resumen = _build_cumplimiento_resumen(
        df_mysql=df_mysql,
        df_fechas_lunes=df_fechas_lunes,
        semana_actual=semana_actual,
    )

    return _persist_outputs(
        df_report=df_report,
        df_mysql=df_mysql,
        df_matas=df_matas,
        df_quipus_export=df_quipus_export,
        df_resumen=df_resumen,
        enviar_email=enviar_email,
        semana_actual=semana_actual,
    )
