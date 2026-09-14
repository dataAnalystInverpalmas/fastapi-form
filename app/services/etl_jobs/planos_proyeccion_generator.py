"""Extrae el plano de siembra/proyeccion de Palermo y Palmas desde MySQL.

Cada finca sube su plano ("BASE PLANO PROYECCION") desde una macro de
Excel a la tabla de staging STAGING_TABLE_NAME (via el endpoint PHP
plano_proyeccion_upload.php) en vez de que este job lea el .xlsm
directamente -- asi ninguna finca depende de que un archivo local se
sincronice hasta este servidor. Cada subida nueva no borra la anterior:
la marca como estado='historico' y deja la nueva como 'activo', asi se
conserva el historico y este job siempre toma solo la ultima subida
vigente por finca. Este job lee esa tabla para cada finca
(FINCA_CODES), une los resultados, cruza con Lotes_de_siembra.csv
(finca/bloque/variedad/semana de siembra) para traer el Id del lote, y
exporta un CSV con las columnas: finca, bloque, variedad, cosecha,
nvari, yyww_siembra, rev, amort, proyecta_quipus, id_lote_siembra.

yyww_siembra es el codigo semana ISO (ej. 2604) derivado de fec_siem; la
fecha de siembra completa no se conserva. nvari reemplaza espacios por
guion bajo. variedad se lee y exporta como texto (nunca se convierte a
numero) para no perder ceros a la izquierda ni caracteres no numericos.

Las filas que no cruzan con Lotes_de_siembra.csv (sin id_lote_siembra) se
excluyen de planos_proyeccion.csv. Se genera ademas ajustes_proyeccion.xlsx
en Outputs (combinado) con las filas cruzadas cuyo Factor (amort) sea
distinto de 1 o cuyo Mueve semanas (rev) sea distinto de 0, en columnas
ID/Factor/Mueve semanas/Vigencia/Bloqueado. Al terminar se envia un correo
POR FINCA (Palermo/Palmas) con el Excel de esa finca adjunto (listo para
subir) y, si aplica, el detalle de sus registros sin Id. Los destinatarios
reales por finca son settings.PLANOS_PROYECCION_AJUSTES_EMAILS_PALERMO /
_PALMAS; mientras se prueba, ambos apuntan a estadistica@inverpalmas.com.

Las filas cruzadas tambien se replican en MySQL (tabla
ld_planos_proyeccion), siguiendo el mismo patron que ld_proyecciones: la
API PHP (api/endpoints/planos_proyeccion.php) puede leerla directo sin
que este servicio FastAPI exponga HTTP hacia afuera.
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path

import mysql.connector
import openpyxl
import pandas as pd

from app.core.mail import MailNotConfiguredError, send_email
from app.core.settings import settings
from app.services.utils.dbf_reader import normalize_path
from app.services.etl.helpers import dataframe_to_sql, execute_query, normalize_finca_series, validate_columns

logger = logging.getLogger(__name__)

MYSQL_TABLE_NAME = "ld_planos_proyeccion"
STAGING_TABLE_NAME = "stg_plano_proyeccion"
_ERRNO_TABLE_DOES_NOT_EXIST = 1146

# Codigo de finca -> se recorren en este orden al construir el CSV/tabla final.
FINCA_CODES = ["002", "001"]  # 002 = Palermo, 001 = Palmas
FINCA_NAMES = {"002": "Palermo", "001": "Palmas"}
# Setting (en app.core.settings) con la lista de destinatarios de
# ajustes_proyeccion para cada finca. Mientras se prueba, ambos settings
# apuntan a estadistica@inverpalmas.com; el valor real sera
# palermo@inverpalmas.com / produccion@inverpalmas.com.
FINCA_EMAIL_SETTINGS = {
    "002": "PLANOS_PROYECCION_AJUSTES_EMAILS_PALERMO",
    "001": "PLANOS_PROYECCION_AJUSTES_EMAILS_PALMAS",
}

EXCEL_SERIAL_DATE_ORIGIN = pd.Timestamp("1899-12-30")

AJUSTES_MYSQL_TABLE_NAME = "ld_ajustes_proyeccion"

AJUSTES_COLUMN_MAP = {
    "id_lote_siembra": "ID",
    "amort": "Factor",
    "rev": "Mueve semanas",
}
AJUSTES_OUTPUT_COLUMNS = ["ID", "Factor", "Mueve semanas", "Vigencia", "Bloqueado"]
# "finca" se conserva junto a las columnas de salida solo para poder
# filtrar por finca en MySQL (api/endpoints/ajustes_proyeccion.php); el
# Excel que se descarga NO incluye "finca", solo AJUSTES_OUTPUT_COLUMNS.
AJUSTES_EXPORT_COLUMNS = ["finca"] + AJUSTES_OUTPUT_COLUMNS
AJUSTES_SQL_COLUMN_MAP = {
    "ID": "id_lote_siembra",
    "Factor": "factor",
    "Mueve semanas": "mueve_semanas",
    "Vigencia": "vigencia",
    "Bloqueado": "bloqueado",
}

AJUSTES_EMAIL_SUBJECT = "Planos de proyeccion: ajustes listos para subir"

# Correo con la plantilla Subir_datos_de_proyecciones.xlsx (Hoja1/Hoja2) para
# el flujo manual de subida a Tika/khipus. Hoja2 usa las mismas columnas y el
# mismo filtro de "ajuste" (Factor!=1 o Mueve semanas!=0) que AJUSTES_*, pero
# conservando bloque/variedad/cosecha en vez de renombrar a ID/Factor/etc.
TIKA_EMAIL_SUBJECT = "para Subir a Tika - Ajuste de proyección"
TIKA_HOJA2_COLUMNS = ["finca", "bloque", "variedad", "cosecha", "rev", "amort"]
TIKA_UPLOAD_URL = "https://inverpalmas-tika.meliusid.app/khipus/projection_adjustments"

LOTES_REQUIRED_COLUMNS = {"Id", "Finca", "Bloque", "Variedad", "Semana de siembra"}

REQUIRED_COLUMNS = {
    "finca",
    "bloque",
    "variedad",
    "cosecha",
    "nvari",
    "fec_siem",
    "rev",
    "amort",
    "proyecta_quipus",
}

SOURCE_COLUMNS = [
    "finca",
    "bloque",
    "variedad",
    "cosecha",
    "nvari",
    "fec_siem",
    "rev",
    "amort",
    "proyecta_quipus",
]

OUTPUT_COLUMNS = [
    "finca",
    "bloque",
    "variedad",
    "cosecha",
    "nvari",
    "yyww_siembra",
    "rev",
    "amort",
    "proyecta_quipus",
]

JOIN_KEYS = ["finca", "bloque", "nvari", "yyww_siembra"]

FINAL_COLUMNS = OUTPUT_COLUMNS + ["id_lote_siembra"]


def _load_base_from_staging(finca_code: str) -> pd.DataFrame:
    """Lee las filas subidas por la macro de Excel para una finca.

    Solo lee estado='activo': cada subida nueva marca el lote anterior de
    esa finca como 'historico' en vez de borrarlo (ver
    plano_proyeccion_upload.php), asi que aqui siempre se toma unicamente
    la ultima subida vigente por finca.

    finca_code viene de la lista fija FINCA_CODES (no de entrada de
    usuario), asi que interpolarlo directo en el SQL es seguro.
    """
    columns = list(SOURCE_COLUMNS)
    sql = (
        f"SELECT {', '.join(columns)} FROM {STAGING_TABLE_NAME} "
        f"WHERE finca = '{finca_code}' AND estado = 'activo'"
    )
    try:
        rows = execute_query(sql) or []
    except mysql.connector.errors.ProgrammingError as exc:
        if exc.errno == _ERRNO_TABLE_DOES_NOT_EXIST:
            logger.warning(
                "planos_proyeccion: la tabla %s aun no existe; ninguna macro ha subido datos todavia.",
                STAGING_TABLE_NAME,
            )
            return pd.DataFrame(columns=columns)
        raise

    return pd.DataFrame(rows, columns=columns)


def _parse_fec_siem(value: object) -> pd.Timestamp:
    """Convierte una celda fec_siem a Timestamp.

    Algunas filas del Excel guardan la fecha como numero serial (celda con
    formato General/Numero en vez de Fecha); pandas/openpyxl las entrega
    como int/float en lugar de datetime, y pd.to_datetime las interpretaria
    mal (como nanosegundos desde 1970). Se detectan y convierten usando el
    origen de fechas de Excel (1899-12-30).
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NaT
    if isinstance(value, (pd.Timestamp, datetime.datetime, datetime.date)):
        return pd.Timestamp(value)
    if isinstance(value, (int, float)):
        return EXCEL_SERIAL_DATE_ORIGIN + pd.to_timedelta(float(value), unit="D")
    return pd.to_datetime(value, errors="coerce", dayfirst=True)


def _transform_base_sheet(df: pd.DataFrame, sheet_name: str = "BASE PLANO PROYECCION") -> tuple[pd.DataFrame, dict[str, int]]:
    audit: dict[str, object] = {"raw_rows": int(len(df))}

    validate_columns(df, REQUIRED_COLUMNS, sheet_name)
    df = df[SOURCE_COLUMNS].copy()

    df = df[df["finca"].notna()].copy()
    audit["rows_after_dropna_finca"] = int(len(df))

    df["finca"] = normalize_finca_series(df["finca"])
    df["bloque"] = pd.to_numeric(df["bloque"], errors="coerce").astype("Int64").astype(str)
    df["variedad"] = df["variedad"].astype(str).str.strip()
    df["cosecha"] = df["cosecha"].astype(str).str.strip()
    df["nvari"] = df["nvari"].astype(str).str.strip().str.replace(r"\s+", "_", regex=True)

    fec_siem = pd.to_datetime(df["fec_siem"].apply(_parse_fec_siem))
    audit["invalid_fec_siem_rows"] = int(fec_siem.isna().sum())
    iso_week = fec_siem.dt.isocalendar()["week"].astype("Int64").astype(str).str.zfill(2)
    df["yyww_siembra"] = fec_siem.dt.strftime("%y") + iso_week
    df = df.drop(columns=["fec_siem"])

    df["rev"] = pd.to_numeric(df["rev"], errors="coerce")
    df["amort"] = pd.to_numeric(df["amort"], errors="coerce")
    df["proyecta_quipus"] = pd.to_numeric(df["proyecta_quipus"], errors="coerce")

    df = df[OUTPUT_COLUMNS].reset_index(drop=True)
    audit["final_rows"] = int(len(df))

    return df, audit


def _load_lotes_siembra(input_path: str) -> pd.DataFrame:
    path = Path(normalize_path(input_path))
    if not path.exists():
        raise FileNotFoundError(f"No existe el archivo de lotes de siembra: {path}")

    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(col).strip() for col in df.columns]
    return df


def _transform_lotes_siembra(df: pd.DataFrame) -> pd.DataFrame:
    missing = LOTES_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Faltan columnas en Lotes_de_siembra.csv: {', '.join(sorted(missing))}")

    df = df[["Id", "Finca", "Bloque", "Variedad", "Semana de siembra"]].copy()
    df["finca"] = normalize_finca_series(df["Finca"])
    df["bloque"] = pd.to_numeric(df["Bloque"], errors="coerce").astype("Int64").astype(str)
    df["nvari"] = df["Variedad"].astype(str).str.strip().str.replace(r"\s+", "_", regex=True)
    df["yyww_siembra"] = pd.to_numeric(df["Semana de siembra"], errors="coerce").astype("Int64").astype(str).str.zfill(4)
    df["id_lote_siembra"] = pd.to_numeric(df["Id"], errors="coerce").astype("Int64")

    return df[JOIN_KEYS + ["id_lote_siembra"]]


def _attach_id_lote_siembra(df_planos: pd.DataFrame, df_lotes: pd.DataFrame) -> pd.DataFrame:
    duplicated_keys = df_lotes.duplicated(subset=JOIN_KEYS, keep=False)
    df_lotes_dedup = df_lotes[~duplicated_keys].drop_duplicates(subset=JOIN_KEYS)

    merged = df_planos.merge(df_lotes_dedup, on=JOIN_KEYS, how="left")
    return merged[FINAL_COLUMNS]


def _ajustes_mask(df_matched: pd.DataFrame) -> pd.Series:
    """Fila cambio si Factor (amort) != 1 o Mueve semanas (rev) != 0."""
    factor = df_matched["amort"]
    mueve_semanas = df_matched["rev"]
    return (factor.notna() & (factor != 1)) | (mueve_semanas.notna() & (mueve_semanas != 0))


def _build_ajustes_export(df_matched: pd.DataFrame) -> pd.DataFrame:
    """Filtra Factor!=1 o Mueve semanas!=0, y arma las columnas finales.

    Incluye "finca" ademas de AJUSTES_OUTPUT_COLUMNS para poder filtrar por
    finca al persistir en MySQL y al enviar el correo por finca; quien
    escriba el Excel a descargar/enviar debe quitarla antes (ver
    AJUSTES_OUTPUT_COLUMNS).
    """
    mask = _ajustes_mask(df_matched)
    df_ajustes = df_matched[mask].rename(columns=AJUSTES_COLUMN_MAP).copy()
    df_ajustes["Vigencia"] = 10
    df_ajustes["Bloqueado"] = 0
    return df_ajustes[AJUSTES_EXPORT_COLUMNS].reset_index(drop=True)


def _build_hoja2_export(df_matched: pd.DataFrame) -> pd.DataFrame:
    """Filas de ajuste (mismo filtro que _build_ajustes_export) en forma de
    Hoja2 de Subir_datos_de_proyecciones.xlsx: finca/bloque/variedad/cosecha/
    rev/amort, ambas fincas juntas (identificadas por la columna finca)."""
    mask = _ajustes_mask(df_matched)
    return df_matched[mask][TIKA_HOJA2_COLUMNS].reset_index(drop=True)


def _build_finca_email_body(finca_name: str, df_missing_finca: pd.DataFrame, ajustes_rows: int) -> str:
    body = (
        f"<p>Se adjunta <strong>ajustes_proyeccion_{finca_name.lower()}.xlsx</strong> ({ajustes_rows} fila(s)) "
        f"con el resultado final de {finca_name} ya cruzado con Lotes_de_siembra.csv: ID, Factor, Mueve "
        "semanas, Vigencia y Bloqueado, listo para subir.</p>"
    )
    if not df_missing_finca.empty:
        tabla = df_missing_finca[["bloque", "variedad", "cosecha", "nvari", "yyww_siembra"]].to_html(
            index=False, border=1
        )
        body += (
            f"<p>Ademas, se encontraron {len(df_missing_finca)} registro(s) de {finca_name} que no "
            "cruzaron con ningun Id en Lotes_de_siembra.csv (bloque/variedad/semana de siembra). "
            f"Estos registros se excluyeron de planos_proyeccion.csv:</p>"
            f"{tabla}"
        )
    return body


def _notify_ajustes_por_finca(df_ajustes: pd.DataFrame, df_missing: pd.DataFrame, ajustes_dir: Path) -> dict[str, object]:
    """Genera un Excel de ajustes por finca y lo envia por correo a cada una.

    Nunca lanza excepcion: los datos ya quedaron persistidos en MySQL de
    todas formas, asi que un problema de envio se registra en el log pero
    no debe tumbar la corrida del ETL.
    """
    resultados: dict[str, object] = {}

    for finca_code in FINCA_CODES:
        finca_name = FINCA_NAMES[finca_code]
        df_ajustes_finca = df_ajustes[df_ajustes["finca"] == finca_code][AJUSTES_OUTPUT_COLUMNS].reset_index(
            drop=True
        )
        df_missing_finca = df_missing[df_missing["finca"] == finca_code].reset_index(drop=True)

        finca_output_file = ajustes_dir / f"ajustes_proyeccion_{finca_name.lower()}.xlsx"
        with pd.ExcelWriter(finca_output_file, engine="openpyxl") as writer:
            df_ajustes_finca.to_excel(writer, index=False, sheet_name="ajustes")

        resultados[finca_code] = {
            "output": str(finca_output_file),
            "ajustes_rows": int(len(df_ajustes_finca)),
            "missing_rows": int(len(df_missing_finca)),
        }

        if df_ajustes_finca.empty and df_missing_finca.empty:
            logger.info(
                "planos_proyeccion: nada que reportar para %s; no se envia correo.", finca_name
            )
            continue

        destinatarios = [
            addr.strip()
            for addr in (getattr(settings, FINCA_EMAIL_SETTINGS[finca_code], None) or [])
            if str(addr).strip()
        ]
        if not destinatarios:
            logger.warning(
                "planos_proyeccion: %s esta vacio; no se envia correo de ajustes a %s.",
                FINCA_EMAIL_SETTINGS[finca_code],
                finca_name,
            )
            continue

        try:
            send_email(
                to=destinatarios,
                subject=f"{AJUSTES_EMAIL_SUBJECT} ({finca_name})",
                body=_build_finca_email_body(finca_name, df_missing_finca, len(df_ajustes_finca)),
                html=True,
                attachments=[finca_output_file],
            )
        except MailNotConfiguredError as exc:
            logger.warning("planos_proyeccion: no se envio el correo de ajustes de %s: %s", finca_name, exc)
        except Exception:  # noqa: BLE001
            logger.exception("planos_proyeccion: fallo inesperado enviando el correo de ajustes de %s.", finca_name)

    return resultados


def _fill_tika_workbook(df_hoja2: pd.DataFrame, template_path: Path, output_path: Path) -> Path:
    """Copia la plantilla dejando Hoja1 solo con sus encabezados (sin filas
    de datos, se llenan manualmente en el flujo de Tika) y Hoja2 con las
    filas de ajuste."""
    wb = openpyxl.load_workbook(template_path)
    hoja1 = wb["Hoja1"]
    if hoja1.max_row > 1:
        hoja1.delete_rows(2, hoja1.max_row - 1)

    hoja2 = wb["Hoja2"]
    if hoja2.max_row > 1:
        hoja2.delete_rows(2, hoja2.max_row - 1)
    for row in df_hoja2[TIKA_HOJA2_COLUMNS].itertuples(index=False):
        hoja2.append(list(row))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


def _build_tika_upload_body(ajustes_filenames: list[str]) -> str:
    archivos = " y ".join(f"<strong>{name}</strong>" for name in ajustes_filenames)
    return (
        f"<p>Se adjuntan los archivos de ajustes por finca ({archivos}) y la plantilla "
        "<strong>Subir_datos_de_proyecciones.xlsx</strong> (Hoja2 ya diligenciada; Hoja1 pendiente).</p>"
        "<p>Pasos a seguir:</p>"
        "<ol>"
        f'<li>Subir los archivos de ajustes por finca ({archivos}) a '
        f'<a href="{TIKA_UPLOAD_URL}">{TIKA_UPLOAD_URL}</a> usando el importador alli dispuesto.</li>'
        "<li>Una vez subidos, en Tika ir al menu <strong>Curvas khipus</strong>, descargar los datos "
        "filtrando desde la semana siguiente a la actual, y exportar en Excel.</li>"
        "<li>Con ese Excel, hacer una limpieza suave: dejar en el campo <strong>Estado</strong> solo "
        '"Sembrada" y quitar el bloque <strong>Confinados</strong>.</li>'
        "<li>Pegar ese resultado en la <strong>Hoja1</strong> de la plantilla "
        "Subir_datos_de_proyecciones.xlsx adjunta (Hoja2 ya viene lista, no se toca).</li>"
        "</ol>"
    )


def _notify_tika_ajuste(
    df_matched: pd.DataFrame, ajustes_files: dict[str, dict[str, object]], output_dir: Path
) -> dict[str, object] | None:
    """Genera Subir_datos_de_proyecciones.xlsx (Hoja2 con los ajustes) a
    partir de la plantilla de red y lo envia por correo junto con los
    archivos de ajustes por finca (los que hay que subir primero a Tika).

    ajustes_files es el resultado de _notify_ajustes_por_finca: por cada
    finca trae la ruta del ajustes_proyeccion_<finca>.xlsx ya escrito en
    output_dir (siempre se escribe, incluso si no se envio correo por
    finca).

    Nunca lanza excepcion, igual que _notify_ajustes_por_finca: un problema
    de plantilla/envio queda en el log pero no debe tumbar el ETL.
    """
    template_path = Path(normalize_path(settings.PLANOS_PROYECCION_TIKA_TEMPLATE_PATH))
    if not template_path.exists():
        logger.warning(
            "planos_proyeccion: no existe la plantilla Tika en %s; no se envia el correo.", template_path
        )
        return None

    ajustes_paths = [Path(info["output"]) for info in ajustes_files.values() if info.get("output")]
    missing_paths = [str(path) for path in ajustes_paths if not path.exists()]
    if missing_paths:
        logger.warning(
            "planos_proyeccion: faltan archivos de ajustes por finca (%s); no se envia el correo Tika.",
            ", ".join(missing_paths),
        )
        return None

    destinatarios = [addr.strip() for addr in (settings.PLANOS_PROYECCION_TIKA_EMAILS or []) if str(addr).strip()]
    if not destinatarios:
        logger.warning(
            "planos_proyeccion: PLANOS_PROYECCION_TIKA_EMAILS esta vacio; no se envia el correo Tika."
        )
        return None

    df_hoja2 = _build_hoja2_export(df_matched)
    output_file = output_dir / "Subir_datos_de_proyecciones.xlsx"
    _fill_tika_workbook(df_hoja2, template_path, output_file)

    cc = [addr.strip() for addr in (settings.PLANOS_PROYECCION_TIKA_CC_EMAILS or []) if str(addr).strip()]
    attachments = [*ajustes_paths, output_file]

    try:
        send_email(
            to=destinatarios,
            subject=TIKA_EMAIL_SUBJECT,
            body=_build_tika_upload_body([path.name for path in ajustes_paths]),
            html=True,
            cc=cc or None,
            attachments=attachments,
        )
    except MailNotConfiguredError as exc:
        logger.warning("planos_proyeccion: no se envio el correo Tika: %s", exc)
        return None
    except Exception:  # noqa: BLE001
        logger.exception("planos_proyeccion: fallo inesperado enviando el correo Tika.")
        return None

    return {
        "output": str(output_file),
        "hoja2_rows": int(len(df_hoja2)),
        "ajustes_files": [str(path) for path in ajustes_paths],
        "to": destinatarios,
        "cc": cc,
    }


def generate_planos_proyeccion(debug: bool = False) -> str | tuple[str, dict[str, int]]:
    output_path = settings.PLANOS_PROYECCION_OUTPUT_PATH
    lotes_path = settings.LOTES_SIEMBRA_INPUT_PATH

    frames: list[pd.DataFrame] = []
    audit: dict[str, object] = {"por_finca": {}}
    for finca_code in FINCA_CODES:
        df_raw = _load_base_from_staging(finca_code)
        if df_raw.empty:
            logger.warning(
                "planos_proyeccion: no hay filas en %s para finca %s (la macro no ha subido datos todavia).",
                STAGING_TABLE_NAME,
                finca_code,
            )
            audit["por_finca"][finca_code] = {"raw_rows": 0}
            continue

        df_file, file_audit = _transform_base_sheet(df_raw, STAGING_TABLE_NAME)
        frames.append(df_file)
        audit["por_finca"][finca_code] = file_audit

    if not frames:
        raise RuntimeError(
            f"No hay datos en {STAGING_TABLE_NAME} para ninguna finca; "
            "verifica que las macros de Excel ya subieron informacion."
        )

    df = pd.concat(frames, ignore_index=True)
    audit["final_rows"] = int(len(df))
    audit["finca_counts"] = df["finca"].value_counts(dropna=False).to_dict()

    df_lotes_raw = _load_lotes_siembra(lotes_path)
    df_lotes = _transform_lotes_siembra(df_lotes_raw)
    df = _attach_id_lote_siembra(df, df_lotes)

    matched_mask = df["id_lote_siembra"].notna()
    df_matched = df[matched_mask].reset_index(drop=True)
    df_missing = df[~matched_mask].reset_index(drop=True)
    audit["matched_id_lote_siembra"] = int(len(df_matched))
    audit["missing_id_lote_siembra"] = int(len(df_missing))

    output_file = Path(normalize_path(output_path))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_matched.to_csv(output_file, index=False)
    dataframe_to_sql(df_matched, MYSQL_TABLE_NAME, if_exists="replace")

    df_ajustes = _build_ajustes_export(df_matched)
    dataframe_to_sql(
        df_ajustes.rename(columns=AJUSTES_SQL_COLUMN_MAP), AJUSTES_MYSQL_TABLE_NAME, if_exists="replace"
    )

    ajustes_output_file = Path(normalize_path(settings.PLANOS_PROYECCION_AJUSTES_OUTPUT_PATH))
    ajustes_output_file.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(ajustes_output_file, engine="openpyxl") as writer:
        df_ajustes[AJUSTES_OUTPUT_COLUMNS].to_excel(writer, index=False, sheet_name="ajustes")
    audit["ajustes_rows"] = int(len(df_ajustes))
    audit["ajustes_output"] = str(ajustes_output_file)

    resultados_ajustes = _notify_ajustes_por_finca(df_ajustes, df_missing, ajustes_output_file.parent)
    audit["por_finca_ajustes"] = resultados_ajustes
    audit["tika_ajuste"] = _notify_tika_ajuste(df_matched, resultados_ajustes, ajustes_output_file.parent)

    if debug:
        return str(output_file), audit
    return str(output_file)
