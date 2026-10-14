"""Detección de anomalías en ld_lonas usando reglas físicas e históricas.

Analiza registros en ld_lonas filtrados por rango de semanas (YYWW), por grupo
(finca, bloque, variedad, cosecha). Rellena fechas faltantes entre el mínimo y
máximo del grupo para detectar huecos de datos.

Reglas de detección:
    - registro con tallos > 0 y plantas nulas o <= 0 → plantas_invalidas (error
      de digitación). Se sugieren las plantas más frecuentes de esa
      finca/bloque/variedad/semana_siembra en todo ld_lonas; si no hay, la media
      de plantas de los 3 días de corte anteriores (o de los 3 siguientes).
    - tallos > plantas/2 → anomalía potencial (regla_fisica). Se sugiere
      corregir plantas (si las de la siembra explican los tallos) o tallos
      (media de los 3 días de corte anteriores).
    - posible_falta_dato: si el promedio de flor_planta de los 7 días previos
        (considerando solo días con tallos > 0) es > 0.1, el día no es domingo,
        no es festivo y el valor de tallos del día está vacío.
    - fecha sin registro y sin condición histórica → sin_dato.

Parámetros:
  semana_inicio (int) – semana de inicio YYWW (ej: 2601)
  semana_fin    (int) – semana de fin YYWW (ej: 2653)

Salida en settings.ANOMALIAS_OUTPUT_DIR:
  anomalias_detectadas.csv  – todos los días del rango con su motivo.
  correcciones_lonas.xlsx   – hojas plantas_invalidas y
                              tallos_mayor_mitad_plantas con el valor sugerido
                              para corregir cada registro.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text

from app.core.settings import settings
from app.services.utils.date_service import date_to_yyww, yyww_to_date
from app.services.etl.helpers import _get_engine


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


VENTANA_DIAS_CORTE = 3
DIAS_CONTEXTO_PREVIO = 14
CLAVES_SIEMBRA = ["finca", "bloque", "variedad", "siembra_yyww"]


def _rango_semanas(semana_inicio: int, semana_fin: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Lunes de semana_inicio y domingo de semana_fin (semanas completas).

    yyww_to_date devuelve el jueves de la semana; usarlo directo como límite
    dejaba fuera lunes-miércoles de la primera semana y viernes-domingo de la última.
    """
    return (
        yyww_to_date(semana_inicio) - pd.Timedelta(days=3),
        yyww_to_date(semana_fin) + pd.Timedelta(days=3),
    )


def _load_lonas(fecha_inicio: pd.Timestamp, fecha_fin: pd.Timestamp) -> pd.DataFrame:
    """Lee de ld_lonas solo el rango pedido (la tabla completa son millones de filas) y normaliza tipos."""
    engine = _get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT finca, bloque, variedad, cosecha, plantas, tallos, flor, "
                "fecha AS fecha_registro, fecha_siembra FROM ld_lonas "
                "WHERE fecha BETWEEN :inicio AND :fin "
                "ORDER BY finca, bloque, variedad, cosecha, fecha"
            ),
            conn,
            params={"inicio": fecha_inicio.to_pydatetime(), "fin": fecha_fin.to_pydatetime()},
        )

    df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], errors="coerce")
    df["fecha_siembra"] = pd.to_datetime(df["fecha_siembra"], errors="coerce")
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce")
    df["plantas"] = pd.to_numeric(df["plantas"], errors="coerce")
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")

    return df.dropna(subset=["fecha_registro"])


def _load_plantas_referencia() -> pd.DataFrame:
    """Plantas más frecuentes por finca/bloque/variedad/semana de siembra en todo ld_lonas.

    Las plantas de una siembra no dependen de la cosecha ni del día, así que el
    valor más repetido en toda la historia sirve para inferir el dato faltante
    o mal digitado. La agregación se hace en MySQL para no traer la tabla completa.
    """
    engine = _get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT finca, bloque, variedad, fecha_siembra, plantas, COUNT(*) AS n FROM ld_lonas "
            "WHERE plantas > 0 AND fecha_siembra IS NOT NULL "
            "GROUP BY finca, bloque, variedad, fecha_siembra, plantas",
            conn,
        )
    if df.empty:
        return pd.DataFrame(columns=CLAVES_SIEMBRA + ["plantas_referencia"])

    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")
    df["siembra_yyww"] = _yyww_series(pd.to_datetime(df["fecha_siembra"], errors="coerce"))
    df = (
        df.groupby(CLAVES_SIEMBRA + ["plantas"])["n"].sum().reset_index()
        .sort_values(["n", "plantas"], ascending=False)
        .drop_duplicates(CLAVES_SIEMBRA)
    )
    return df[CLAVES_SIEMBRA + ["plantas"]].rename(columns={"plantas": "plantas_referencia"})


def _yyww_series(fechas: pd.Series) -> pd.Series:
    iso = fechas.dt.isocalendar()
    return ((iso["year"] % 100) * 100 + iso["week"]).astype("Int64")


def _media_dias_corte(valores: pd.Series, es_corte: pd.Series) -> pd.Series:
    """Media móvil de `valores` en los 3 días de corte previos a cada fila.

    Solo cuentan los días marcados en `es_corte`. Si no hay días de corte antes
    (inicio del grupo), se usa la media de los 3 siguientes.
    """
    base = valores.where(es_corte).dropna()
    if base.empty:
        return pd.Series(float("nan"), index=valores.index)

    ventana = VENTANA_DIAS_CORTE
    previos = base.rolling(ventana, min_periods=1).mean().reindex(valores.index).ffill()
    siguientes = base[::-1].rolling(ventana, min_periods=1).mean()[::-1].reindex(valores.index).bfill()
    return previos.fillna(siguientes).round()


COLUMNAS_REGISTRO = [
    "finca", "bloque", "variedad", "cosecha", "semana_siembra",
    "fecha_registro", "semana_registro", "flor", "tallos", "plantas_actual",
]


def _preparar_correcciones(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["semana_registro"] = _yyww_series(df["fecha_registro"])
    df["plantas_actual"] = df["plantas"]
    df["semana_siembra"] = pd.to_numeric(df["siembra_yyww"], errors="coerce").astype("Int64")
    return df.sort_values(["finca", "bloque", "variedad", "cosecha", "fecha_registro"])


def _build_correcciones_plantas(df_result: pd.DataFrame) -> pd.DataFrame:
    """Registros plantas_invalidas con las plantas sugeridas para corregir en el origen.

    Primero se infiere de finca/bloque/variedad/semana_siembra; si esa siembra no
    tiene plantas válidas en ningún registro, se usa la media de 3 días de corte.
    """
    df = _preparar_correcciones(df_result[df_result["motivo"] == "plantas_invalidas"])
    por_siembra = df["plantas_referencia"].notna()
    por_media = ~por_siembra & df["plantas_media_3d"].notna()
    df["plantas_sugeridas"] = df["plantas_referencia"].fillna(df["plantas_media_3d"]).astype("Int64")
    df["fuente_sugerencia"] = "sin_referencia"
    df.loc[por_siembra, "fuente_sugerencia"] = "finca_bloque_variedad_siembra"
    df.loc[por_media, "fuente_sugerencia"] = "media_3_dias_corte"
    return df[COLUMNAS_REGISTRO + ["plantas_sugeridas", "fuente_sugerencia"]]


def _build_correcciones_tallos(df_result: pd.DataFrame) -> pd.DataFrame:
    """Registros regla_fisica (tallos > plantas/2) con el dato que probablemente está mal.

    - corregir_plantas: las plantas digitadas son menores que las de la siembra y
      con las plantas de la siembra los tallos ya no superan la mitad.
    - corregir_tallos: se sugiere la media de tallos de los 3 días de corte previos
      (sin contar otros días que también violan la regla).
    - revisar: no hay referencia para sugerir un valor.
    """
    df = _preparar_correcciones(df_result[df_result["motivo"] == "regla_fisica"])
    ref = df["plantas_referencia"]
    corregir_plantas = ref.notna() & (df["plantas"] < ref) & (df["tallos"] <= ref / 2.0)
    corregir_tallos = ~corregir_plantas & df["tallos_media_3d"].notna()

    df["accion_sugerida"] = "revisar"
    df.loc[corregir_plantas, "accion_sugerida"] = "corregir_plantas"
    df.loc[corregir_tallos, "accion_sugerida"] = "corregir_tallos"
    df["valor_sugerido"] = (
        ref.where(corregir_plantas, df["tallos_media_3d"].where(corregir_tallos)).astype("Int64")
    )
    df["plantas_referencia"] = ref.astype("Int64")
    df["tallos_media_3d"] = df["tallos_media_3d"].astype("Int64")
    return df[
        COLUMNAS_REGISTRO
        + ["flor_planta", "plantas_referencia", "tallos_media_3d", "accion_sugerida", "valor_sugerido"]
    ]


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

    # Se marca antes de rellenar plantas para no ocultar los nulos con plantas_ref.
    # Día de corte: registro real con tallos > 0 y plantas > 0.
    hubo_corte = merged["tallos"].notna() & (merged["tallos"] > 0)
    es_corte = hubo_corte & (merged["plantas"] > 0)
    # Error de digitación: hubo corte pero plantas nulas o <= 0. Con tallos en 0
    # no se marca (por ahora no es problema).
    plantas_invalidas = hubo_corte & ~(merged["plantas"] > 0)
    merged["plantas_media_3d"] = _media_dias_corte(merged["plantas"], es_corte).where(plantas_invalidas)

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

    merged.loc[plantas_invalidas, "es_anomalo"] = True
    merged.loc[plantas_invalidas, "motivo"] = "plantas_invalidas"

    # Regla física: tallos > plantas/2, solo con plantas > 0 (con plantas 0
    # cualquier tallo la cumpliría; esos registros quedan como plantas_invalidas)
    anomalos = es_corte & (merged["tallos"] > merged["plantas"] / 2.0)
    merged.loc[anomalos, "es_anomalo"] = True
    merged.loc[anomalos, "motivo"] = "regla_fisica"
    merged["tallos_media_3d"] = _media_dias_corte(merged["tallos"], es_corte & ~anomalos).where(anomalos)

    # Posible falta de dato: historial alto en 7 días previos,
    # día no domingo, no festivo y tallos nulo.
    dia_no_domingo = merged["fecha_registro"].dt.weekday != 6
    es_festivo = merged["fecha_registro"].isin(festivos)
    merged["es_festivo"] = es_festivo
    historial_alto = merged["promedio_flor_planta_7d_prev"] >= 0.1
    tallos_nulos = merged["tallos"].isna()
    posible_falta = dia_no_domingo & ~es_festivo & historial_alto & tallos_nulos
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

    fecha_inicio, fecha_fin = _rango_semanas(semana_inicio, semana_fin)

    # Días previos al rango solo como contexto para las medias móviles (3 días
    # de corte, 7 días de flor_planta); no se reportan en la salida.
    df = _load_lonas(fecha_inicio - pd.Timedelta(days=DIAS_CONTEXTO_PREVIO), fecha_fin)
    if not (df["fecha_registro"] >= fecha_inicio).any():
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
        if not (group["fecha_registro"] >= fecha_inicio).any():
            continue
        siembra_value = group["siembra_yyww"].iloc[0]
        siembra_yyww = int(siembra_value) if pd.notna(siembra_value) else None

        # plantas de referencia: moda del grupo
        plantas_mode = group["plantas"][group["plantas"] > 0].mode()
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
    df_result = df_result[df_result["fecha_registro"] >= fecha_inicio].reset_index(drop=True)
    df_result["siembra_yyww"] = pd.to_numeric(df_result["siembra_yyww"], errors="coerce").astype("Int64")
    df_result = df_result.merge(_load_plantas_referencia(), on=CLAVES_SIEMBRA, how="left")
    df_correcciones_plantas = _build_correcciones_plantas(df_result)
    df_correcciones_tallos = _build_correcciones_tallos(df_result)

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
    print(f"  Resultado guardado en: {output_path}")

    correcciones_path = output_dir / "correcciones_lonas.xlsx"
    with pd.ExcelWriter(correcciones_path) as writer:
        df_correcciones_plantas.to_excel(writer, index=False, sheet_name="plantas_invalidas")
        df_correcciones_tallos.to_excel(writer, index=False, sheet_name="tallos_mayor_mitad_plantas")
    print(
        f"  Correcciones: {len(df_correcciones_plantas):,} plantas_invalidas, "
        f"{len(df_correcciones_tallos):,} tallos > plantas/2 en: {correcciones_path}\n"
    )

    return f"csv:{output_path} | xlsx:{correcciones_path}"


