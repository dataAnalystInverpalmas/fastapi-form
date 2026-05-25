"""
Configuración de la aplicación usando variables de entorno.

Para usar variables de entorno, crea un archivo .env en la raíz del proyecto
o exporta las variables antes de ejecutar la aplicación.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuración de la aplicación."""
    
    # Información de la aplicación
    APP_NAME: str = "Portal de Datos Inverpalmas"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Ruta por defecto del archivo DBF
    DEFAULT_DBF_PATH: str = r"\\svrinverpalmas\produc\LD_BCULT\hijos2026.dbf"
    
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
    EXCEL_FILENAME: str = "labores_de_siembra.xlsx"

    # ETL producto procesado
    PPROCESADO_2024_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2024.dbf"
    PPROCESADO_2025_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado_2025.dbf"
    PPROCESADO_CURRENT_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado.dbf"
    PPROCESADO_OUTPUT_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\pprocesado.csv"
    PPROCESADO_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROS", "ROC"]
    PPROCESADO_FUENTE_FILTER: list[str] = [
        "AjFito Cultivo DFFV",
        "Dirigida Finca-Flor-Variedad",
        "Dirigida",
        "Fitosanitario Cultivo",
        "AjFito Cultivo"
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

    # Cargas DBF directas (menu separado)
    LOAD_LD_BCULT_DIR: str = r"\\svrinverpalmas\produc\ld_bcult"
    LOAD_MGCOL_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mgcol.dbf"
    LOAD_MFIES_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mfies.dbf"
    LOAD_MCOSE_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mcose.dbf"
    LOAD_MCAUS_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mcaus.dbf"
    LOAD_MVARI_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\ld_mvari.dbf"
    LOAD_HIJOS_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\hijos2026.dbf"
    LOAD_DESCARTA_CURVA_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\descarta_curva.dbf"
    LOAD_RFLO_NACIONAL_PATH: str = r"\\svrinverpalmas\produc\ld_bcult\rflo2026.dbf"
    LOAD_RFLO_NACIONAL_TABLES: list[str] = ["rflo2026"]
    LOAD_LONAS_FILES: list[str] = ["lonas2026.dbf", "lonas2025.dbf", "lonas2024.dbf"]
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
    PROCESS_SIEMBRAS_OUTPUT_PATH: str = r"\\svrinverpalmas\usuarios\produccion\Sofia\tika\plano nuevo siembra.xlsx"
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
    PICOS_DEMANDA_PATH: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\demanda_jun24-2526_abr24-2653_sep25-2752_v5.csv"
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
    COMPARE_TIKA_DEMANDA_PATH: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\demanda_jun24-2526_abr24-2653_sep25-2752_v5.csv"
    COMPARE_TIKA_OUTPUT_PATH: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\comparar producción.csv"
    COMPARE_TIKA_OUTPUT_EXCEL_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\comparar producción.xlsx"

    # ETL anomalias lonas
    ANOMALIAS_OUTPUT_DIR: str = r"\\svrinverpalmas\Usuarios\Outputs"
    ANOMALIAS_SEMANA_INICIO: int = 2601
    ANOMALIAS_SEMANA_FIN: int = 2653

    # ETL tabla curvas clavel
    TABLA_CURVAS_CLAVEL_DBF_PATH: str = r"\\svrinverpalmas\produc\basetdinamica\Curvas_por_Tiqueteado_EC.dbf"
    TABLA_CURVAS_CLAVEL_OUTPUT_CSV: str = r"\\svrinverpalmas\Usuarios\Hilder\Data\tabla_curvas_clavel.csv"

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


# Instancia global de configuración
settings = Settings()
