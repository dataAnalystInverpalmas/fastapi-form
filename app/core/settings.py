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
    DEFAULT_DBF_PATH: str = r"\\172.10.18.2\produc\LD_BCULT\hijos2026.dbf"

    # Codigo de "todas las fincas consolidadas" usado por varios pipelines
    # (production_pipeline, qualities_pipeline, fusarium_pipeline,
    # productivity_varieties_report, proyectar_rosas).
    ALL_FARMS_CODE: str = "000"

    # Montaje SMB/CIFS para contenedores. Estos SI se usan en tiempo de
    # ejecucion (app/services/utils/pathing.py y network_health.py) para
    # traducir rutas UNC \\servidor\... al punto de montaje local en Linux.
    # Las credenciales de montaje (usuario/password/dominio/opciones) NO
    # viven aqui: esas las usa unicamente scripts/entrypoint.sh al arrancar
    # el contenedor (antes de que la app Python exista), asi que configurarlas
    # es responsabilidad del entorno/docker-compose, no de esta pagina.
    SMB_SERVER: str = "172.10.18.2"
    # Nombres alternos del mismo servidor. Las rutas de la app usan la IP,
    # pero el servidor tambien responde por nombre NetBIOS/DNS y un operador
    # puede escribir una ruta asi desde /config: se resuelven igual que la IP.
    SMB_SERVER_ALIASES: list[str] = ["svrinverpalmas"]
    # Todos los shares del servidor que la app necesita. scripts/entrypoint.sh
    # monta cada uno en SMB_MOUNT_ROOT/<share> y resolve_network_path traduce
    # \\<servidor>\<share>\... a ese punto de montaje, sin distinguir
    # mayusculas (las rutas de settings mezclan Usuarios/usuarios). Si se
    # agrega un job que lea un share nuevo, hay que sumarlo aqui.
    #
    # Es texto separado por comas, no list[str], a proposito: la misma
    # variable de entorno la leen este Settings y scripts/entrypoint.sh (bash).
    # pydantic exige JSON para los campos lista, y ese JSON es incomodo en
    # bash; con texto plano las dos partes leen el mismo valor.
    # Usar pathing.get_configured_shares() para obtenerlo ya separado.
    SMB_SHARES: str = "produc,Usuarios,newfact"
    # Share principal: es el que se reporta en /health y el unico con punto de
    # montaje configurable aparte (SMB_MOUNT_PATH); el resto va a
    # SMB_MOUNT_ROOT/<share>.
    SMB_SHARE: str = "produc"
    SMB_MOUNT_ROOT: str = "/mnt/smb"
    SMB_MOUNT_PATH: str = "/mnt/smb/produc"

    # Codificaciones a intentar al leer archivos DBF
    DBF_ENCODINGS: list[str] = ["latin1", "cp1252", "utf-8", "iso-8859-1"]

    # Conexión a base de datos (MySQL/MariaDB)
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = "informes"

    # Correo electrónico (SMTP) - notificaciones de la app / jobs ETL.
    # Las credenciales quedan en .env (no se suben al repo); SMTP_ENABLED
    # actua como interruptor general para no romper el envio si el
    # servidor SMTP no esta configurado todavia.
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    SMTP_USE_SSL: bool = False
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Portal de Datos Inverpalmas"
    SMTP_TIMEOUT: int = 10

    # Salida del Excel
    EXCEL_OUTPUT_DIR: str = r"\\172.10.18.2\Usuarios\Outputs"
    EXCEL_FILENAME: str = "consultor_archivos_dbf.xlsx"

    # ETL producto procesado
    PPROCESADO_2021_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado_2021.dbf"
    PPROCESADO_2022_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado_2022.dbf"
    PPROCESADO_2023_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado_2023.dbf"
    PPROCESADO_2024_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado_2024.dbf"
    PPROCESADO_2025_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado_2025.dbf"
    PPROCESADO_CURRENT_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado.dbf"
    PPROCESADO_INCREMENTAL_START_DATE: str = "2025-12-29"
    PPROCESADO_OUTPUT_PATH: str = r"\\172.10.18.2\produc\basetdinamica\pprocesado.csv"
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
    PROYECCIONES_BASE_DIR: str = r"\\172.10.18.2\produc\basetdinamica"
    PROYECCIONES_DBF_FILES: list[str] = [
        "Proyecciones_2025-1S.dbf",
        "Proyecciones_2024-1S.dbf",
        "proyecciones.dbf",
    ]
    PROYECCIONES_OUTPUT_PATH: str = r"\\172.10.18.2\produc\basetdinamica\proyecciones.csv"
    PROYECCIONES_BUDGET_START_DATE: str = "2024-01-01"
    PROYECCIONES_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROC", "ROS"]
    PROYECTAR_ROSAS_OUTPUT_PATH: str = r"\\172.10.18.2\usuarios\Outputs\proyeccion_rosas.csv"
    PROYECTAR_ROSAS_DECAY_FACTOR: float = 0.9
    PROYECTAR_ROSAS_PCT_TOLERANCE: float = 0.001
    PROYECTAR_ROSAS_TIPO_REAL: list[str] = ["RE"]
    PROYECTAR_ROSAS_TIPO_PODA_SELECTIVA: list[str] = ["S1", "S2", "S3"]

    # ETL planos proyeccion (sistemas Palermo + Palmas). Cada finca sube su
    # plano por macro de Excel a MySQL (tabla stg_plano_proyeccion via el
    # endpoint PHP plano_proyeccion_upload.php); este job ya no lee ningun
    # .xlsm directamente.
    PLANOS_PROYECCION_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\planos_proyeccion.csv"
    PLANOS_PROYECCION_AJUSTES_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\ajustes_proyeccion.xlsx"
    # Subir_Proyeccion.xlsx: plantilla Subir_datos_de_proyecciones.xlsx con
    # sus dos hojas llenas y lista para subir (job planos_proyeccion_hoja1):
    # proyeccion desde la hoja "datos" de datos.xlsx (quipus_vs_proy) y
    # ajustes desde planos_proyeccion.csv.
    PLANOS_PROYECCION_HOJA1_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\Subir_Proyeccion.xlsx"
    # Destinatarios de ajustes_proyeccion_<finca>.xlsx por finca. Mientras se
    # prueba, ambos apuntan a estadistica@inverpalmas.com; los reales seran
    # palermo@inverpalmas.com (Palermo) y produccion@inverpalmas.com (Palmas).
    PLANOS_PROYECCION_AJUSTES_EMAILS_PALERMO: list[str] = ["estadistica@inverpalmas.com"]
    PLANOS_PROYECCION_AJUSTES_EMAILS_PALMAS: list[str] = ["estadistica@inverpalmas.com"]
    LOTES_SIEMBRA_INPUT_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\Lotes_de_siembra.csv"
    # Plantilla "Subir_datos_de_proyecciones.xlsx" que llena el job
    # planos_proyeccion_hoja1 para subir al sistema de cultivo.
    PLANOS_PROYECCION_TIKA_TEMPLATE_PATH: str = (
        r"\\172.10.18.2\Usuarios\produccion\Proyecciones\Subir_datos_de_proyecciones.xlsx"
    )
    # Destinatarios del correo con los ajustes por finca para cargar a Tika
    # (job planos_proyeccion).
    PLANOS_PROYECCION_TIKA_EMAILS: list[str] = ["logisticapc@inverpalmas.com"]
    PLANOS_PROYECCION_TIKA_CC_EMAILS: list[str] = ["estadistica@inverpalmas.com"]
    # Destinatarios de Subir_Proyeccion.xlsx para el sistema de cultivo (job
    # planos_proyeccion_hoja1).
    PLANOS_PROYECCION_CULTIVO_EMAILS: list[str] = ["logisticapc@inverpalmas.com"]
    PLANOS_PROYECCION_CULTIVO_CC_EMAILS: list[str] = ["estadistica@inverpalmas.com"]
    PROYECTAR_ROSAS_TIPO_PRUNING: list[str] = ["AR", "BA", "S1", "S2", "S3"]
    PROYECTAR_ROSAS_FECHA_INICIO_DEFAULT: str = "2021-01-01"
    PROYECTAR_ROSAS_FECHA_FIN_DEFAULT: str = "2026-12-31"

    # Cargas DBF directas (menu separado)
    LOAD_LD_BCULT_DIR: str = r"\\172.10.18.2\produc\ld_bcult"
    LOAD_MGCOL_PATH: str = r"\\172.10.18.2\produc\ld_bcult\ld_mgcol.dbf"
    LOAD_MFIES_PATH: str = r"\\172.10.18.2\produc\ld_bcult\ld_mfies.dbf"
    LOAD_MCOSE_PATH: str = r"\\172.10.18.2\produc\ld_bcult\ld_mcose.dbf"
    LOAD_MCAUS_PATH: str = r"\\172.10.18.2\produc\ld_bcult\ld_mcaus.dbf"
    LOAD_MVARI_PATH: str = r"\\172.10.18.2\produc\ld_bcult\ld_mvari.dbf"
    LOAD_HIJOS_PATH: str = r"\\172.10.18.2\produc\ld_bcult\hijos2026.dbf"
    LOAD_DESCARTA_CURVA_PATH: str = r"\\172.10.18.2\produc\ld_bcult\descarta_curva.dbf"
    LOAD_RFLO_NACIONAL_PATH: str = r"\\172.10.18.2\produc\ld_bcult\rflo2026.dbf"
    LOAD_RFLO_NACIONAL_TABLES: list[str] = ["rflo2026"]
    LOAD_LONAS_FILES: list[str] = ["lonas2026.dbf", "lonas2025.dbf", "lonas2024.dbf", "lonas2023.dbf", "lonas2022.dbf", "lonas2021.dbf"]
    # Años recientes (incluido el actual) que load_maestra_lonas borra y recarga;
    # los anteriores quedan intactos en ld_lonas. <= 0 fuerza recarga completa.
    LOAD_LONAS_ANIOS_RECARGA: int = 2
    LOAD_FUSARIUM_PATH: str = r"\\172.10.18.2\produc\basetdinamica\historico_fusarium.dbf"
    LOAD_PLANO_SIEMBRA_RESUMIDO_PATH: str = r"\\172.10.18.2\produc\basetdinamica\plano_de_siembra_resumido.dbf"
    LOAD_VARIEDADES_FLOR_FILTER: list[str] = ["CLA", "CM0", "VCL", "VCM", "ROC", "ROS"]
    LOAD_METAS_FLOR_FILTER: list[str] = ["CLA", "CM0", "VCL", "VCM"]
    LOAD_ARRE_ANIO_INICIO: int = 2020
    LOAD_ARRE_ANIO_FIN: int = 2026

    # ETL produccion por picos
    PRODUCCION_PICOS_OUTPUT_PATH: str = r"\\172.10.18.2\usuarios\Outputs\produccion_por_picos.csv"
    PRODUCCION_PICOS_FLOR_FILTER: list[str] = ["CLA", "CM0"]
    PRODUCCION_PICOS_TIPO_FILTER: list[str] = ["PT", "RE"]
    PRODUCCION_PICOS_VARIEDAD_PLACEHOLDER: str = "0000"
    PRODUCCION_PICOS_COSECHA_CORRECTIONS: dict[str, str] = {"OHS24": "OH24S"}
    PRODUCCION_PICOS_DATE_START: str = "2024-01-01"
    PRODUCCION_PICOS_DATE_END: str = "2028-12-31"

    # ETL bajas de exportado
    BAJAS_EXPORTADO_DATE_START: str = "2010-01-01"
    BAJAS_EXPORTADO_DATE_END: str = "2026-11-02"
    BAJAS_EXPORTADO_EXPORTADO_PATH: str = r"\\172.10.18.2\produc\basetdinamica\exportado.dbf"
    BAJAS_EXPORTADO_DOCU_DIR: str = r"\\172.10.18.2\produc\ld_bcult"
    BAJAS_EXPORTADO_DOCU_YEAR_START: int = 2010
    BAJAS_EXPORTADO_DOCU_YEAR_END: int = 2026
    BAJAS_EXPORTADO_TIPO_FILTRADO: str = "001"
    BAJAS_EXPORTADO_TIPO_TODOS: str = "010"
    BAJAS_EXPORTADO_GRADO_NAL: str = "NAL"
    BAJAS_EXPORTADO_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROC", "ROS"]

    # ETL nuevos scripts de load/
    PROCESS_GUARDE_INPUT_PATH: str = r"\\172.10.18.2\produc\BASETDINAMICA\TIKA_SALDOS_CTO.csv"
    PROCESS_GUARDE_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\guarde_procesado.xlsx"
    PROCESS_SIEMBRAS_OUTPUT_PATH: str = r"\\172.10.18.2\usuarios\propagacion\lorena\tika\plano nuevo siembra.xlsx"
    SIEMBRAS_TEO_REAL_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\siembras teo vs real.xlsx"
    SIEMBRAS_TEO_REAL_ANIOS: list[int] = [2024, 2025, 2026]
    SIEMBRAS_TEO_REAL_FLOR_FILTER: list[str] = ["CLA", "CM0"]

    # ETL quipus vs proyecciones
    QUIPUS_DATE_START: str = "2023-01-01"
    QUIPUS_DATE_END: str = "2028-12-31"
    QUIPUS_PLANO_PATH: str = r"//172.10.18.2/usuarios/Hilder/Data/tika-plano-siembra-todo.csv"
    QUIPUS_TIKA_DIR: str = r"//172.10.18.2/usuarios/Hilder/Data/tika/quipus"
    QUIPUS_TIKA_FILE_PREFIX: str = "tika-quipus"
    QUIPUS_OUTPUT_PATH: str = r"//172.10.18.2/usuarios/Hilder/Data/quipus.csv"
    QUIPUS_VS_PROY_OUTPUT_PATH: str = r"//172.10.18.2/usuarios/Hilder/Data/quipus_vs_proy.csv"

    # ETL cargas Tika (menú "Cargas Tika")
    TIKA_DEMANDA_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\demanda_27-28v4.csv"
    # Lo escribe quipus_vs_proy y lo lee planos_proyeccion_hoja1 (pasos 1 y 3
    # del flujo). Vive en el share, no en una carpeta local de un equipo: en
    # Docker una ruta "C:\..." no existe y los dos jobs fallan.
    QUIPUS_EXCEL_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\datos.xlsx"
    QUIPUS_FARM_MAP: dict[str, str] = {"INVERPALMAS": "001", "PALERMO": "002"}
    QUIPUS_FLOWER_MAP: dict[str, str] = {"CLAVEL": "CLA", "MINICLAVEL": "CM0"}
    QUIPUS_VS_PROY_SEMANAS_RECIENTES: int = 10
    # Destinatarios del correo de "cumplimiento_khipus_10_semanas.xlsx"
    # (job quipus_vs_proy, parametro enviar_email). Se completa desde Ajustes
    # > Quipus o en .env; si queda vacio el job no envia el correo aunque
    # SMTP este configurado.
    QUIPUS_CUMPLIMIENTO_EMAILS: list[str] = []

    # ETL comparar por picos vs demanda
    PICOS_TIKA_MODELO: int = 485
    PICOS_TALLOS_FACTOR: float = 0.9
    PICOS_DEMANDA_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\demanda_27-28v2.csv"
    PICOS_OUTPUT_PATH: str = r"\\172.10.18.2\produc\BASETDINAMICA\compara_pto_proy_real.csv"
    PICOS_OUTPUT_DIFERENCIAS_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\flor_color_diferencias.csv"
    PICOS_SEMANA_INICIO: int = 2527
    PICOS_SEMANA_FIN: int = 2620

    # ETL dirigidas analyzer
    DIRIGIDAS_ARREGLOS_PATH: str = r"//172.10.18.2/usuarios/Hilder/Data/tabla_arreglos.xlsx"
    DIRIGIDAS_DATE_MIN: str = "2026-02-01"
    DIRIGIDAS_MUESTRAS: int = 5
    DIRIGIDAS_TALLOS_MIN: int = 1000
    DIRIGIDAS_LONAS_SEMANA: int = 65
    DIRIGIDAS_OUTPUT_PATH: str = r"//172.10.18.2/usuarios/produccion/Sofia/dirigidas/datos/Para dirigida PC.xlsx"
    DIRIGIDAS_BLOQUE_OUTPUT_PATH: str = r"//172.10.18.2/usuarios/produccion/Sofia/dirigidas/datos/para dirigida por bloque.xlsx"
    DIRIGIDAS_RESUMEN_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\dirigidas_resumen.xlsx"
    DIRIGIDAS_FLOR_FILTER: list[str] = ["CLA", "CM0"]
    DIRIGIDAS_CAMAS_MIN: int = 4
    DIRIGIDAS_TALLOS_X2: int = 4000
    DIRIGIDAS_TALLOS_X3: int = 8000
    DIRIGIDAS_PLANTAS_POR_CAMA: int = 960
    DIRIGIDAS_TOLERANCIA_MATAS: float = 0.9
    DIRIGIDAS_EDAD_MIN: int = 30
    DIRIGIDAS_EDAD_PICO_INICIO: int = 40
    DIRIGIDAS_EDAD_PICO_FIN: int = 58
    # Bloques con arreglo (tipo AR) en ld_arre dentro de estos días no se escogen como muestra.
    DIRIGIDAS_EXCLUIR_ARREGLOS_DIAS: int = 42

    # ETL pedidos surtidos (genera ventas ultimo año.xlsx)
    PEDIDOS_SURTIDO_DBF_PATH: str = r"//172.10.18.2/newfact/DINAMICA/PEDIDOS_surtido.dbf"
    PEDIDOS_SURTIDO_FLOR_FILTER: list[str] = ["CLA", "CM0", "ROC", "ROS"]
    PEDIDOS_SURTIDO_PROYECCION_ANIO: int = 2026
    PEDIDOS_SURTIDO_VENTANA_SEMANAS: int = 52
    PEDIDOS_SURTIDO_FLOR_MAP: dict[str, str] = {"CLA": "CLAVEL", "CM0": "MINI"}
    PEDIDOS_SURTIDO_COLOR_REPLACEMENTS: dict[str, str] = {
        "LILAS": "LILA",
        "BICOLOR_PURPURA": "NOVEDAD",
        "BICOLOR_AMARILLO": "NOVEDAD",
        "BICOLOR_ROJO": "NOVEDAD",
        "NOVEDAD_BICOLOR": "NOVEDAD",
        "NOVEDADES": "NOVEDAD",
        "BICOLOR": "NOVEDAD",
        "AZUL": "BLANCO",
        "VERDE_TINTURADO": "BLANCO",
        "RAINBOW": "NOVEDAD",
        "SURTIDOS": "NOVEDAD",
        "NEGRO": "BLANCO",
        "RAINBOW TINTURADO": "NOVEDAD",
        "AMARILLO_NATURAL_CON": "AMARILLO",
        "ROSADO O HOT PINK": "ROSADO OSCURO",
        "NOVEDADES BICOLOR": "NOVEDAD",
        "ROSADO_OSCURO": "ROSADO OSCURO",
        "": "NOVEDAD",
        "RAINBOW_TINTURADO": "BLANCO",
    }

    # ETL comparativo Tika / produccion / despachos
    COMPARE_TIKA_DEFAULT_MODELS: list[int] = [161, 328, 485, 405]
    COMPARE_TIKA_TALLOS_FACTOR: float = 0.9
    COMPARE_TIKA_D_CUTOFF_DATE: str = "2026-01-05"
    COMPARE_TIKA_DESPACHOS_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\ventas ultimo año.xlsx"
    COMPARE_TIKA_DEMANDA_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\demanda_27-28v3.csv"
    COMPARE_TIKA_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\comparar producción.csv"
    COMPARE_TIKA_OUTPUT_EXCEL_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\comparar producción.xlsx"

    # Explicar brecha Real vs Demanda (cascada por escenarios Tika)
    EXPLICAR_BRECHA_TIKA_SEMANA_INICIO: int = 2620
    EXPLICAR_BRECHA_TIKA_SEMANA_FIN: int = 2639
    EXPLICAR_BRECHA_TIKA_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\explicar brecha tika.xlsx"

    # ETL comparativo de proyecciones Tika entre varios modelos/escenarios
    COMPARE_PROYECCIONES_TIKA_DEFAULT_MODELS: list[int] = [161, 328, 485, 405]
    COMPARE_PROYECCIONES_TIKA_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\Data\comparar proyecciones tika.csv"

    # ETL anomalias lonas
    ANOMALIAS_OUTPUT_DIR: str = r"\\172.10.18.2\Usuarios\Outputs"
    ANOMALIAS_SEMANA_INICIO: int = 2601
    ANOMALIAS_SEMANA_FIN: int = 2653

    # ETL tabla curvas clavel
    TABLA_CURVAS_CLAVEL_DBF_PATH: str = r"\\172.10.18.2\produc\basetdinamica\Curvas_por_Tiqueteado_EC.dbf"
    TABLA_CURVAS_CLAVEL_OUTPUT_CSV: str = r"\\172.10.18.2\Usuarios\Hilder\Data\tabla_curvas_clavel.csv"
    TABLA_CURVAS_CLAVEL_VARIEDAD_EXCLUIDA: str = "6522"
    CURVAS_PRODUCCION_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\bd_pipeline.xlsx"
    CURVAS_PRODUCCION_RESUMEN_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\resumen_variedades.csv"
    CURVAS_PRODUCCION_FILTRADA_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\curvas_filtradas_variedades.csv"
    DESVIACION_PRODUCCION_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\desviacion_produccion.csv"
    DESVIACION_PRODUCCION_UMBRAL_SEMANAS: float = 1.0
    CALIDADES_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\calidades_aporte.csv"
    CALIDADES_FUENTE_FILTER: list[str] = ["AjFito Cultivo DFFV", "Dirigida Finca-Flor-Variedad"]
    QUALITIES_PIPELINE_NAL_APORTE_MAX: float = 0.5
    APORTES_GRADOS_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\aportes_por_grado.csv"
    APORTES_GRADOS_FUENTE_FILTER: list[str] = [
        "Clasificacion",
        "Dirigida",
        "AjFito Cultivo",
        "Dirigida Finca-Flor-Variedad",
        "AjFito Cultivo DFFV",
    ]
    APORTES_GRADOS_FUENTE_MAP: dict[str, str] = {
        "Clasificacion": "procesado",
        "Dirigida": "solo dirigida",
        "AjFito Cultivo": "dirigida_cultivo",
        "Dirigida Finca-Flor-Variedad": "dirigida_pc",
        "AjFito Cultivo DFFV": "dirigida_pc",
    }
    APORTES_GRADOS_GRADO_EXCLUIDO: str = "CB"
    FUSARIUM_VARIETIES_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\fusarium_variedades.csv"
    PRODUCTIVIDADES_OUTPUT_PATH: str = r"\\172.10.18.2\Usuarios\Outputs\reporte de productividades.xlsx"

    # ETL cortes/lonas
    CORTES_LONAS_FLOR_FILTER: list[str] = ["CLA", "CM0"]
    CORTES_LONAS_FINCA_MAP: dict[str, str] = {"001": "INVERPALMAS", "002": "PALERMO"}

    # ETL informe jefes de area consolidado
    INFORMES_JEFES_AREA_INPUT_PATH: str = r"\\172.10.18.2\Usuarios\Hilder\INFORMES MES\DATOS\base_datos.xlsx"
    INFORMES_JEFES_AREA_OUTPUT_DIR: str = r"\\172.10.18.2\Usuarios\Hilder\INFORMES MES\DATOS"
    # Replica en Python el flujo de Power Query (tablas<año> -> datos_<año> -> hoja
    # 'base' de base_datos.xlsx) para que el reporte no dependa de que alguien
    # abra Excel y le de "Actualizar todo" antes de correr el job. La carpeta de
    # tablas del año en curso se actualiza cada enero; los datos_YYYY de años
    # cerrados quedan congelados (no cambian una vez cerrado el año).
    INFORMES_JEFES_AREA_TABLAS_DIR: str = r"\\172.10.18.2\Usuarios\Hilder\INFORMES MES\DATOS\tablas2026"
    # mes hasta el cual se acumulan las operaciones aritmeticas (ACM_mes_actual)
    # al mes en curso; se actualiza cada mes (ej. "AGOSTO" en agosto).
    INFORMES_JEFES_AREA_MES_ACUMULA: str = "AGOSTO"
    INFORMES_JEFES_AREA_ANIOS_CONGELADOS: list[str] = [
        r"\\172.10.18.2\Usuarios\Hilder\INFORMES MES\DATOS\datos_2023.xlsx",
        r"\\172.10.18.2\Usuarios\Hilder\INFORMES MES\DATOS\datos_2024_v2.xlsx",
        r"\\172.10.18.2\Usuarios\Hilder\INFORMES MES\DATOS\datos_2025.xlsx",
    ]
    # 'flor' combinada tal como se digita en las tablas de origen -> se reparte
    # entre las flores reales usando los porcentajes de la hoja 'distribuciones'.
    INFORMES_JEFES_AREA_FLORES_COMBINADAS: list[str] = ["CLA Y CM0", "CLA Y ROS", "ROC Y ROS"]
    INFORMES_JEFES_AREA_FLORES_DISTRIBUCION: list[str] = ["CLAVEL", "MINIATURA", "ROSAS COLORES", "ROSAS ROJAS"]
    # años que se excluyen del historico reconstruido (datos incompletos/piloto)
    INFORMES_JEFES_AREA_ANIOS_EXCLUIDOS: list[int] = [2019, 2020]

    # ETL balance de masas (informes mensuales)
    BALANCE_MASAS_EXPORTADO_PATH: str = r"\\172.10.18.2\produc\basetdinamica\exportado.dbf"
    # lonas<año>, pto<año>, pblo<año> y cre<año>.dbf
    BALANCE_MASAS_LD_BCULT_DIR: str = r"\\172.10.18.2\produc\ld_bcult"
    BALANCE_MASAS_OUTPUT_DIR: str = r"\\172.10.18.2\Usuarios\Hilder\Data"
    BALANCE_MASAS_YEAR_START: int = 2010
    BALANCE_MASAS_PTO_VS_REAL_YEAR_START: int = 2023
    # presupuesto exportable = presupuesto de produccion * factor por flor
    BALANCE_MASAS_PTO_EXPORTABLE_FACTORES: dict[str, float] = {"CLA": 0.92, "CM0": 0.95}
    BALANCE_MASAS_PTO_EXPORTABLE_FACTOR_DEFAULT: float = 0.90

    # Ejecucion ETL
    ETL_MAX_WORKERS: int = 3
    
    # Zona horaria
    TIMEZONE: str = "America/Bogota"  # UTC-5 (Colombia)
    
    # Directorios
    BASE_DIR: Path = Path(__file__).resolve().parents[2]
    STATIC_DIR: Path = BASE_DIR / "static"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        # El .env es compartido con docker-compose (credenciales de montaje
        # CIFS como SMB_USERNAME/PASSWORD que no son campos de Settings, solo
        # variables de entorno para scripts/entrypoint.sh): se ignoran en vez
        # de fallar al no encontrar un campo correspondiente.
        extra = "ignore"

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

    def apply_overrides(self, overrides: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
        if not isinstance(overrides, dict):
            raise ValueError("Las sobreescrituras deben ser un diccionario.")

        applied: dict[str, Any] = {}
        for key, value in overrides.items():
            if key not in type(self).model_fields:
                if strict:
                    raise ValueError(f"No existe la configuración '{key}' en la aplicación.")
                # override persistido de un campo que ya no existe (se
                # elimino de Settings en una version posterior): se ignora en
                # vez de tumbar el arranque de la app.
                continue
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


# Rutas que Settings deriva de la ubicacion del codigo, no configuracion de
# negocio. Nunca se toman de los overrides persistidos: ese archivo viaja a la
# imagen Docker, y un BASE_DIR/STATIC_DIR guardado desde Windows dejaba al
# contenedor Linux arrancando con "C:\Users\...\static" (que no existe alli).
DERIVED_PATH_SETTINGS: frozenset[str] = frozenset({"BASE_DIR", "STATIC_DIR"})


def _load_persistent_overrides() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / ".app_config_overrides.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key not in DERIVED_PATH_SETTINGS}


# Instancia global de configuración
settings = Settings()
settings.apply_overrides(_load_persistent_overrides(), strict=False)
