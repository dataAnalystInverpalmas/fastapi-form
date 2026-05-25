"""Detección de anomalías en ld_lonas usando reglas físicas e históricas.

Analiza registros en ld_lonas filtrados por rango de semanas (YYWW), por grupo
(finca, bloque, variedad, cosecha). Rellena fechas faltantes entre el mínimo y
máximo del grupo para detectar huecos de datos.

Reglas de detección:
    - tallos > plantas/2 → anomalía potencial (regla_fisica).
    - posible_falta_dato: si el promedio de flor_planta de los 7 días previos
        (considerando solo días con tallos > 0) es > 0.1, el día no es domingo,
        no es festivo y el valor de tallos del día es nulo o <= 0.
    - fecha sin registro y sin condición histórica → sin_dato.

Parámetros:
  semana_inicio (int) – semana de inicio YYWW (ej: 2601)
  semana_fin    (int) – semana de fin YYWW (ej: 2653)

Salida: anomalias_detectadas.csv en settings.ANOMALIAS_OUTPUT_DIR.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.core.settings import settings
from app.services.date_service import date_to_yyww, yyww_to_date
from app.services.etl_helpers import _get_engine


def _load_festivos() -> set[pd.Timestamp]:
    """Retorna el conjunto de fechas marcadas como festivo en la tabla dates."""
    engine = _get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT fecha FROM dates WHERE festivo = 1",
            conn,
        )
    if df.empty:
        return set()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    return set(df["fecha"].dropna())


def _load_lonas() -> pd.DataFrame:
    """Lee ld_lonas desde MySQL y normaliza tipos."""
    engine = _get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT finca, bloque, variedad, cosecha, plantas, tallos, flor, "
            "fecha AS fecha_registro, fecha_siembra FROM ld_lonas ORDER BY finca, bloque, variedad, cosecha, fecha",
            conn,
        )
    if df.empty:
        raise RuntimeError("La tabla ld_lonas no contiene datos.")

    df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], errors="coerce")
    df["fecha_siembra"] = pd.to_datetime(df["fecha_siembra"], errors="coerce")
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce")
    df["plantas"] = pd.to_numeric(df["plantas"], errors="coerce")
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")

    return df.dropna(subset=["fecha_registro"])


def _analyze_group(
    group_df: pd.DataFrame,
    siembra_yyww: int | None,
    plantas_ref: float,
    festivos: set[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    """Analiza un grupo, rellena fechas faltantes y aplica reglas de anomalía.

    - group_df: registros del grupo ya filtrados por rango de fechas.
    - siembra_yyww: YYWW de fecha_siembra (moda del grupo).
    - plantas_ref: valor de referencia de plantas (moda del grupo).
    - festivos: conjunto de fechas festivas (días feriados).

    Devuelve un DataFrame con una fila por cada fecha entre min y max del grupo.
    Las fechas sin registro tienen tallos=NaN, y se clasifican según reglas.
    """
    if festivos is None:
        festivos = set()
    group_df = group_df.sort_values("fecha_registro").copy()

    fecha_min = group_df["fecha_registro"].min()
    fecha_max = group_df["fecha_registro"].max()

    # Serie completa de fechas diarias entre min y max del grupo
    full_dates = pd.DataFrame(
        {"fecha_registro": pd.date_range(fecha_min, fecha_max, freq="D")}
    )

    # Merge: left join para mantener todas las fechas
    merged = full_dates.merge(
        group_df[["fecha_registro", "tallos", "plantas", "flor"]],
        on="fecha_registro",
        how="left",
    )

    # Completar metadatos del grupo
    finca = group_df["finca"].iloc[0]
    bloque = group_df["bloque"].iloc[0]
    variedad = group_df["variedad"].iloc[0]
    cosecha = group_df["cosecha"].iloc[0]

    merged["finca"] = finca
    merged["bloque"] = bloque
    merged["variedad"] = variedad
    merged["cosecha"] = cosecha
    merged["siembra_yyww"] = siembra_yyww

    # Para fechas sin dato, usar plantas de referencia
    merged["plantas"] = merged["plantas"].fillna(plantas_ref if pd.notna(plantas_ref) else float("nan"))

    # Índice diario de flor/planta
    merged["flor_planta"] = float("nan")
    valid_ratio = merged["tallos"].notna() & merged["plantas"].notna() & (merged["plantas"] > 0)
    merged.loc[valid_ratio, "flor_planta"] = merged.loc[valid_ratio, "tallos"] / merged.loc[valid_ratio, "plantas"]

    # Promedio de flor/planta de los 7 días previos,
    # considerando solo días con tallos > 0.
    prev_flor_planta_pos = merged["flor_planta"].where(merged["tallos"] > 0).shift(1)
    merged["promedio_flor_planta_7d_prev"] = prev_flor_planta_pos.rolling(window=7, min_periods=1).mean()

    # Clasificar registros
    merged["es_anomalo"] = False
    merged["motivo"] = "normal"

    tiene_datos = merged["tallos"].notna() & merged["plantas"].notna()

    # Regla física: tallos > plantas/2
    anomalos = tiene_datos & (merged["tallos"] > merged["plantas"] / 2.0)
    merged.loc[anomalos, "es_anomalo"] = True
    merged.loc[anomalos, "motivo"] = "regla_fisica"

    # Posible falta de dato: historial alto en 7 días previos,
    # día no domingo, no festivo y tallos nulo o <= 0.
    dia_no_domingo = merged["fecha_registro"].dt.weekday != 6
    es_festivo = merged["fecha_registro"].isin(festivos)
    merged["es_festivo"] = es_festivo
    historial_alto = merged["promedio_flor_planta_7d_prev"] >= 0.1
    tallos_bajos_o_nulos = merged["tallos"].isna() | (merged["tallos"] <= 0)
    posible_falta = dia_no_domingo & ~es_festivo & historial_alto & tallos_bajos_o_nulos
    merged.loc[posible_falta, "es_anomalo"] = True
    merged.loc[posible_falta, "motivo"] = "posible_falta_dato"

    # Fechas sin registro
    merged.loc[(~tiene_datos) & (~posible_falta), "motivo"] = "sin_dato"

    return merged


def generate_anomalias_lonas(params: dict | None = None) -> str:
    """Runner ETL: detecta anomalías en ld_lonas con reglas física e histórica.

    Filtra por rango de semanas YYWW, rellena fechas faltantes por grupo y
    aplica la regla física tallos > plantas/2 y una regla de posible falta
    de dato basada en promedio histórico de flor_planta.

    Parámetros opcionales (dict params):
      semana_inicio (int) – YYWW de inicio (defecto: settings.ANOMALIAS_SEMANA_INICIO)
      semana_fin    (int) – YYWW de fin    (defecto: settings.ANOMALIAS_SEMANA_FIN)
    """
    p = params or {}
    semana_inicio = int(p.get("semana_inicio") or settings.ANOMALIAS_SEMANA_INICIO)
    semana_fin = int(p.get("semana_fin") or settings.ANOMALIAS_SEMANA_FIN)

    fecha_inicio = yyww_to_date(semana_inicio)
    fecha_fin = yyww_to_date(semana_fin)

    df = _load_lonas()

    # Filtrar por rango de fechas
    df = df[(df["fecha_registro"] >= fecha_inicio) & (df["fecha_registro"] <= fecha_fin)].copy()
    if df.empty:
        raise RuntimeError(
            f"Sin datos en ld_lonas entre {semana_inicio} y {semana_fin}."
        )

    df["siembra_yyww"] = df["fecha_siembra"].apply(
        lambda x: date_to_yyww(x) if pd.notna(x) else None
    )

    festivos = _load_festivos()

    group_cols = ["finca", "bloque", "variedad", "cosecha", "siembra_yyww"]
    all_results: list[pd.DataFrame] = []

    for keys, group in df.groupby(group_cols, sort=False, dropna=False):
        siembra_value = group["siembra_yyww"].iloc[0]
        siembra_yyww = int(siembra_value) if pd.notna(siembra_value) else None

        # plantas de referencia: moda del grupo
        plantas_mode = group["plantas"].dropna().mode()
        plantas_ref = float(plantas_mode.iloc[0]) if not plantas_mode.empty else float("nan")

        result = _analyze_group(group, siembra_yyww, plantas_ref, festivos)
        if not result.empty:
            all_results.append(result)

    if not all_results:
        raise RuntimeError(
            "No se generaron resultados de anomalías. "
            "Verifique que ld_lonas contenga datos en el rango indicado."
        )

    df_result = pd.concat(all_results, ignore_index=True)

    # Seleccionar columnas finales para el CSV
    cols_finales = [
        "finca", "bloque", "variedad", "cosecha", "siembra_yyww",
        "fecha_registro", "plantas", "flor", "tallos", "flor_planta",
        "promedio_flor_planta_7d_prev", "es_festivo", "es_anomalo", "motivo"
    ]
    df_result = df_result[cols_finales]

    # -----------------------------------------------------------------------
    # Resumen
    # -----------------------------------------------------------------------
    total = len(df_result)
    anomalias = df_result[df_result["es_anomalo"]]
    n_anomalias = len(anomalias)
    total_grupos = df_result.groupby(group_cols).ngroups

    print(f"\n{'='*60}")
    print("  DETECCIÓN DE ANOMALÍAS EN ld_lonas")
    print(f"  Rango: {semana_inicio} → {semana_fin}")
    print("  (Reglas: física + posible falta de dato)")
    print(f"{'='*60}")
    print(f"  Grupos analizados:    {total_grupos:>10,}")
    print(f"  Total registros:      {total:>10,}")
    print(f"  Total anomalías:      {n_anomalias:>10,}")
    if total > 0:
        print(f"  Tasa anomalías:       {n_anomalias/total*100:>9.1f}%")
    print()
    print("  Distribución por motivo:")
    for motivo, cnt in df_result["motivo"].value_counts().items():
        pct = cnt / total * 100 if total > 0 else 0
        print(f"    {motivo:<30} {cnt:>8,} ({pct:>5.1f}%)")

    if not anomalias.empty:
        print("\n  Anomalías por grupo:")
        resumen = (
            anomalias.groupby(group_cols)
            .size()
            .reset_index(name="n_anomalias")
            .sort_values("n_anomalias", ascending=False)
        )
        print(resumen.to_string(index=False))
    print(f"{'='*60}\n")

    # -----------------------------------------------------------------------
    # Guardar CSV
    # -----------------------------------------------------------------------
    output_dir = Path(settings.ANOMALIAS_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "anomalias_detectadas.csv"

    df_result.to_csv(output_path, index=False)
    print(f"  Resultado guardado en: {output_path}\n")

    return str(output_path)


