"""Explica la brecha Real vs Demanda de un rango de semanas como una cascada.

La brecha final (produccion real - demanda actual) se parte en escalones que
suman exacto:

    Brecha A = Tika_A - Demanda_A
    + por cada cambio de escenario (A->B, B->C, C->D):
        siembras       (cambio de plantas de cada cohorte, a la productividad del escenario anterior)
        productividad  (mismas plantas, distinta produccion en la ventana: curva, pico, edad)
        demanda        (-(Demanda_nuevo - Demanda_anterior))
    + ultimo paso D->Real con los mismos tres componentes
    = Brecha Real = Real - Demanda actual

La unidad que se sigue de punta a punta es la cohorte (flor, variedad, mes de siembra):
SemanaSiembra en los proy*.csv de Tika, fecha - edad en proyecciones.csv (real) y
fecha_siembra del programa (program) y de lo sembrado (hplane). Se usa el mes y no
el codigo de cosecha porque la cosecha planeada en Tika muchas veces queda registrada
con otro codigo (cruza ~60% por cosecha vs ~90% por mes en 2620-2639); mover una
siembra de mes si es un cambio de siembra.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, execute_query, safe_int_series
from app.services.etl_jobs.compare_tika_produccion_generator import (
    FLOWER_MAP,
    PROYECCIONES_TYPE_MAP,
    _load_dates_and_variedades,
    _load_demanda,
    _normalize_columns,
    _normalize_date,
    _parse_quantity,
    _read_tika_csv,
    _resolve_modelos_tika,
)
from app.services.utils.dbf_reader import normalize_path

logger = logging.getLogger(__name__)

FLORES = ("CLA", "CM0")
KEY = ["flor", "color", "variedad", "mes_siembra"]
NIVELES = {
    "flor": ["flor"],
    "color": ["flor", "color"],
    "variedad": ["flor", "color", "variedad"],
}
SIN_DATO = "SIN_MAPEO"
# Las siembras que producen en la ventana se hicieron entre ~72 y ~18 semanas antes.
SEMANAS_SIEMBRA_ANTES = 75
REAL = "Real"


# ---------------------------------------------------------------------------
# Parametros
# ---------------------------------------------------------------------------


def _resolve_params(params: dict[str, Any] | None) -> tuple[int, int, dict[str, int], float]:
    params = params or {}
    semana_inicio = int(params.get("semana_inicio") or settings.EXPLICAR_BRECHA_TIKA_SEMANA_INICIO)
    semana_fin = int(params.get("semana_fin") or settings.EXPLICAR_BRECHA_TIKA_SEMANA_FIN)
    if semana_inicio > semana_fin:
        raise ValueError(f"semana_inicio ({semana_inicio}) es mayor que semana_fin ({semana_fin}).")
    modelos = _resolve_modelos_tika(params)
    factor = params.get("factor_real")
    factor_real = float(factor) if factor not in (None, "") else float(settings.COMPARE_TIKA_TALLOS_FACTOR)
    return semana_inicio, semana_fin, modelos, factor_real


def _window_dates(df_dates: pd.DataFrame, semana_inicio: int, semana_fin: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    lookup = df_dates.set_index("aass")["fecha"]
    faltan = [s for s in (semana_inicio, semana_fin) if s not in lookup.index]
    if faltan:
        raise ValueError(f"Semanas {faltan} no existen en la tabla dates (formato AASS, ej. 2620).")
    return pd.Timestamp(lookup[semana_inicio]), pd.Timestamp(lookup[semana_fin])


# ---------------------------------------------------------------------------
# Normalizacion comun
# ---------------------------------------------------------------------------


def _norm_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(" ", "_", regex=False).str.upper()


def _vari_lookup(df_vari: pd.DataFrame) -> pd.DataFrame:
    df = df_vari.copy()
    df["variedad"] = _norm_text(df["variedad"])
    df["color"] = _norm_text(df["color"])
    return df.drop_duplicates("variedad")


def _attach_flor_color(df: pd.DataFrame, vari: pd.DataFrame) -> pd.DataFrame:
    """Completa flor/color desde ld_variedades; si no esta, usa lo que trae el archivo."""
    df = df.copy()
    for col in ("flor", "color"):
        if col not in df.columns:
            df[col] = pd.NA
    merged = df.merge(vari, on="variedad", how="left", suffixes=("", "_db"))
    merged["flor"] = merged["flor_db"].combine_first(
        merged["flor"].astype("string").str.strip().replace(FLOWER_MAP)
    )
    merged["color"] = merged["color_db"].combine_first(_norm_text(merged["color"].astype("string")))
    merged = merged.drop(columns=["flor_db", "color_db"])
    merged["flor"] = merged["flor"].fillna(SIN_DATO).astype(str)
    merged["color"] = merged["color"].fillna(SIN_DATO).replace({"<NA>": SIN_DATO, "NAN": SIN_DATO}).astype(str)
    return merged


def _lunes(fechas: pd.Series) -> pd.Series:
    fechas = pd.to_datetime(fechas, errors="coerce").dt.normalize()
    return fechas - pd.to_timedelta(fechas.dt.weekday.fillna(0), unit="D")


def _mes_siembra(fechas: pd.Series) -> pd.Series:
    """'YYYY-MM' del lunes de la semana de siembra; SIN_FECHA si no se puede calcular."""
    lunes = _lunes(fechas)
    return lunes.dt.strftime("%Y-%m").fillna("SIN_FECHA")


# ---------------------------------------------------------------------------
# Carga de fuentes
# ---------------------------------------------------------------------------


def _tika_dir(modelo: int) -> str:
    return f"//172.10.18.2/Usuarios/Hilder/Data/tika/{modelo}"


def _read_tika_proy(modelo: int) -> pd.DataFrame:
    frames = []
    for i in (1, 2, 3):
        path = Path(normalize_path(f"{_tika_dir(modelo)}/proy{i}.csv"))
        if not path.exists():
            raise FileNotFoundError(f"No existe archivo Tika de proyeccion para modelo {modelo}: {path}")
        frames.append(pd.read_csv(path, thousands=",", low_memory=False))
    return _normalize_columns(pd.concat(frames, ignore_index=True))


def tika_cohortes(
    raw: pd.DataFrame,
    vari: pd.DataFrame,
    semana_por_fecha: pd.DataFrame,
    fecha_ini: pd.Timestamp,
    fecha_fin: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (cohortes, semanal) de un escenario Tika.

    cohortes: KEY + plantas (sembradas por cama, sin duplicar) + tallos en la ventana + semana_siembra.
    semanal: fecha + flor/color/variedad + tallos (solo ventana).
    """
    df = raw.rename(columns={"semanaproducion": "aass", "semanasiembra": "semana_siembra"}).copy()
    df["variedad"] = _norm_text(df["variedad"])
    df["cosecha"] = df["cosecha"].astype(str).str.strip().str.upper()
    df["tallos"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0)
    # CantidadSembradaFutura viene llena en todos los modelos; CantidadSembrada queda vacia
    # en los escenarios viejos (agregados, sin cama), por eso solo sirve de respaldo.
    plantas = pd.Series(float("nan"), index=df.index)
    for col in ("cantidadsembradafutura", "cantidadsembrada"):
        if col in df.columns:
            plantas = plantas.combine_first(pd.to_numeric(df[col], errors="coerce"))
    if plantas.isna().all():
        raise ValueError("El proy*.csv de Tika no trae CantidadSembradaFutura ni CantidadSembrada.")
    df["plantas"] = plantas.fillna(0)
    df = _attach_flor_color(df, vari)
    df["aass"] = safe_int_series(df["aass"]).astype(int)
    df["semana_siembra"] = safe_int_series(df["semana_siembra"]).astype(int)
    df = df.merge(semana_por_fecha, on="aass", how="left")
    fecha_siembra = df["semana_siembra"].map(semana_por_fecha.set_index("aass")["fecha"])
    df["mes_siembra"] = _mes_siembra(fecha_siembra)

    # Plantas: una vez por cama/grupo (se repite en cada semana de produccion y ciclo).
    cama_cols = [c for c in ("finca", "bloque", "nave", "tabla", "cama", "cosecha") if c in df.columns]
    camas = df.groupby(KEY + cama_cols + ["semana_siembra"], dropna=False, as_index=False)["plantas"].max()
    plantas = camas.groupby(KEY, as_index=False).agg(plantas=("plantas", "sum"), semana_siembra=("semana_siembra", "min"))

    ventana = df[(df["fecha"] >= fecha_ini) & (df["fecha"] <= fecha_fin)]
    tallos = ventana.groupby(KEY, as_index=False)["tallos"].sum()
    cohortes = plantas.merge(tallos, on=KEY, how="left")
    cohortes["tallos"] = cohortes["tallos"].fillna(0)
    cohortes["plantas_conocidas"] = True
    semanal = ventana.groupby(["fecha", "flor", "color", "variedad"], as_index=False)["tallos"].sum()
    return cohortes, semanal


def demanda_modelo(raw: pd.DataFrame, vari: pd.DataFrame, semana_por_fecha: pd.DataFrame) -> pd.DataFrame:
    """demanda.csv de un modelo Tika -> fecha, flor, color, variedad, tallos."""
    # La fecha sale de la semana (tabla dates); la columna Fecha del archivo se ignora.
    df = raw.drop(columns=["fecha"], errors="ignore").rename(columns={"item_demanda": "variedad", "semana": "aass"})
    df["variedad"] = _norm_text(df["variedad"])
    df["tallos"] = _parse_quantity(df["cantidad"])
    df = _attach_flor_color(df, vari)
    df["aass"] = safe_int_series(df["aass"]).astype(int)
    df = df.merge(semana_por_fecha, on="aass", how="left")
    return df.groupby(["fecha", "flor", "color", "variedad"], as_index=False)["tallos"].sum()


def _load_real(vari: pd.DataFrame, factor: float, fecha_ini: pd.Timestamp, fecha_fin: pd.Timestamp) -> pd.DataFrame:
    path = Path(normalize_path(settings.PROYECCIONES_OUTPUT_PATH))
    if not path.exists():
        raise FileNotFoundError("No existe proyecciones.csv. Ejecuta primero el job 'proyecciones_csv'.")
    df = _normalize_columns(pd.read_csv(path, low_memory=False))
    if "variedad" not in df.columns and "nvari" in df.columns:
        df = df.rename(columns={"nvari": "variedad"})
    if "color" not in df.columns and "ncolor" in df.columns:
        df = df.rename(columns={"ncolor": "color"})
    df["tipo"] = df["tipo"].astype(str).str.strip().str.upper().replace(PROYECCIONES_TYPE_MAP)
    df = df[df["tipo"] == REAL].copy()
    df["fecha"] = _normalize_date(df["fecha"])
    df = df[(df["fecha"] >= fecha_ini) & (df["fecha"] <= fecha_fin)].copy()
    df["variedad"] = _norm_text(df["variedad"])
    df["tallos"] = pd.to_numeric(df["tallos"], errors="coerce").fillna(0) * factor
    # edad = semanas desde la siembra (igual que Edad en Tika).
    edad = pd.to_numeric(df["edad"], errors="coerce")
    df["mes_siembra"] = _mes_siembra(df["fecha"] - pd.to_timedelta(edad * 7, unit="D"))
    df = _attach_flor_color(df, vari)
    return df[df["flor"].isin(FLORES)]


def _load_siembras(sql: str, vari: pd.DataFrame, semana_por_fecha: pd.DataFrame) -> pd.DataFrame:
    rows = execute_query(sql) or []
    df = pd.DataFrame(rows, columns=["variedad", "fecha_siembra", "plantas"])
    if df.empty:
        return pd.DataFrame(columns=KEY + ["plantas", "semana_siembra"])
    df["variedad"] = _norm_text(df["variedad"])
    df["plantas"] = pd.to_numeric(df["plantas"], errors="coerce").fillna(0)
    df["fecha"] = _lunes(df["fecha_siembra"])
    df["mes_siembra"] = _mes_siembra(df["fecha"])
    df = df.merge(semana_por_fecha.rename(columns={"aass": "semana_siembra"}), on="fecha", how="left")
    df = _attach_flor_color(df, vari)
    return df.groupby(KEY, as_index=False).agg(plantas=("plantas", "sum"), semana_siembra=("semana_siembra", "min"))


def _siembras_sql(desde: pd.Timestamp) -> tuple[str, str]:
    desde_sql = desde.strftime("%Y-%m-%d")  # fecha calculada, no texto del usuario
    programa = f"""
        SELECT p.variedad, p.fecha_siembra, SUM(p.plantas)
        FROM program AS p
        WHERE p.estado = 1 AND p.fecha_siembra >= '{desde_sql}'
        GROUP BY p.variedad, p.fecha_siembra
    """
    sembrado = f"""
        SELECT h.variedad, h.fecha_siembra, SUM(h.plantas)
        FROM hplane AS h
        WHERE h.fecha_siembra >= '{desde_sql}'
        GROUP BY h.variedad, h.fecha_siembra
    """
    return programa, sembrado


# ---------------------------------------------------------------------------
# Logica de la cascada (pura, testeable)
# ---------------------------------------------------------------------------


def descomponer_paso(prev: pd.DataFrame, curr: pd.DataFrame) -> pd.DataFrame:
    """Separa el cambio de tallos en la ventana entre dos etapas, por cohorte.

    siembras      = (plantas_nuevas - plantas_previas) * (tallos_previos / plantas_previas)
                    (cohorte nueva: todos sus tallos; cohorte que desaparece: -todos)
    productividad = cambio de tallos - siembras

    Si la etapa nueva no tiene dato de plantas para la cohorte (plantas_conocidas=False),
    todo el cambio va a productividad: no se puede afirmar que fue siembra.
    """
    cols = KEY + ["plantas", "tallos", "plantas_conocidas"]
    p = prev[cols] if not prev.empty else pd.DataFrame(columns=cols)
    c = curr[cols] if not curr.empty else pd.DataFrame(columns=cols)
    df = p.merge(c, on=KEY, how="outer", suffixes=("_prev", "_curr"))
    for col in ("plantas_prev", "tallos_prev", "plantas_curr", "tallos_curr"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
    conocidas = df["plantas_conocidas_curr"].fillna(True).astype(bool) & df["plantas_conocidas_prev"].fillna(True).astype(bool)

    delta = df["tallos_curr"] - df["tallos_prev"]
    fm_prev = df["tallos_prev"].where(df["plantas_prev"] > 0, 0.0) / df["plantas_prev"].where(df["plantas_prev"] > 0, 1.0)
    siembra = (df["plantas_curr"] - df["plantas_prev"]) * fm_prev
    siembra = siembra.where(df["plantas_prev"] > 0, df["tallos_curr"])  # cohorte nueva
    siembra = siembra.where(df["plantas_curr"] > 0, -df["tallos_prev"])  # cohorte eliminada
    siembra = siembra.where(conocidas, 0.0)

    df["siembras"] = siembra
    df["productividad"] = delta - siembra
    return df


def _sum_por(df: pd.DataFrame, nivel: list[str], col: str, nombre: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=nivel + [nombre])
    return df.groupby(nivel, as_index=False)[col].sum().rename(columns={col: nombre})


def construir_cascada(
    etapas: list[str],
    cohortes: dict[str, pd.DataFrame],
    demandas: dict[str, pd.DataFrame],
    nivel: list[str],
) -> pd.DataFrame:
    """Tabla ancha de la cascada en el nivel pedido.

    `etapas` en orden (p.ej. ['A','B','C','D','Real']); `cohortes[e]` trae KEY+plantas+tallos,
    `demandas[e]` trae flor/color/variedad+tallos (ya filtrada a la ventana).
    """
    primera, ultima = etapas[0], etapas[-1]
    partes = [
        _sum_por(demandas[primera], nivel, "tallos", f"Demanda {primera}"),
        _sum_por(cohortes[primera], nivel, "tallos", f"Produccion {primera}"),
    ]
    for prev, curr in zip(etapas, etapas[1:]):
        paso = descomponer_paso(cohortes[prev], cohortes[curr])
        etiqueta_prod = "productividad y ejecucion" if curr == ultima else "productividad"
        partes.append(_sum_por(paso, nivel, "siembras", f"{prev}->{curr}: siembras"))
        partes.append(_sum_por(paso, nivel, "productividad", f"{prev}->{curr}: {etiqueta_prod}"))
        dem = pd.concat(
            [demandas[curr].assign(_d=demandas[curr]["tallos"]), demandas[prev].assign(_d=-demandas[prev]["tallos"])],
            ignore_index=True,
        )
        dem["_d"] = -dem["_d"]  # mas demanda achica la brecha
        partes.append(_sum_por(dem, nivel, "_d", f"{prev}->{curr}: demanda"))
    partes.append(_sum_por(cohortes[ultima], nivel, "tallos", f"Produccion {ultima}"))
    partes.append(_sum_por(demandas[ultima], nivel, "tallos", f"Demanda {ultima}"))

    tabla = partes[0]
    for parte in partes[1:]:
        tabla = tabla.merge(parte, on=nivel, how="outer")
    valores = [c for c in tabla.columns if c not in nivel]
    tabla[valores] = tabla[valores].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    tabla.insert(len(nivel) + 2, f"Brecha {primera}", tabla[f"Produccion {primera}"] - tabla[f"Demanda {primera}"])
    tabla[f"Brecha {ultima}"] = tabla[f"Produccion {ultima}"] - tabla[f"Demanda {ultima}"]
    pasos = [c for c in tabla.columns if "->" in c]
    tabla["Cuadre"] = tabla[f"Brecha {primera}"] + tabla[pasos].sum(axis=1) - tabla[f"Brecha {ultima}"]
    return tabla.sort_values(nivel).reset_index(drop=True)


def agregar_total(tabla: pd.DataFrame, nivel: list[str]) -> pd.DataFrame:
    valores = [c for c in tabla.columns if c not in nivel]
    total = tabla[valores].sum().to_frame().T
    for col in nivel:
        total[col] = "TOTAL"
    return pd.concat([tabla, total[nivel + valores]], ignore_index=True)


def cascada_larga(tabla: pd.DataFrame, nivel: list[str]) -> pd.DataFrame:
    """Formato largo para un grafico de cascada: un escalon por fila, en orden."""
    escalones = [c for c in tabla.columns if c.startswith("Brecha") or "->" in c]
    largo = tabla.melt(id_vars=nivel, value_vars=escalones, var_name="escalon", value_name="tallos")
    orden = {nombre: i for i, nombre in enumerate(escalones)}
    largo["orden"] = largo["escalon"].map(orden)
    largo["tipo"] = largo["escalon"].map(lambda e: "total" if e.startswith("Brecha") else "cambio")
    return largo.sort_values(nivel + ["orden"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------


def generate_explicar_brecha_tika(params: dict[str, Any] | None = None) -> str:
    semana_inicio, semana_fin, modelos, factor_real = _resolve_params(params)
    df_dates, df_vari = _load_dates_and_variedades()
    vari = _vari_lookup(df_vari)
    semana_por_fecha = df_dates[["aass", "fecha"]].drop_duplicates("aass")
    fecha_ini, fecha_fin = _window_dates(df_dates, semana_inicio, semana_fin)

    def en_ventana(df: pd.DataFrame) -> pd.DataFrame:
        return df[(df["fecha"] >= fecha_ini) & (df["fecha"] <= fecha_fin)]

    etapas = list(modelos.keys()) + [REAL]
    cohortes: dict[str, pd.DataFrame] = {}
    semanal: dict[str, pd.DataFrame] = {}
    demandas: dict[str, pd.DataFrame] = {}
    fuente_demanda: dict[str, str] = {}

    demanda_actual = _load_demanda(df_dates, df_vari)
    demanda_actual["variedad"] = _norm_text(demanda_actual["variedad"])
    demanda_actual = _attach_flor_color(demanda_actual.drop(columns=["flor", "color"]), vari)
    demanda_actual = demanda_actual.groupby(["fecha", "flor", "color", "variedad"], as_index=False)["tallos"].sum()

    anterior = None
    for letra, modelo in modelos.items():
        coh, sem = tika_cohortes(_read_tika_proy(modelo), vari, semana_por_fecha, fecha_ini, fecha_fin)
        cohortes[letra] = coh[coh["flor"].isin(FLORES)].copy()
        semanal[letra] = sem[sem["flor"].isin(FLORES)]
        dem_path = Path(normalize_path(f"{_tika_dir(modelo)}/demanda.csv"))
        if dem_path.exists():
            demandas[letra] = en_ventana(demanda_modelo(_read_tika_csv(dem_path), vari, semana_por_fecha))
            fuente_demanda[letra] = f"demanda.csv del modelo {modelo}"
        elif anterior is not None:
            demandas[letra] = demandas[anterior]
            fuente_demanda[letra] = f"sin demanda.csv: se usa la del escenario {anterior}"
        else:
            demandas[letra] = en_ventana(demanda_actual)
            fuente_demanda[letra] = "sin demanda.csv: se usa la demanda actual"
        anterior = letra

    demandas[REAL] = en_ventana(demanda_actual)
    fuente_demanda[REAL] = f"demanda actual ({Path(settings.COMPARE_TIKA_DEMANDA_PATH).name})"

    # Siembras programadas y ejecutadas de los meses que producen en la ventana.
    sql_programa, sql_sembrado = _siembras_sql(fecha_ini - pd.Timedelta(weeks=SEMANAS_SIEMBRA_ANTES))
    programa = _load_siembras(sql_programa, vari, semana_por_fecha)
    programa = programa[programa["flor"].isin(FLORES)]
    sembrado = _load_siembras(sql_sembrado, vari, semana_por_fecha)
    sembrado = sembrado[sembrado["flor"].isin(FLORES)]

    real = _load_real(vari, factor_real, fecha_ini, fecha_fin)
    semanal[REAL] = real.groupby(["fecha", "flor", "color", "variedad"], as_index=False)["tallos"].sum()
    real_coh = real.groupby(KEY, as_index=False)["tallos"].sum()
    real_coh = real_coh.merge(sembrado[KEY + ["plantas"]], on=KEY, how="left")
    real_coh["plantas_conocidas"] = real_coh["plantas"].notna()
    real_coh["plantas"] = real_coh["plantas"].fillna(0)
    # Meses sembrados que no produjeron nada en la ventana (cuentan como siembra con 0 tallos).
    sin_prod = sembrado.merge(real_coh[KEY], on=KEY, how="left", indicator=True)
    sin_prod = sin_prod[sin_prod["_merge"] == "left_only"].drop(columns=["_merge", "semana_siembra"])
    sin_prod = sin_prod.assign(tallos=0.0, plantas_conocidas=True)
    cohortes[REAL] = pd.concat([real_coh, sin_prod], ignore_index=True)

    tablas = {nombre: construir_cascada(etapas, cohortes, demandas, nivel) for nombre, nivel in NIVELES.items()}

    hoja_siembras = _hoja_siembras(etapas, cohortes, programa, sembrado)
    hoja_semanal = _hoja_semanal(etapas, semanal, demandas, df_dates)
    resumen = _hoja_resumen(
        semana_inicio, semana_fin, modelos, factor_real, fuente_demanda, cohortes, tablas["flor"], etapas
    )

    output = Path(normalize_path(settings.EXPLICAR_BRECHA_TIKA_OUTPUT_PATH))
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output) as writer:
        resumen.to_excel(writer, sheet_name="Resumen", index=False)
        agregar_total(tablas["flor"], NIVELES["flor"]).to_excel(writer, sheet_name="Cascada_flor", index=False)
        tablas["color"].to_excel(writer, sheet_name="Cascada_color", index=False)
        tablas["variedad"].to_excel(writer, sheet_name="Cascada_variedad", index=False)
        cascada_larga(tablas["color"], NIVELES["color"]).to_excel(writer, sheet_name="Cascada_larga", index=False)
        hoja_siembras.to_excel(writer, sheet_name="Siembras_ventana", index=False)
        hoja_semanal.to_excel(writer, sheet_name="Semanal", index=False)

    try:
        largo = cascada_larga(tablas["color"], NIVELES["color"]).assign(
            semana_inicio=semana_inicio, semana_fin=semana_fin
        )
        dataframe_to_sql(largo, "tika_explicar_brecha", if_exists="replace")
    except Exception:  # el Excel es la salida principal; la tabla es un extra
        logger.exception("No se pudo guardar tika_explicar_brecha en MySQL")

    return str(output)


def _hoja_siembras(
    etapas: list[str],
    cohortes: dict[str, pd.DataFrame],
    programa: pd.DataFrame,
    sembrado: pd.DataFrame,
) -> pd.DataFrame:
    base = programa.rename(columns={"plantas": "Plantas programadas", "semana_siembra": "semana_programada"})
    base = base.merge(
        sembrado.rename(columns={"plantas": "Plantas sembradas", "semana_siembra": "semana_sembrada"}),
        on=KEY,
        how="outer",
    )
    for etapa in etapas:
        coh = cohortes[etapa]
        cols = {"tallos": f"Tallos ventana {etapa}"}
        if etapa != REAL:
            cols["plantas"] = f"Plantas Tika {etapa}"
        base = base.merge(coh[KEY + list(cols)].rename(columns=cols), on=KEY, how="outer")

    tallos_cols = [f"Tallos ventana {e}" for e in etapas]
    num_cols = [c for c in base.columns if c.startswith(("Plantas", "Tallos"))]
    base[num_cols] = base[num_cols].apply(pd.to_numeric, errors="coerce")
    # Solo las siembras que alimentan la ventana en algun escenario o en el real.
    base = base[base[tallos_cols].fillna(0).gt(0).any(axis=1)].copy()

    base["Sembradas - programadas"] = base["Plantas sembradas"].fillna(0) - base["Plantas programadas"].fillna(0)
    base["% siembra ejecutada"] = (
        base["Plantas sembradas"] / base["Plantas programadas"].where(base["Plantas programadas"] > 0)
    ).round(3)

    ultima_tika = etapas[-2]
    paso = descomponer_paso(cohortes[ultima_tika], cohortes[REAL])[KEY + ["siembras", "productividad"]]
    paso = paso.rename(
        columns={
            "siembras": f"{ultima_tika}->Real: efecto siembras",
            "productividad": f"{ultima_tika}->Real: efecto productividad",
        }
    )
    base = base.merge(paso, on=KEY, how="left")
    base["semana_siembra"] = base["semana_sembrada"].combine_first(base["semana_programada"])
    base["Estado"] = "Sembrado segun programa"
    base.loc[base["Plantas programadas"].isna(), "Estado"] = "Sembrado sin estar programado"
    base.loc[base["Plantas sembradas"].isna(), "Estado"] = "Programado y no sembrado (o sin registro)"
    base.loc[base["Plantas programadas"].isna() & base["Plantas sembradas"].isna(), "Estado"] = "Solo en Tika"

    primeras = KEY + ["semana_siembra", "Estado", "Plantas programadas", "Plantas sembradas",
                      "Sembradas - programadas", "% siembra ejecutada"]
    resto = [c for c in base.columns if c not in primeras and c not in ("semana_programada", "semana_sembrada")]
    return base[primeras + resto].sort_values(KEY).reset_index(drop=True)


def _hoja_semanal(
    etapas: list[str],
    semanal: dict[str, pd.DataFrame],
    demandas: dict[str, pd.DataFrame],
    df_dates: pd.DataFrame,
) -> pd.DataFrame:
    nivel = ["fecha", "flor", "color"]
    tabla = None
    for etapa in etapas:
        for nombre, frames in ((f"Demanda {etapa}", demandas), (f"Produccion {etapa}", semanal)):
            parte = frames[etapa].groupby(nivel, as_index=False)["tallos"].sum().rename(columns={"tallos": nombre})
            tabla = parte if tabla is None else tabla.merge(parte, on=nivel, how="outer")
    valores = [c for c in tabla.columns if c not in nivel]
    tabla[valores] = tabla[valores].fillna(0.0)
    tabla = tabla.merge(df_dates[["fecha", "aass"]].drop_duplicates("fecha"), on="fecha", how="left")
    return tabla[["aass"] + nivel + valores].sort_values(["aass", "flor", "color"]).reset_index(drop=True)


def _hoja_resumen(
    semana_inicio: int,
    semana_fin: int,
    modelos: dict[str, int],
    factor_real: float,
    fuente_demanda: dict[str, str],
    cohortes: dict[str, pd.DataFrame],
    cascada_flor: pd.DataFrame,
    etapas: list[str],
) -> pd.DataFrame:
    filas: list[tuple[str, Any]] = [
        ("Ventana", f"{semana_inicio} a {semana_fin}"),
        ("Factor aplicado a la produccion real", factor_real),
    ]
    for letra, modelo in modelos.items():
        filas.append((f"Escenario {letra}", f"modelo Tika {modelo} - demanda: {fuente_demanda[letra]}"))
    filas.append(("Real", f"proyecciones.csv tipo RE - demanda: {fuente_demanda[REAL]}"))

    real = cohortes[REAL]
    total_real = real["tallos"].sum()
    con_plantas = real.loc[real["plantas_conocidas"], "tallos"].sum()
    filas.append((
        "Produccion real con siembra identificada (hplane)",
        f"{con_plantas / total_real:.1%}" if total_real else "sin produccion real",
    ))
    ultima_tika = etapas[-2]
    tika = cohortes[ultima_tika]
    en_real = tika.merge(real.loc[real["tallos"] > 0, KEY], on=KEY, how="inner")["tallos"].sum()
    if tika["tallos"].sum():
        filas.append((
            f"Tallos de {ultima_tika} cuya siembra (variedad + mes) tambien produjo en el real",
            f"{en_real / tika['tallos'].sum():.1%}",
        ))
    filas.append(("Cuadre maximo (debe ser ~0)", float(cascada_flor["Cuadre"].abs().max())))
    filas += [
        ("", ""),
        ("Como leer la cascada", "Brecha = produccion - demanda. Positivo = sobra flor."),
        ("Cohorte", "Variedad + mes de siembra. Es la unidad que se sigue entre escenarios y el real."),
        ("Brecha " + etapas[0], "Lo que el primer escenario esperaba frente a su demanda."),
        ("X->Y: siembras", "Cambio de plantas de cada cohorte, valorado a la productividad del escenario anterior. "
                           "Mes de siembra nuevo suma todos sus tallos; mes quitado resta los suyos "
                           "(mover una siembra de mes cae aqui)."),
        ("X->Y: productividad", "Mismas plantas, distinta produccion en la ventana (curva, pico, edad)."),
        ("X->Y: demanda", "Cambio de demanda con signo invertido: mas demanda achica la brecha."),
        ("->Real: siembras", "Plantas sembradas (hplane) vs plantas del ultimo escenario, por cohorte."),
        ("->Real: productividad y ejecucion", "Todo lo demas: curva real vs Tika, bajas, pico corrido, factor real. "
                                             "Incluye produccion real sin registro de siembra en hplane."),
        ("Cuadre", "Brecha inicial + todos los cambios - brecha real. Si no es ~0 hay un error."),
    ]
    return pd.DataFrame(filas, columns=["Concepto", "Valor"])
