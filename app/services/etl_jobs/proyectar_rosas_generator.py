from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd

from app.core.db import db_connection
from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path


DEFAULT_OUTPUT_PATH = r"\\svrinverpalmas\usuarios\Outputs\proyeccion_rosas.csv"


def normalize_to_thursday(date):
    if isinstance(date, pd.Series):
        days_to_thursday = 3 - date.dt.weekday
        return date + pd.to_timedelta(days_to_thursday, unit="D")
    days_to_thursday = 3 - date.weekday()
    return date + pd.Timedelta(days=days_to_thursday)


def normalize_dates_to_thursday(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df[col] = normalize_to_thursday(df[col])
    return df


def extend_distribution_curve(curva, max_semanas: int = 52):
    if not isinstance(curva, list) or len(curva) == 0:
        return []
    if len(curva) >= max_semanas:
        return curva[:max_semanas]
    last_value = curva[-1]
    extension = [last_value * (0.9 ** i) for i in range(1, max_semanas - len(curva) + 1)]
    return curva + extension


def _execute_sql(sql: str, params: tuple | None = None) -> list[tuple]:
    with db_connection() as connection:
        cursor = connection.cursor()
        cursor.execute(sql, params or ())
        rows = cursor.fetchall()
        cursor.close()
        return rows


def _normalize_db_rows(rows: list[tuple], expected_columns: list[str], insert_default_finca: bool = False) -> list[tuple]:
    if not rows:
        return []

    normalized_rows: list[tuple] = []
    for row in rows:
        if len(row) == len(expected_columns):
            normalized_rows.append(tuple(row))
            continue

        if insert_default_finca and len(row) == len(expected_columns) - 1:
            normalized_rows.append((row[0], "000", *row[1:]))
            continue

        raise ValueError(f"Unexpected row shape for {expected_columns}: {row!r}")

    return normalized_rows


def _load_dates() -> pd.DataFrame:
    rows = _execute_sql(
        "SELECT fecha, año AS ano, semana FROM dates WHERE dia_semana=1"
    )
    df_dates = pd.DataFrame(rows, columns=["fecha", "ano", "semana"])
    if df_dates.empty:
        return df_dates
    df_dates["ano"] = pd.to_numeric(df_dates["ano"], errors="coerce").astype("Int64")
    df_dates["semana"] = pd.to_numeric(df_dates["semana"], errors="coerce").astype("Int64")
    return df_dates


def _load_proyecciones_data() -> pd.DataFrame:
    rows = _execute_sql(
        """
        SELECT
            DATE_ADD(l.fecha, INTERVAL (3 - WEEKDAY(l.fecha)) DAY) AS fecha,
            l.finca,
            l.variedad,
            l.bloque,
            SUM(l.tallos) AS tallos,
            'RE' AS tipo
        FROM ld_lonas l
        INNER JOIN dates d ON d.fecha = l.fecha
        WHERE l.flor IN ('ROC', 'ROS')
        GROUP BY
            DATE_ADD(l.fecha, INTERVAL (3 - WEEKDAY(l.fecha)) DAY),
            l.finca,
            l.variedad,
            l.bloque
        """
    )
    rows = _normalize_db_rows(rows, ["fecha", "finca", "variedad", "bloque", "tallos", "tipo"], insert_default_finca=True)
    df = pd.DataFrame(rows, columns=["fecha", "finca", "variedad", "bloque", "tallos", "tipo"])
    if df.empty:
        return df
    df = df[df["tipo"].astype(str).str.upper() == "RE"].copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["fecha"] = normalize_to_thursday(df["fecha"])
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce")
    return df


def _load_arre_data() -> pd.DataFrame:
    rows = _execute_sql(
        "SELECT fecha, finca, nombre_variedad AS variedad, bloque, tallos, tipo FROM ld_arre WHERE flor IN ('ROC','ROS') AND tipo IN ('AR', 'BA', 'S1', 'S2', 'S3')"
    )
    rows = _normalize_db_rows(rows, ["fecha", "finca", "variedad", "bloque", "tallos", "tipo"], insert_default_finca=True)
    df = pd.DataFrame(rows, columns=["fecha", "finca", "variedad", "bloque", "tallos", "tipo"])
    if df.empty:
        return df
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["fecha"] = normalize_to_thursday(df["fecha"])
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce")
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce")
    return df


def _load_curva_variedad_rosas() -> pd.DataFrame:
    rows = _execute_sql(
        "SELECT variedad, ciclo, curva, s1, s2, s3 FROM curva_variedad_rosas WHERE activo=1"
    )
    df_varieties = pd.DataFrame(
        rows,
        columns=["variedad", "ciclo", "curva_distribucion", "S1", "S2", "S3"],
    )
    if df_varieties.empty:
        return df_varieties

    for column in ["curva_distribucion", "S1", "S2", "S3"]:
        df_varieties[column] = df_varieties[column].apply(
            lambda value: json.loads(value) if isinstance(value, str) and value.strip() else []
        )
    return df_varieties


def _as_series(value):
    if isinstance(value, list):
        return pd.Series(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return pd.Series(parsed)
        except Exception:
            return pd.Series([], dtype=float)
    return pd.Series([], dtype=float)


def proyectar_tallos(df_operaciones, df_variedades, fecha_inicio, fecha_fin):
    if df_operaciones.empty:
        return pd.DataFrame()

    df_operaciones = df_operaciones.sort_values("fecha").copy()
    df_operaciones = df_operaciones[
        (df_operaciones["fecha"] >= fecha_inicio) & (df_operaciones["fecha"] <= fecha_fin)
    ].copy()

    if df_operaciones.empty:
        return pd.DataFrame()

    df_merged = df_operaciones.merge(
        df_variedades[["variedad", "ciclo", "curva_distribucion", "S1", "S2", "S3"]],
        on="variedad",
        how="left",
    ).sort_values(["fecha", "finca", "bloque", "variedad"]).copy()

    sin_curva = df_merged[df_merged["curva_distribucion"].isna()]["variedad"].dropna().unique()
    if len(sin_curva) > 0:
        print(f"⚠️ Variedades sin curva: {list(sin_curva)}")

    posicion_pico = 4
    df_merged["semana_inicio_curva"] = df_merged["ciclo"] - posicion_pico + 1

    tipos_normales = {"RE", "AR", "BA"}
    tipos_selectivos = {"S1", "S2", "S3"}
    semanas_descuento = {"S3": 1, "S2": 5, "S1": 9}

    registros = []
    for row in df_merged.itertuples(index=False):
        tipo = row.tipo
        tallos = row.tallos
        fecha_evento = row.fecha
        finca = getattr(row, "finca", None)
        bloque = row.bloque
        variedad = row.variedad
        semana_inicio_curva = row.semana_inicio_curva

        if tipo not in tipos_normales and tipo not in tipos_selectivos:
            continue

        curva_normal = row.curva_distribucion
        if not isinstance(curva_normal, list) or len(curva_normal) == 0:
            continue

        for i, pct in enumerate(curva_normal):
            if abs(pct) < 0.001:
                continue

            semanas_desde_evento = semana_inicio_curva + i - 1
            fecha_proyeccion = normalize_to_thursday(
                fecha_evento + pd.Timedelta(weeks=int(semanas_desde_evento))
            )

            if fecha_proyeccion > fecha_fin:
                continue

            cantidad_proyectada = tallos * pct
            registros.append(
                {
                    "fecha": fecha_proyeccion,
                    "finca": finca,
                    "bloque": bloque,
                    "variedad": variedad,
                    "tipo_origen": tipo,
                    "tallos": cantidad_proyectada,
                    "tipo_registro": "proyeccion_normal",
                }
            )

        if tipo in tipos_selectivos:
            edad_inicio_descuento = semanas_descuento[tipo]
            curvas_descuento = {"S1": row.S1, "S2": row.S2, "S3": row.S3}
            curva_descuento = curvas_descuento[tipo]

            if not isinstance(curva_descuento, list) or len(curva_descuento) == 0:
                continue

            for i, pct in enumerate(curva_descuento):
                if abs(pct) < 0.001:
                    continue

                edad_descuento = edad_inicio_descuento + i
                fecha_descuento = normalize_to_thursday(
                    fecha_evento + pd.Timedelta(weeks=int(edad_descuento))
                )

                if fecha_descuento > fecha_fin:
                    continue

                cantidad_descuento = -tallos * pct
                registros.append(
                    {
                        "fecha": fecha_descuento,
                        "finca": finca,
                        "bloque": bloque,
                        "variedad": variedad,
                        "tipo_origen": tipo,
                        "tallos": cantidad_descuento,
                        "tipo_registro": "descuento_selectiva",
                    }
                )

    if not registros:
        return pd.DataFrame()

    return pd.DataFrame(registros)


def _build_projection_summary(
    df_historico: pd.DataFrame,
    df_varieties: pd.DataFrame,
    projection_kind: str,
    fecha_inicio: str,
    fecha_fin: str,
) -> pd.DataFrame:
    if df_historico.empty:
        return pd.DataFrame(
            columns=["variedad", "bloque", "tipo", "fecha_proyeccion", "cantidad_proyectada"]
        )

    df = df_historico.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.normalize()
    df = df[df["fecha"].notna()].copy()
    df = df[(df["fecha"] >= pd.to_datetime(fecha_inicio)) & (df["fecha"] <= pd.to_datetime(fecha_fin))].copy()
    df = df.sort_values("fecha").copy()

    if df.empty:
        return pd.DataFrame(
            columns=["variedad", "bloque", "tipo", "fecha_proyeccion", "cantidad_proyectada"]
        )

    grouped = (
        df.groupby(["variedad", "bloque"], as_index=False)["tallos"]
        .mean()
        .rename(columns={"tallos": "cantidad_promedio"})
    )
    if not df_varieties.empty:
        grouped = grouped.merge(df_varieties[["variedad", "curva_distribucion"]], on="variedad", how="left")

    project_rows: list[dict] = []
    start = pd.to_datetime(fecha_inicio).normalize()
    end = pd.to_datetime(fecha_fin).normalize()
    projection_dates = pd.date_range(start=start, end=end, freq="W-MON")
    if projection_dates.empty:
        projection_dates = pd.DatetimeIndex([end])

    for _, row in grouped.iterrows():
        variedad = row["variedad"]
        bloque = row["bloque"]
        promedio = float(row.get("cantidad_promedio", 0.0) or 0.0)
        curve = row.get("curva_distribucion")
        if isinstance(curve, str):
            try:
                curve = json.loads(curve)
            except Exception:
                curve = []
        if not isinstance(curve, list) or not curve:
            curve = [1.0]
        curve_values = pd.Series(curve, dtype=float)
        if curve_values.sum() == 0:
            curve_values = pd.Series([1.0] * max(len(curve_values), 1), dtype=float)
        weights = curve_values / curve_values.sum()

        for idx, projection_date in enumerate(projection_dates):
            weight = float(weights.iloc[idx % len(weights)]) if len(weights) else 1.0
            project_rows.append(
                {
                    "variedad": variedad,
                    "bloque": bloque,
                    "tipo": projection_kind,
                    "fecha_proyeccion": pd.Timestamp(projection_date).normalize(),
                    "cantidad_proyectada": promedio * weight,
                }
            )

    return pd.DataFrame(project_rows, columns=["variedad", "bloque", "tipo", "fecha_proyeccion", "cantidad_proyectada"])


def _resolve_output_dir() -> Path:
    configured = getattr(settings, "PROYECTAR_ROSAS_OUTPUT_PATH", DEFAULT_OUTPUT_PATH)
    requested_path = Path(normalize_path(configured))
    if requested_path.suffix.lower() == ".csv":
        return requested_path.parent
    return requested_path


def _build_arreglos_cortes_export(
    df_proyecciones: pd.DataFrame,
    df_arre: pd.DataFrame,
    df_dates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_cuts = (
        df_proyecciones[df_proyecciones["tipo"].isin(["RE"]) ]
        .groupby(["fecha", "variedad", "bloque", "tipo"], as_index=False)["tallos"]
        .sum()
    )
    if not df_cuts.empty:
        df_cuts = df_cuts.merge(df_dates, on="fecha", how="left")

    df_pruning = df_arre.copy()
    if not df_pruning.empty:
        df_pruning = df_pruning.merge(df_dates, on="fecha", how="left")

    arreglos = df_pruning[df_pruning["tipo"].isin(["Poda", "S1", "S2", "S3"])].copy()
    cortes = df_cuts[df_cuts["tipo"] == "RE"].copy() if not df_cuts.empty else pd.DataFrame(columns=["fecha", "variedad", "bloque", "tipo", "tallos", "ano", "semana"]) 

    return arreglos[["variedad", "bloque", "tipo", "ano", "semana", "tallos"]].reset_index(drop=True), cortes[["variedad", "bloque", "tipo", "ano", "semana", "tallos"]].reset_index(drop=True)


def _build_export_frame(
    df_proyecciones: pd.DataFrame,
    df_arre: pd.DataFrame,
    df_varieties: pd.DataFrame,
    df_dates: pd.DataFrame,
    fecha_inicio: str,
    fecha_fin: str,
) -> pd.DataFrame:
    df_proyecciones = df_proyecciones.copy()
    df_arre = df_arre.copy()

    if not df_proyecciones.empty:
        df_proyecciones["fecha"] = pd.to_datetime(df_proyecciones["fecha"], errors="coerce").dt.normalize()
        df_proyecciones = df_proyecciones[(df_proyecciones["fecha"].notna())]

    if not df_arre.empty:
        df_arre["fecha"] = pd.to_datetime(df_arre["fecha"], errors="coerce").dt.normalize()
        df_arre = df_arre[(df_arre["fecha"].notna())]

    df_cuts = (
        df_proyecciones[df_proyecciones["tipo"].isin(["RE"]) ]
        .groupby(["fecha", "variedad", "bloque", "tipo"], as_index=False)["tallos"]
        .sum()
    )
    if not df_cuts.empty:
        df_cuts = df_cuts.merge(df_dates, on="fecha", how="left")

    df_pruning = df_arre.copy()
    if not df_pruning.empty:
        df_pruning = df_pruning.merge(df_dates, on="fecha", how="left")

    df_cortes_reales = df_cuts[df_cuts["tipo"] == "RE"].copy() if not df_cuts.empty else pd.DataFrame(columns=["fecha", "variedad", "bloque", "tipo", "tallos", "ano", "semana"])
    df_podas_reales = df_pruning[df_pruning["tipo"].isin(["Poda", "S1", "S2", "S3"])].copy() if not df_pruning.empty else pd.DataFrame(columns=["fecha", "variedad", "bloque", "tipo", "tallos", "ano", "semana"])
    df_podas_selectivas = df_podas_reales[df_podas_reales["tipo"].isin(["S1", "S2", "S3"])].copy() if not df_podas_reales.empty else pd.DataFrame(columns=["fecha", "variedad", "bloque", "tipo", "tallos", "ano", "semana"])

    projections: list[pd.DataFrame] = []
    for name, frame in [
        ("Poda", df_podas_reales),
        ("Corte", df_cortes_reales),
        ("Selectiva", df_podas_selectivas),
    ]:
        generated = _build_projection_summary(frame, df_varieties, name, fecha_inicio, fecha_fin)
        if not generated.empty:
            projections.append(generated)

    if not projections:
        return pd.DataFrame(columns=["variedad", "bloque", "fecha_proyeccion", "tallos_formula", "tallos_real"])

    base = pd.concat(projections, ignore_index=True)
    base = base.groupby(["variedad", "bloque", "fecha_proyeccion"], as_index=False)["cantidad_proyectada"].sum()
    base = base.rename(columns={"cantidad_proyectada": "tallos_formula"})

    real = df_proyecciones[df_proyecciones["tipo"] == "RE"].copy()
    if not real.empty:
        real["fecha"] = pd.to_datetime(real["fecha"], errors="coerce").dt.normalize()
        real = real.groupby(["variedad", "bloque", "fecha"], as_index=False)["tallos"].sum().rename(columns={"fecha": "fecha_proyeccion", "tallos": "tallos_real"})
        base = base.merge(real, on=["variedad", "bloque", "fecha_proyeccion"], how="outer")
    else:
        base["tallos_real"] = pd.NA

    return base[["variedad", "bloque", "fecha_proyeccion", "tallos_formula", "tallos_real"]]


def generate_proyectar_rosas_report(
    params: dict | None = None,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
) -> str:
    params = params or {}
    if isinstance(params, dict):
        fecha_inicio = params.get("fecha_inicio", fecha_inicio or "2021-01-01")
        fecha_fin = params.get("fecha_fin", fecha_fin or "2026-12-31")

    fecha_inicio = str(fecha_inicio or "2021-01-01")
    fecha_fin = str(fecha_fin or "2026-12-31")
    fecha_inicio_dt = normalize_to_thursday(pd.to_datetime(fecha_inicio))
    fecha_fin_dt = normalize_to_thursday(pd.to_datetime(fecha_fin))

    df_proyecciones = _load_proyecciones_data()
    df_arre = _load_arre_data()
    df_varieties = _load_curva_variedad_rosas()

    if not df_proyecciones.empty:
        df_proyecciones = df_proyecciones[df_proyecciones["tipo"].astype(str).str.upper() == "RE"].copy()

    if not df_proyecciones.empty and "finca" not in df_proyecciones.columns:
        df_proyecciones["finca"] = "000"
    if not df_arre.empty and "finca" not in df_arre.columns:
        df_arre["finca"] = "000"

    df_re = df_proyecciones[df_proyecciones["tipo"] == "RE"].copy() if not df_proyecciones.empty else pd.DataFrame(columns=["fecha", "finca", "variedad", "bloque", "tallos", "tipo"])
    df_pruning = df_arre[df_arre["tipo"].isin(["AR", "BA", "S1", "S2", "S3"])].copy() if not df_arre.empty else pd.DataFrame(columns=["fecha", "finca", "variedad", "bloque", "tallos", "tipo"])
    df_total_operaciones = pd.concat([df_re, df_pruning], ignore_index=True)
    df_total_operaciones = (
        df_total_operaciones.groupby(["fecha", "finca", "variedad", "bloque", "tipo"], as_index=False)["tallos"]
        .sum()
        .sort_values(["fecha", "finca", "bloque", "variedad", "tipo"])
        .reset_index(drop=True)
    )

    proyeccion_detallada = proyectar_tallos(
        df_total_operaciones,
        df_varieties,
        fecha_inicio_dt,
        fecha_fin_dt,
    )

    if proyeccion_detallada.empty:
        df_py = pd.DataFrame(columns=["fecha", "finca", "variedad", "bloque", "tallos", "tipo"])
    else:
        df_py = (
            proyeccion_detallada.groupby(["fecha", "finca", "variedad", "bloque"], as_index=False)["tallos"]
            .sum()
        )
        df_py["tipo"] = "PY"

    df_final = pd.concat([
        df_proyecciones,
        df_pruning,
        df_py,
    ], ignore_index=True)
    df_final = (
        df_final.groupby(["fecha", "finca", "variedad", "bloque", "tipo"], as_index=False)["tallos"]
        .sum()
    ).sort_values(["fecha", "finca", "bloque", "variedad", "tipo"]).reset_index(drop=True)

    output_dir = _resolve_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    proyeccion_path = output_dir / "proyeccion_rosas.csv"
    arreglos_path = output_dir / "arreglos.csv"
    cortes_path = output_dir / "cortes.csv"

    df_final.to_csv(proyeccion_path, index=False)

    if not df_pruning.empty:
        df_pruning[["fecha", "finca", "variedad", "bloque", "tipo", "tallos"]].to_csv(arreglos_path, index=False)
    else:
        pd.DataFrame(columns=["fecha", "finca", "variedad", "bloque", "tipo", "tallos"]).to_csv(arreglos_path, index=False)

    if not df_re.empty:
        df_re[["fecha", "finca", "variedad", "bloque", "tipo", "tallos"]].to_csv(cortes_path, index=False)
    else:
        pd.DataFrame(columns=["fecha", "finca", "variedad", "bloque", "tipo", "tallos"]).to_csv(cortes_path, index=False)

    requested_path = Path(normalize_path(getattr(settings, "PROYECTAR_ROSAS_OUTPUT_PATH", DEFAULT_OUTPUT_PATH)))
    if requested_path.suffix.lower() == ".csv":
        requested_path.parent.mkdir(parents=True, exist_ok=True)
        df_final.to_csv(requested_path, index=False)
    return str(proyeccion_path)


__all__ = [
    "_load_dates",
    "_load_proyecciones_data",
    "_load_arre_data",
    "_load_curva_variedad_rosas",
    "_build_export_frame",
    "generate_proyectar_rosas_report",
]
