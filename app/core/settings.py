"""
Configuración de la aplicación usando variables de entorno.

Para usar variables de entorno, crea un archivo .env en la raíz del proyecto
o exporta las variables antes de ejecutar la aplicación.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración de la aplicación."""
    
    # Información de la aplicación
    APP_NAME: str = "Portal de Datos Inverpalmas"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    APP_ENV: str = "local"

    # Ruta por defecto del archivo DBF
    DEFAULT_DBF_PATH: str = r"\\svrinverpalmas\produc\LD_BCULT\hijos2026.dbf"

    # Montaje SMB/CIFS para contenedores
    SMB_SERVER: str = "172.10.18.2"
    SMB_SHARE: str = "produc"
    SMB_MOUNT_ROOT: str = "/mnt/smb"
    SMB_MOUNT_PATH: str = "/mnt/smb/produc"
    SMB_USERNAME: str = ""
    SMB_PASSWORD: str = ""
    SMB_DOMAIN: str = ""
    SMB_OPTIONS: str = "username=,uid=1000,gid=1000,vers=3.0,iocharset=utf8,sec=ntlm"
    SMB_MOUNT_RETRY_SECONDS: int = 10
    
    # Límites y paginación
    DEFAULT_LIMIT: int = 100
    MAX_LIMIT: int = 10000
    
    # Codificaciones a intentar al leer archivos DBF
    DBF_ENCODINGS: list[str] = ["latin1", "cp1252", "utf-8", "iso-8859-1"]

    # Conexión a base de datos (MySQL/MariaDB)
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = "informes"

    # Salida del Excel
    EXCEL_OUTPUT_DIR: str = r"\\svrinverpalmas\Usuarios\Outputs"
    EXCEL_FILENAME: str = "consultor_archivos_dbf.xlsx"

    # ETL producto procesado
    PPROCESADO_2021_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2021.dbf"
    PPROCESADO_2022_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2022.dbf"
    PPROCESADO_2023_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2023.dbf"
    PPROCESADO_2024_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2024.dbf"
    PPROCESADO_2025_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2025.dbf"
    PPROCESADO_CURRENT_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado.dbf"
    PPROCESADO_INCREMENTAL_START_DATE: str = "2025-12-29"
    PPROCESADO_OUTPUT_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado.csv"
    PPROCESADO_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROS", "ROC"]
    PPROCESADO_FUENTE_FILTER: list[str] = [
        "AjFito Cultivo DFFV",
        "Dirigida Finca-Flor-Variedad",
        "Dirigida",
        "Fitosanitario Cultivo",
        "AjFito Cultivo",
        "Clasificacion",
        "AjFito por Finca/Flor PP"
    ]

    # ETL proyecciones
    PROYECCIONES_BASE_DIR: str = r"\\svrinverpalmas\produc\basetdinamica"
    PROYECCIONES_DBF_FILES: list[str] = [
        "Proyecciones_2025-1S.dbf",
        "Proyecciones_2024-1S.dbf",
        "proyecciones.dbf",
    ]
    PROYECCIONES_OUTPUT_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\proyecciones.csv"
    PROYECCIONES_BUDGET_START_DATE: str = "2024-01-01"
    PROYECCIONES_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROC", "ROS"]
    PROYECTAR_ROSAS_OUTPUT_PATH: str = r"C:\Users\ESTADISTICA\Documents\fastapi-form\output\proyeccion_rosas.csv"

    # Cargas DBF directas (menu separado)
    LOAD_LD_BCULT_DIR: str = r"\\172.10.18.2\produc\ld_bcult"
    LOAD_MGCOL_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mgcol.dbf"
    LOAD_MFIES_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mfies.dbf"
    LOAD_MCOSE_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mcose.dbf"
    LOAD_MCAUS_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mcaus.dbf"
    LOAD_MVARI_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mvari.dbf"
    LOAD_HIJOS_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\hijos2026.dbf"
    LOAD_DESCARTA_CURVA_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\descarta_curva.dbf"
    LOAD_RFLO_NACIONAL_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\rflo2026.dbf"
    LOAD_RFLO_NACIONAL_TABLES: list[str] = ["rflo2026"]
    LOAD_LONAS_FILES: list[str] = ["lonas2026.dbf", "lonas2025.dbf", "lonas2024.dbf", "lonas2023.dbf", "lonas2022.dbf", "lonas2021.dbf"]
    LOAD_FUSARIUM_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\historico_fusarium.dbf"
    LOAD_PLANO_SIEMBRA_RESUMIDO_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\plano_de_siembra_resumido.dbf"
    LOAD_VARIEDADES_FLOR_FILTER: list[str] = ["CLA", "CM0", "VCL", "VCM", "ROC", "ROS"]
    LOAD_METAS_FLOR_FILTER: list[str] = ["CLA", "CM0", "VCL", "VCM"]

    # ETL produccion por picos
    PRODUCCION_PICOS_OUTPUT_PATH: str = r"\\svrinverpalmas\usuarios\Outputs\produccion_por_picos.csv"
    PRODUCCION_PICOS_FLOR_FILTER: list[str] = ["CLA", "CM0"]
    PRODUCCION_PICOS_DATE_START: str = "2024-01-01"
    PRODUCCION_PICOS_DATE_END: str = "2028-12-31"

    # ETL nuevos scripts de load/
    PROCESS_GUARDE_INPUT_PATH: str = r"\\172.10.18.2\produc\BASETDINAMICA\TIKA_SALDOS_CTO.csv"
    PROCESS_GUARDE_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\guarde_procesado.xlsx"
    PROCESS_SIEMBRAS_OUTPUT_PATH: str = r"\\svrinverpalmas\usuarios\propagacion\lorena\tika\plano nuevo siembra.xlsx"
    SIEMBRAS_TEO_REAL_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\siembras teo vs real.xlsx"

    # ETL quipus vs proyecciones
    QUIPUS_DATE_START: str = "2023-01-01"
    QUIPUS_DATE_END: str = "2028-12-31"
    QUIPUS_PLANO_PATH: str = r"//svrinverpalmas/usuarios/Hilder/Data/tika-plano-siembra-todo.csv"
    QUIPUS_TIKA_DIR: str = r"//svrinverpalmas/usuarios/Hilder/Data/tika/quipus"
    QUIPUS_TIKA_FILE_PREFIX: str = "tika-quipus"
    QUIPUS_OUTPUT_PATH: str = r"//svrinverpalmas/usuarios/Hilder/Data/quipus.csv"
    QUIPUS_VS_PROY_OUTPUT_PATH: str = r"//svrinverpalmas/usuarios/Hilder/Data/quipus_vs_proy.csv"
    QUIPUS_EXCEL_OUTPUT_PATH: str = r"C:\Users\ESTADISTICA\Qsync\POSCOSECHA MERCADEO\Datos Quipus\datos.xlsx"
    QUIPUS_FARM_MAP: dict[str, str] = {"INVERPALMAS": "001", "PALERMO": "002"}
    QUIPUS_FLOWER_MAP: dict[str, str] = {"CLAVEL": "CLA", "MINICLAVEL": "CM0"}

    # ETL comparar por picos vs demanda
    PICOS_TIKA_MODELO: int = 485
    PICOS_TALLOS_FACTOR: float = 0.9
    PICOS_DEMANDA_PATH: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\demanda_27-28v2.csv"
    PICOS_OUTPUT_PATH: str = r"\\svrinverpalmas\produc\BASETDINAMICA\compara_pto_proy_real.csv"
    PICOS_OUTPUT_DIFERENCIAS_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\flor_color_diferencias.csv"
    PICOS_SEMANA_INICIO: int = 2527
    PICOS_SEMANA_FIN: int = 2620

    # ETL dirigidas analyzer
    DIRIGIDAS_ARREGLOS_PATH: str = r"//svrinverpalmas/usuarios/Hilder/Data/tabla_arreglos.xlsx"
    DIRIGIDAS_DATE_MIN: str = "2026-02-01"
    DIRIGIDAS_MUESTRAS: int = 5
    DIRIGIDAS_TALLOS_MIN: int = 1000
    DIRIGIDAS_LONAS_SEMANA: int = 65
    DIRIGIDAS_OUTPUT_PATH: str = r"//svrinverpalmas/usuarios/produccion/Sofia/dirigidas/datos/Para dirigida PC.xlsx"
    DIRIGIDAS_BLOQUE_OUTPUT_PATH: str = r"//svrinverpalmas/usuarios/produccion/Sofia/dirigidas/datos/para dirigida por bloque.xlsx"
    DIRIGIDAS_RESUMEN_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\dirigidas_resumen.xlsx"

    # ETL pedidos surtidos (genera ventas ultimo año.xlsx)
    PEDIDOS_SURTIDO_DBF_PATH: str = r"//svrinverpalmas/newfact/DINAMICA/PEDIDOS_surtido.dbf"
    PEDIDOS_SURTIDO_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROC", "ROS"]
    PEDIDOS_SURTIDO_PROYECCION_ANIO: int = 2026

    # ETL comparativo Tika / produccion / despachos
    COMPARE_TIKA_DEFAULT_MODELS: list[int] = [161, 328, 485, 405]
    COMPARE_TIKA_TALLOS_FACTOR: float = 0.9
    COMPARE_TIKA_D_CUTOFF_DATE: str = "2026-01-05"
    COMPARE_TIKA_DESPACHOS_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\ventas ultimo año.xlsx"
    COMPARE_TIKA_QUIPUS_EXCEL_PATH: str = r"C:\Users\ESTADISTICA\Qsync\POSCOSECHA MERCADEO\Datos Quipus\datos.xlsx"
    COMPARE_TIKA_DEMANDA_PATH: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\demanda_27-28v3.csv"
    COMPARE_TIKA_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\comparar producción.csv"
    COMPARE_TIKA_OUTPUT_EXCEL_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\comparar producción.xlsx"

    # ETL anomalias lonas
    ANOMALIAS_OUTPUT_DIR: str = r"\\svrinverpalmas\Usuarios\Outputs"
    ANOMALIAS_SEMANA_INICIO: int = 2601
    ANOMALIAS_SEMANA_FIN: int = 2653

    # ETL tabla curvas clavel
    TABLA_CURVAS_CLAVEL_DBF_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\Curvas_por_Tiqueteado_EC.dbf"
    TABLA_CURVAS_CLAVEL_OUTPUT_CSV: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\tabla_curvas_clavel.csv"
    CURVAS_PRODUCCION_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\bd_pipeline.xlsx"
    CURVAS_PRODUCCION_RESUMEN_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\resumen_variedades.csv"
    CURVAS_PRODUCCION_FILTRADA_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\curvas_filtradas_variedades.csv"
    CALIDADES_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\calidades_aporte.csv"
    CALIDADES_FUENTE_FILTER: list[str] = ["AjFito Cultivo DFFV", "Dirigida Finca-Flor-Variedad"]
    APORTES_GRADOS_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\aportes_por_grado.csv"
    FUSARIUM_VARIETIES_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\fusarium_variedades.csv"
    PRODUCTIVIDADES_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Outputs\reporte de productividades.xlsx"

    # Ejecucion ETL
    ETL_MAX_WORKERS: int = 3
    
    # Zona horaria
    TIMEZONE: str = "America/Bogota"  # UTC-5 (Colombia)
    
    # Directorios
    BASE_DIR: Path = Path(__file__).resolve().parents[2]
    STATIC_DIR: Path = BASE_DIR / "static"
    TEMPLATES_DIR: Path = BASE_DIR / "templates"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    def _coerce_scalar(self, value: Any, annotation: Any) -> Any:
        if annotation in {Any, object}:
            return value

        if annotation is bool:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "y", "si", "sí"}
            return bool(value)

        if annotation in {int, float}:
            if isinstance(value, str):
                token = value.strip()
                if token == "":
                    return 0 if annotation is int else 0.0
                return int(token) if annotation is int else float(token)
            return annotation(value)

        if annotation is str:
            return str(value)

        origin = get_origin(annotation)
        if origin in {list, tuple, set}:
            sequence = value if isinstance(value, (list, tuple, set)) else [value]
            item_type = get_args(annotation)[0] if get_args(annotation) else str
            return [self._coerce_scalar(item, item_type) for item in sequence]

        if annotation is dict or origin is dict:
            if isinstance(value, dict):
                return value
            return value

        return value

    def _coerce_value(self, key: str, value: Any) -> Any:
        field = self.model_fields.get(key)
        if field is None:
            return value

        annotation = field.annotation
        origin = get_origin(annotation)
        args = get_args(annotation)

        if isinstance(value, str):
            token = value.strip()
            if token == "":
                return ""

            if annotation is bool:
                return self._coerce_scalar(value, annotation)

            if annotation in {int, float}:
                return self._coerce_scalar(value, annotation)

            if origin in {list, tuple, set}:
                parsed: Any = token
                if token.startswith("["):
                    try:
                        parsed = json.loads(token)
                    except json.JSONDecodeError:
                        parsed = token
                elif any(sep in token for sep in (";", ",")):
                    parsed = [part.strip() for part in token.replace(";", ",").split(",") if part.strip()]

                if isinstance(parsed, (list, tuple, set)):
                    item_type = args[0] if args else str
                    return [self._coerce_scalar(item, item_type) for item in parsed]
                if isinstance(parsed, str):
                    item_type = args[0] if args else str
                    if item_type is str:
                        return [parsed]
                    return [self._coerce_scalar(parsed, item_type)]
                return parsed

            if annotation is dict or origin is dict:
                if token.startswith("{"):
                    try:
                        return json.loads(token)
                    except json.JSONDecodeError:
                        return value
                return value

        if annotation is bool:
            return self._coerce_scalar(value, annotation)

        if annotation in {int, float}:
            return self._coerce_scalar(value, annotation)

        if origin in {list, tuple, set}:
            sequence = value if isinstance(value, (list, tuple, set)) else [value]
            item_type = args[0] if args else str
            return [self._coerce_scalar(item, item_type) for item in sequence]

        if annotation is dict or origin is dict:
            if isinstance(value, dict):
                return value
            return value

        return value

    def apply_overrides(self, overrides: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(overrides, dict):
            raise ValueError("Las sobreescrituras deben ser un diccionario.")

        applied: dict[str, Any] = {}
        for key, value in overrides.items():
            if key not in type(self).model_fields:
                raise ValueError(f"No existe la configuración '{key}' en la aplicación.")
            coerced = self._coerce_value(key, value)
            setattr(self, key, coerced)
            applied[key] = coerced
        return applied

    def reset_to_defaults(self) -> dict[str, Any]:
        restored: dict[str, Any] = {}
        for key, field in type(self).model_fields.items():
            default_value = field.default
            if default_value is not None:
                setattr(self, key, default_value)
                restored[key] = default_value
            else:
                setattr(self, key, None)
                restored[key] = None
        return restored


def _load_persistent_overrides() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / ".app_config_overrides.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


# Instancia global de configuración
settings = Settings()
settings.apply_overrides(_load_persistent_overrides())
