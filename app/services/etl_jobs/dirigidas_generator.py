from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import execute_query, normalize_finca_series, safe_int_series, validate_columns


# ---------------------------------------------------------------------------
# Mapping and Constants
# ---------------------------------------------------------------------------

FLOWER_MAP: dict[str, str] = {
    "CLAVEL": "CLA",
    "MINICLAVEL": "CM0",
    "MINI": "CM0",
    "CLA": "CLA",
    "CM0": "CM0",
}

DIAS_SEMANA: list[str] = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]

# Máximo de lonas por día por finca/flor: el sábado la jornada es la mitad.
CAPACIDAD_DIA: dict[str, int] = {dia: 12 for dia in DIAS_SEMANA} | {"sabado": 6}

# Variedades con incremento prioritario de 1 muestra en la salida de dirigida PC.
DIRIGIDA_PC_PRIORITY_VARIETIES: set[str] = {
    "DON PEDRO",
    "MOON LIGHT",
    "DONCEL",
    "ARAGON",
    "ARTIC",
    "ATHENA",
    "PIGEON",
    "PINK PIGEON",
}


def _normalize_variety_key(value: Any) -> str:
    """Normaliza nombres de variedad para comparacion robusta."""
    return " ".join(str(value).replace("_", " ").upper().split())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
    )
    return df


def _normalize_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(" ", "_", regex=False)


def _normalize_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def _current_week_window() -> tuple[pd.Timestamp, pd.Timestamp, int]:
    """Replica la lógica temporal del notebook para dirigidas."""
    fecha_actual = datetime.now()
    fecha_inicio = fecha_actual + timedelta(weeks=1)
    dias_desde_lunes = (fecha_inicio.weekday() + 1) % 7
    fecha_inicio_lunes = fecha_inicio - timedelta(days=dias_desde_lunes)
    fecha_final = fecha_inicio_lunes + timedelta(days=7)
    numero_semana = int(fecha_final.strftime("%Y%U"))
    return pd.Timestamp(fecha_inicio_lunes).normalize(), pd.Timestamp(fecha_final).normalize(), numero_semana


def _dias_habiles_semana(fecha_inicio: pd.Timestamp) -> list[str]:
    """Días lunes-sábado de la semana objetivo que no son festivo según la tabla dates.

    fecha_inicio es el domingo previo (límite exclusivo de la ventana), así que
    DIAS_SEMANA[i] cae en fecha_inicio + (i + 1) días.
    """
    fechas = {dia: fecha_inicio + pd.Timedelta(days=i + 1) for i, dia in enumerate(DIAS_SEMANA)}
    desde = min(fechas.values()).strftime("%Y-%m-%d")
    hasta = max(fechas.values()).strftime("%Y-%m-%d")
    rows = execute_query(
        f"SELECT fecha FROM dates WHERE festivo = 1 AND fecha BETWEEN '{desde}' AND '{hasta}'"
    ) or []
    festivos = {pd.Timestamp(r[0]).normalize() for r in rows if r[0] is not None}
    return [dia for dia, fecha in fechas.items() if fecha not in festivos]


# ---------------------------------------------------------------------------
# Data Loaders
# ---------------------------------------------------------------------------

def _load_db_dirigidas() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load plano, temporadas and dates from database."""
    query_plane = """
        SELECT 
            IF(p.finca = 'INVERPALMAS', '001', '002') AS finca, 
            p.bloque, 
            p.variedad AS nvari,
            s.cod_temporada AS cosecha, 
            p.ferradica AS fecha, 
            p.plantas AS matas
        FROM plane AS p
        LEFT JOIN seasons AS s ON s.nombre = p.temporada
    """

    query_seasons = """
        SELECT cod_temporada, fecha_pico FROM seasons 
    """

    query_dates = """
        SELECT fecha, año, semana, aass FROM dates
    """

    rows_plane = execute_query(query_plane) or []
    df_plane = pd.DataFrame(
        rows_plane,
        columns=["finca", "bloque", "nvari", "cosecha", "ferradica", "matas"],
    )

    rows_seasons = execute_query(query_seasons) or []
    df_seasons = pd.DataFrame(rows_seasons, columns=["cosecha", "fecha"])

    rows_dates = execute_query(query_dates) or []
    df_dates = pd.DataFrame(rows_dates, columns=["fecha", "año", "semana", "aass"])

    if df_plane.empty:
        raise RuntimeError("No se encontraron datos en tabla plane.")
    if df_dates.empty:
        raise RuntimeError("No se encontraron datos en tabla dates.")

    df_plane["finca"] = normalize_finca_series(df_plane["finca"])

    return df_plane, df_seasons, df_dates


def _load_proyecciones_dirigidas() -> pd.DataFrame:
    """Load proyecciones.csv."""
    path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError(
            "No existe proyecciones.csv. Ejecuta primero el job 'proyecciones_csv'."
        )

    df = pd.read_csv(path, low_memory=False)
    df = _normalize_columns(df)

    if "variedad" not in df.columns and "nvari" in df.columns:
        df = df.rename(columns={"nvari": "variedad"})

    required = {"finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "tipo", "tallos"}
    validate_columns(df, required, "proyecciones.csv")

    df = df[["finca", "flor", "bloque", "variedad", "cosecha", "fecha", "matas", "edad", "tipo", "tallos"]].copy()
    df["fecha"] = _normalize_date(df["fecha"])
    df = df.rename(columns={"variedad": "nvari"})
    df["finca"] = normalize_finca_series(df["finca"])
    df["tipo"] = df["tipo"].astype(str).str.strip().str.upper()
    # Compatibilidad entre exportes viejos/nuevos y notebook original.
    df["tipo"] = df["tipo"].replace({
        "AJ": "Proy_Aj",
        "PROY_AJ": "Proy_Aj",
        "PROYAJ": "Proy_Aj",
    })
    df["nvari"] = df["nvari"].astype(str).str.replace("_", " ", regex=False)
    df["matas"] = pd.to_numeric(df["matas"], errors="coerce")
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce")

    return df.drop(columns="matas", errors="ignore")


def _arre_exclusion_key(df: pd.DataFrame, variedad_col: str) -> pd.Series:
    """Llave finca|bloque|variedad normalizada para cruzar contra ld_arre (la flor no cuenta)."""
    finca = normalize_finca_series(df["finca"])
    bloque_num = pd.to_numeric(df["bloque"], errors="coerce")
    bloque = df["bloque"].astype(str).str.strip().str.upper()
    bloque = bloque.where(bloque_num.isna(), bloque_num.round().astype("Int64").astype(str))
    variedad = df[variedad_col].map(_normalize_variety_key)
    return finca + "|" + bloque + "|" + variedad


def _load_arre_exclusiones() -> set[str]:
    """Combinaciones finca/bloque/variedad con arreglo AR reciente en ld_arre."""
    dias = int(settings.DIRIGIDAS_EXCLUIR_ARREGLOS_DIAS)
    if dias <= 0:
        return set()

    query = f"""
        SELECT finca, bloque, nombre_variedad
        FROM ld_arre
        WHERE fecha >= DATE_SUB(NOW(), INTERVAL {dias} DAY) AND tipo = 'AR'
    """
    rows = execute_query(query) or []
    df = pd.DataFrame(rows, columns=["finca", "bloque", "nombre_variedad"])
    if df.empty:
        return set()
    return set(_arre_exclusion_key(df, "nombre_variedad"))


def _exclude_arreglos(df: pd.DataFrame, exclusiones: set[str]) -> pd.DataFrame:
    """Descarta filas que cruzan con arreglos AR recientes."""
    if df.empty or not exclusiones:
        return df
    mask = _arre_exclusion_key(df, "nvari").isin(exclusiones)
    return df[~mask].copy()


def _load_arreglos_dirigidas() -> pd.DataFrame:
    """Load tabla_arreglos.xlsx."""
    path = Path(normalize_path(settings.DIRIGIDAS_ARREGLOS_PATH))
    if not path.exists():
        raise FileNotFoundError(f"No existe tabla de arreglos: {path}")

    df = pd.read_excel(path, sheet_name="Hoja1")
    df = _normalize_columns(df)

    required = {"nvariedad", "cosecha", "finca", "bloque", "flor_a", "fecha", "tallos", "tipo"}
    validate_columns(df, required, "tabla_arreglos.xlsx")

    df["finca"] = df["finca"].astype(str).str.strip()
    df["finca"] = normalize_finca_series(df["finca"])
    df["nvariedad"] = df["nvariedad"].astype(str).str.strip()

    # Filter CLA y CM0
    df = df[df["flor_a"].isin(settings.DIRIGIDAS_FLOR_FILTER)].copy()

    # Filter por fecha mínima
    df["fecha"] = _normalize_date(df["fecha"])
    df = df[df["fecha"] >= settings.DIRIGIDAS_DATE_MIN].copy()

    return df


# ---------------------------------------------------------------------------
# Processing Functions
# ---------------------------------------------------------------------------

def _merge_proy_plane(
    df_proy: pd.DataFrame,
    df_plane: pd.DataFrame,
    df_seasons: pd.DataFrame,
) -> pd.DataFrame:
    """Merge proyecciones with plano data."""
    df_proy_plane = pd.merge(
        df_proy,
        df_plane[["finca", "bloque", "nvari", "cosecha", "matas"]],
        on=["finca", "bloque", "nvari", "cosecha"],
        how="left",
        suffixes=("", "_plane"),
    )

    # Usar matas del plano si está disponible
    if "matas_plane" in df_proy_plane.columns:
        df_proy_plane["matas"] = df_proy_plane["matas_plane"].combine_first(df_proy_plane.get("matas"))
        df_proy_plane = df_proy_plane.drop(columns=["matas_plane"])

    df_proy_plane = pd.merge(
        df_proy_plane,
        df_seasons,
        on="cosecha",
        how="left",
        suffixes=("", "_season"),
    )

    return df_proy_plane


def _select_top_samples(
    df: pd.DataFrame,
    muestras: int = 5,
) -> pd.DataFrame:
    """Select top muestras por finca/bloque/flor conservando todas las columnas."""
    if df.empty:
        return df.copy()

    required_cols = {"finca", "bloque", "flor", "tallos", "matas"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError("Faltan columnas para seleccionar muestras: " + ", ".join(sorted(missing)))

    # Equivalente al notebook: ordenar por tallos/matas y tomar top N por grupo.
    # Este enfoque evita que groupby-apply elimine columnas de agrupación.
    df_top = (
        df.sort_values(["finca", "bloque", "flor", "tallos", "matas"], ascending=[True, True, True, False, False])
        .groupby(["finca", "bloque", "flor"], as_index=False, group_keys=False)
        .head(max(int(muestras), 1))
        .reset_index(drop=True)
    )

    if df_top.empty:
        return pd.DataFrame(columns=df.columns)

    df_top = df_top.sort_values(by=["tallos", "matas"])

    return df_top


def _remove_excedentes(
    df: pd.DataFrame,
    lonas_semana: int = 65,
) -> pd.DataFrame:
    """Remove excess samples beyond lonas_semana limit per finca/flor."""
    df = df.copy()
    df["muestra"] = 1

    # Grupos con más de lonas_semana muestras
    suma_por_grupo = df.groupby(["finca", "flor"]).size().reset_index(name="total")
    grupos_excedentes = suma_por_grupo[suma_por_grupo["total"] > lonas_semana]

    # Procesar cada grupo con excedente
    for _, row in grupos_excedentes.iterrows():
        finca_actual = row["finca"]
        flor_actual = row["flor"]
        excedente_actual = row["total"] - lonas_semana

        # Filtrar muestras del grupo
        mask = (df["finca"] == finca_actual) & (df["flor"] == flor_actual)
        muestras_grupo = df[mask].sort_values("tallos", ascending=False)

        # Eliminar muestras con menor tallos
        indices_a_eliminar = muestras_grupo.tail(excedente_actual).index.tolist()
        df = df.drop(indices_a_eliminar)

    return df.reset_index(drop=True)


def _distribute_by_days(
    df: pd.DataFrame,
    lonas_semana: int = 66,
) -> pd.DataFrame:
    """Distribute samples across days of the week."""
    expected_cols = list(df.columns)
    if "dia" not in expected_cols:
        expected_cols.append("dia")

    if df.empty:
        return pd.DataFrame(columns=expected_cols)

    df_final = pd.DataFrame(columns=expected_cols)

    for _, group in df.groupby(["finca", "flor"]):
        samples = []

        for dia in DIAS_SEMANA:
            remaining_rows = group[~group.index.isin(samples)]

            if dia != "sabado":
                max_sample_size = min(12, len(remaining_rows))
            else:
                max_sample_size = min(6, len(remaining_rows))

            if max_sample_size > 0:
                random_variedades = remaining_rows.sample(n=max_sample_size, replace=False).copy()
                samples.extend(random_variedades.index)
                random_variedades["dia"] = dia
                df_final = pd.concat([df_final, random_variedades], ignore_index=True)

    return df_final if not df_final.empty else pd.DataFrame(columns=expected_cols)


def _assign_muestra_values(
    df: pd.DataFrame,
    lonas_semana: int = 66,
) -> pd.DataFrame:
    """Assign muestra values (1-4) based on available space."""
    expected_cols = list(df.columns)
    if "muestra" not in expected_cols:
        expected_cols.append("muestra")

    if df.empty:
        return pd.DataFrame(columns=expected_cols)

    df_result = pd.DataFrame()

    for _, group in df.groupby(["finca", "flor"]):
        val = lonas_semana - len(group)
        group = group.reset_index(drop=True)

        if val > 0:
            if val >= 3:
                group.loc[:2, "muestra"] = 4
                group.loc[3:5, "muestra"] = 3
                group.loc[6:, "muestra"] = 2
            elif val == 2:
                group.loc[:1, "muestra"] = 4
                group.loc[2:3, "muestra"] = 3
            elif val == 1:
                group.loc[0, "muestra"] = 4
        else:
            group.loc[:val - 1, "muestra"] = 2

        df_result = pd.concat([df_result, group], ignore_index=True)

    if df_result.empty:
        return pd.DataFrame(columns=expected_cols)

    return df_result.sort_values(["finca", "flor"]).reset_index(drop=True)


def _expand_by_muestra(df: pd.DataFrame) -> pd.DataFrame:
    """Repite filas de acuerdo con la columna muestra y normaliza muestra=1."""
    if df.empty:
        return df.copy()

    repeated = []
    for _, row in df.iterrows():
        n = int(row.get("muestra", 1) or 1)
        n = max(n, 1)
        repeated.extend([row.to_dict()] * n)

    out = pd.DataFrame(repeated)
    out["muestra"] = 1
    return out


def _assign_days_by_block(group: pd.DataFrame, dias: list[str] | None = None) -> dict[int, str]:
    """Assign days keeping each bloque concentrated in one or two days when possible."""
    dias = DIAS_SEMANA if dias is None else dias
    day_capacity = [CAPACIDAD_DIA[dia] for dia in dias]
    day_used = [0] * len(dias)
    day_assignment: dict[int, str] = {}

    block_meta = (
        group.groupby("bloque", as_index=False)
        .agg(samples=("bloque", "size"), total_tallos=("tallos", "sum"))
        .sort_values(["samples", "total_tallos", "bloque"], ascending=[False, False, True])
    )

    for _, block_row in block_meta.iterrows():
        bloque = block_row["bloque"]
        block_rows = group[group["bloque"] == bloque]
        block_idxs = block_rows.index.tolist()
        pending = len(block_idxs)

        one_day_candidates = []
        for day_idx in range(len(dias)):
            remaining = day_capacity[day_idx] - day_used[day_idx]
            if remaining >= pending:
                one_day_candidates.append((remaining - pending, day_idx))

        if one_day_candidates:
            _, chosen_day = min(one_day_candidates)
            day_label = dias[chosen_day]
            for idx in block_idxs:
                day_assignment[idx] = day_label
            day_used[chosen_day] += pending
            continue

        two_day_candidates = []
        for day_idx in range(len(dias) - 1):
            rem_first = day_capacity[day_idx] - day_used[day_idx]
            rem_second = day_capacity[day_idx + 1] - day_used[day_idx + 1]
            if rem_first + rem_second >= pending:
                spill = max(pending - rem_first, 0)
                two_day_candidates.append((spill, day_idx))

        if two_day_candidates:
            _, first_day = min(two_day_candidates)
            second_day = first_day + 1
            take_first = min(day_capacity[first_day] - day_used[first_day], pending)
            first_chunk = block_idxs[:take_first]
            second_chunk = block_idxs[take_first:]

            for idx in first_chunk:
                day_assignment[idx] = dias[first_day]
            for idx in second_chunk:
                day_assignment[idx] = dias[second_day]

            day_used[first_day] += len(first_chunk)
            day_used[second_day] += len(second_chunk)
            continue

        pointer = 0
        for day_idx in range(len(dias)):
            remaining = day_capacity[day_idx] - day_used[day_idx]
            if remaining <= 0:
                continue
            take = min(remaining, pending)
            chunk = block_idxs[pointer : pointer + take]
            for idx in chunk:
                day_assignment[idx] = dias[day_idx]
            day_used[day_idx] += take
            pointer += take
            pending -= take
            if pending <= 0:
                break

    return day_assignment


def _build_dirigida_bloque_output(
    df_proy_plane2: pd.DataFrame,
    muestras: int,
    tallos_x2: int,
    tallos_x3: int,
    lonas_semana: int,
    dias_habiles: list[str] | None = None,
) -> pd.DataFrame:
    """Método 'por bloque' del notebook (para dirigida por bloque.xlsx).

    Solo programa en dias_habiles; lonas_semana debe venir ya limitado a la
    capacidad de esos días (CAPACIDAD_DIA de cada día).
    """
    dias_habiles = DIAS_SEMANA if dias_habiles is None else dias_habiles
    if df_proy_plane2.empty or not dias_habiles or lonas_semana <= 0:
        return pd.DataFrame(columns=["finca", "flor", "bloque", "nvari", "aass", "tallos", "matas", "muestra", "dia"])

    df_proy_plane4 = (
        df_proy_plane2.groupby(["finca", "flor", "bloque", "nvari", "aass"])
        .agg({"tallos": np.sum, "matas": np.sum})
        .reset_index()
    )

    df_top_pp = _select_top_samples(df_proy_plane4, muestras=muestras)
    df_top_pp = _remove_excedentes(df_top_pp, lonas_semana=lonas_semana)
    df_top_pp["muestra"] = 1

    # Si faltan muestras para llegar a lonas_semana, subir a 2 algunas filas de mayor tallo.
    suma_por_grupo = df_top_pp.groupby(["finca", "flor"]).size().reset_index(name="total")
    grupos_menor = suma_por_grupo[suma_por_grupo["total"] < lonas_semana]
    for _, row in grupos_menor.iterrows():
        finca, flor = row["finca"], row["flor"]
        faltante = int(lonas_semana - row["total"])
        if faltante <= 0:
            continue

        mask = (df_top_pp["finca"] == finca) & (df_top_pp["flor"] == flor)
        idx = df_top_pp[mask].sort_values("tallos", ascending=False).head(faltante).index
        df_top_pp.loc[idx, "muestra"] = 2

    # Ajustes de muestra por umbral de tallos.
    df_top_pp.loc[df_top_pp["tallos"] < tallos_x2, "muestra"] = 1
    df_top_pp.loc[df_top_pp["tallos"] > tallos_x3, "muestra"] = 2

    sampled_data = _expand_by_muestra(df_top_pp)
    sampled_data = sampled_data.sort_values(
        by=["finca", "flor", "bloque", "tallos", "nvari"],
        ascending=[True, True, True, False, True],
    ).reset_index(drop=True)

    sampled_data["suma_acumulada"] = sampled_data.groupby(["finca", "flor"])["muestra"].cumsum().astype(int)
    sampled_data = sampled_data[sampled_data["suma_acumulada"] <= lonas_semana].copy()
    sampled_data.drop(columns=["suma_acumulada"], inplace=True)

    # Asignación de día concentrando cada bloque en uno o, cuando sea necesario, dos días.
    sampled_data["dia"] = ""
    for (_, _), grp in sampled_data.groupby(["finca", "flor"], sort=True):
        assignment = _assign_days_by_block(grp, dias_habiles)
        for idx, day_label in assignment.items():
            sampled_data.at[idx, "dia"] = day_label

    return sampled_data.reset_index(drop=True)


def _build_dirigida_pc_output(
    df_filtrado: pd.DataFrame,
    tallos_min: int,
    lonas_semana: int,
) -> pd.DataFrame:
    """Método 'por finca-variedad' del notebook (Para dirigida PC.xlsx)."""
    if df_filtrado.empty:
        return pd.DataFrame(columns=["finca", "flor", "nvari", "tallos", "aporte_tallos", "muestra"])

    df_v = (
        df_filtrado.groupby(["finca", "flor", "nvari"], as_index=False)["tallos"]
        .sum()
    )
    # Garantizar base de 1 muestra por variedad presente por finca/flor.
    # El filtro por tallos_min ya se aplica en df_filtrado antes de llegar aquí.
    df_v = df_v[df_v["tallos"] > 0].copy()
    if df_v.empty:
        return pd.DataFrame(columns=["finca", "flor", "nvari", "tallos", "aporte_tallos", "muestra"])

    total_tallos = df_v.groupby(["finca", "flor"])["tallos"].transform("sum")
    df_v["aporte_tallos"] = np.where(total_tallos > 0, df_v["tallos"] / total_tallos, 0)

    df_sorted = df_v.sort_values(by=["finca", "flor", "aporte_tallos"], ascending=[True, True, False]).reset_index(drop=True)
    df_sorted["muestra"] = 1

    # Completar hasta lonas_semana por finca/flor.
    # Regla: primero asegurar base de 1 muestra por variedad (si cabe en el cupo),
    # luego repartir incrementos por aporte dando prioridad a variedades definidas.
    chunks = []
    for _, group in df_sorted.groupby(["finca", "flor"], as_index=False):
        group = group.sort_values(["aporte_tallos", "tallos", "nvari"], ascending=[False, False, True]).reset_index(drop=True)

        if group.empty or lonas_semana <= 0:
            continue

        # Si hay más variedades que cupo semanal, no es posible asignar 1 muestra a todas.
        # En ese caso conservar primero variedades prioritarias y luego mayor aporte.
        if len(group) > lonas_semana:
            priority_mask = group["nvari"].map(_normalize_variety_key).isin(DIRIGIDA_PC_PRIORITY_VARIETIES)
            priority_df = group[priority_mask].copy()
            non_priority_df = group[~priority_mask].copy()
            group = pd.concat([priority_df, non_priority_df], ignore_index=True).head(int(lonas_semana)).copy()
            group = group.sort_values(["aporte_tallos", "tallos", "nvari"], ascending=[False, False, True]).reset_index(drop=True)

        # Priorizar +1 muestra para variedades definidas, sin exceder el cupo semanal.
        special_mask = group["nvari"].map(_normalize_variety_key).isin(DIRIGIDA_PC_PRIORITY_VARIETIES)
        idx_special = group.index[special_mask].tolist()

        faltante = int(max(lonas_semana - len(group), 0))
        for row_idx in idx_special:
            if faltante <= 0:
                break
            incremento = min(1, faltante)
            group.loc[row_idx, "muestra"] += incremento
            faltante -= incremento

        i = 0
        while faltante > 0 and not group.empty:
            row_idx = i % len(group)
            group.loc[row_idx, "muestra"] += 1
            faltante -= 1
            i += 1
        chunks.append(group)

    df_resultado = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame(columns=df_sorted.columns)
    df_repeated = _expand_by_muestra(df_resultado)
    return df_repeated.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def generate_dirigidas_analyzer(params: dict[str, Any] | None = None) -> str:
    """
    Genera análisis de dirigidas desde proyecciones, plano y tabla de arreglos.
    Produce distribución de muestras por día de la semana y valida capacidad
    de lonas (65 muestras máximo por finca/flor).

    Params opcionales:
      muestras       (int)   – número de top muestras por bloque, default settings.DIRIGIDAS_MUESTRAS
      tallos_min     (int)   – tallos mínimos, default settings.DIRIGIDAS_TALLOS_MIN
      lonas_semana   (int)   – capacidad máxima, default settings.DIRIGIDAS_LONAS_SEMANA
    """
    params = params or {}
    def _param_int(key: str, default: int) -> int:
        value = params.get(key, None)
        if value is None:
            return int(default)
        return int(value)

    muestras = _param_int("muestras", settings.DIRIGIDAS_MUESTRAS)
    tallos_min = _param_int("tallos_min", settings.DIRIGIDAS_TALLOS_MIN)
    lonas_semana = _param_int("lonas_semana", settings.DIRIGIDAS_LONAS_SEMANA)
    camas_min = settings.DIRIGIDAS_CAMAS_MIN
    tallos_x2 = settings.DIRIGIDAS_TALLOS_X2
    tallos_x3 = settings.DIRIGIDAS_TALLOS_X3

    # Cargar datos
    df_plane, df_seasons, df_dates = _load_db_dirigidas()
    df_proy = _load_proyecciones_dirigidas()
    df_arr = _load_arreglos_dirigidas()

    # Filtro principal del notebook: flor/tipo/edad + ventana semanal.
    fecha_inicio_lunes, fecha_final, numero_semana = _current_week_window()

    # Festivos lunes-sábado no se programan: el cupo semanal baja a la capacidad
    # de los días hábiles para no pasar el límite por día.
    dias_habiles = _dias_habiles_semana(fecha_inicio_lunes)
    lonas_semana = min(lonas_semana, sum(CAPACIDAD_DIA[dia] for dia in dias_habiles))
    df_proye = df_proy[
        (df_proy["flor"].isin(settings.DIRIGIDAS_FLOR_FILTER))
        & (df_proy["tipo"] == "Proy_Aj")
        & (
            ((df_proy["edad"] > settings.DIRIGIDAS_EDAD_PICO_INICIO) & (df_proy["edad"] <= settings.DIRIGIDAS_EDAD_PICO_FIN))
            | (df_proy["edad"] <= settings.DIRIGIDAS_EDAD_MIN)
        )
    ].copy()

    df_filtrado = df_proye[
        (df_proye["fecha"] > fecha_inicio_lunes)
        & (df_proye["fecha"] <= fecha_final)
        & (df_proye["tallos"] >= tallos_min)
        & (pd.to_numeric(df_proye["edad"], errors="coerce") > 0)
    ].copy()

    # Para dirigida PC (finca/flor) no aplica filtro de edad.
    # Se usa ventana semanal y tallos >= 0.
    df_pc_filtrado = df_proy[
        (df_proy["flor"].isin(settings.DIRIGIDAS_FLOR_FILTER))
        & (df_proy["tipo"] == "Proy_Aj")
        & (df_proy["fecha"] > fecha_inicio_lunes)
        & (df_proy["fecha"] <= fecha_final)
        & (pd.to_numeric(df_proy["tallos"], errors="coerce") >= 0)
    ].copy()

    # Bloques/variedades con arreglo AR reciente no se escogen como muestra (ambos métodos).
    exclusiones_arre = _load_arre_exclusiones()
    df_filtrado = _exclude_arreglos(df_filtrado, exclusiones_arre)
    df_pc_filtrado = _exclude_arreglos(df_pc_filtrado, exclusiones_arre)

    # Preparación de plano/dates como en notebook.
    df_plane = (
        df_plane.groupby(["finca", "bloque", "nvari", "cosecha", "ferradica"], as_index=False)
        .agg({"matas": np.sum})
    )
    df_dates["fecha"] = _normalize_date(df_dates["fecha"])

    df_proy_plane = pd.merge(
        df_filtrado,
        df_plane,
        on=["finca", "bloque", "cosecha", "nvari"],
        how="inner",
    )
    df_proy_plane1 = pd.merge(
        df_proy_plane,
        df_dates,
        on=["fecha"],
        how="inner",
    )

    df_proy_plane1["ferradica_num"] = pd.to_numeric(df_proy_plane1["ferradica"], errors="coerce")
    df_proy_plane2 = df_proy_plane1[
        (df_proy_plane1["matas"] >= settings.DIRIGIDAS_PLANTAS_POR_CAMA * camas_min * settings.DIRIGIDAS_TOLERANCIA_MATAS)
        & (df_proy_plane1["ferradica_num"] > numero_semana)
    ].copy()

    # Método 1: salida por bloque.
    df_bloque = _build_dirigida_bloque_output(
        df_proy_plane2=df_proy_plane2,
        muestras=muestras,
        tallos_x2=tallos_x2,
        tallos_x3=tallos_x3,
        lonas_semana=lonas_semana,
        dias_habiles=dias_habiles,
    )

    # Método 2: salida PC por finca-variedad.
    df_pc = _build_dirigida_pc_output(
        df_filtrado=df_pc_filtrado,
        tallos_min=tallos_min,
        lonas_semana=lonas_semana,
    )

    # Exportar ambos archivos esperados por el proceso.
    output_path_pc = Path(normalize_path(settings.DIRIGIDAS_OUTPUT_PATH))
    output_path_pc.parent.mkdir(parents=True, exist_ok=True)
    df_pc.to_excel(output_path_pc, index=False, sheet_name="Dirigidas_PC")

    output_path_bloque = Path(normalize_path(settings.DIRIGIDAS_BLOQUE_OUTPUT_PATH))
    output_path_bloque.parent.mkdir(parents=True, exist_ok=True)
    df_bloque.to_excel(output_path_bloque, index=False, sheet_name="Dirigidas_Bloque")

    # Resumen
    if df_bloque.empty:
        resumen = pd.DataFrame(columns=["finca", "flor", "muestra"])
    else:
        resumen = df_bloque.groupby(["finca", "flor"])["muestra"].sum().reset_index()
    resumen_path = Path(normalize_path(settings.DIRIGIDAS_RESUMEN_PATH))
    resumen_path.parent.mkdir(parents=True, exist_ok=True)
    resumen.to_excel(resumen_path, index=False, sheet_name="Resumen")

    return str(output_path_pc)
