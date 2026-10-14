from __future__ import annotations

from app.core.settings import settings
from app.services.etl.helpers import default_previous_year_week_range
from app.services.dbf_loaders import (
    load_maestra_arre,
    load_maestra_causas,
    load_maestra_colores,
    load_maestra_cosechas,
    load_maestra_fiestas,
    load_maestra_lonas,
    load_plano_cultivo_fm,
    load_tabla_descarta_curva,
    load_tabla_metas,
    load_tabla_nacional,
    load_maestra_variedades,
)
from app.services.tika_loaders import load_tika_demanda
from app.services.etl.definition import ETLJobDefinition
from app.services.queries.cortes_lonas_query import generate_cortes_lonas
from app.services.etl_jobs import (
    generate_anomalias_lonas,
    generate_aportes_grados,
    generate_aportes_ponderados_problemas,
    generate_bajas_exportado_reports,
    generate_balance_masas,
    generate_compare_proyecciones_tika_report,
    generate_compare_tika_produccion_report,
    generate_comparar_picos_demanda_report,
    generate_desviacion_produccion,
    generate_dirigidas_analyzer,
    generate_excel_file,
    generate_fusarium_pipeline,
    load_maestra_fusarium,
    generate_pedidos_surtidos,
    generate_production_pipeline,
    generate_produccion_picos_report,
    generate_productivity_varieties_report,
    generate_producto_procesado_csv,
    generate_producto_procesado_historico_csv,
    generate_planos_proyeccion,
    generate_planos_proyeccion_hoja1,
    generate_process_guarde,
    generate_process_siembras_report,
    generate_proyectar_rosas_report,
    generate_siembras_teo_real,
    generate_informes_jefes_area,
    generate_proyecciones_csv,
    generate_qualities_pipeline,
    generate_quipus_vs_proy_artifacts,
    generate_resumir_curvas_usadas,
    generate_tabla_curvas_clavel,
)


def build_job_catalog() -> dict[str, ETLJobDefinition]:
    default_week_range = default_previous_year_week_range()
    jobs = [
        ETLJobDefinition(
            job_id="excel_labores",
            name="Generar Excel de Labores",
            description="Construye y exporta el reporte de labores en Excel.",
            allows_parallel=True,
            timeout_seconds=900,
            runner=generate_excel_file,
        ),
        ETLJobDefinition(
            job_id="bajas_exportado",
            name="Bajas vs Exportado",
            description="Genera bajas_por_mes.csv y bajas_desde_2010.csv desde exportado.dbf + docuYYYY.dbf.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_bajas_exportado_reports,
        ),
        ETLJobDefinition(
            job_id="producto_procesado_historico_csv",
            name="Producto Procesado Historico a CSV",
            description="Carga historicos pprocesado_2021..2025 y reemplaza ld_producto_procesado (sin exportar CSV).",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_producto_procesado_historico_csv,
            dependency_group="Producción",
            flow_group="02 - Fuentes y Base",
        ),
        ETLJobDefinition(
            job_id="producto_procesado_csv",
            name="Producto Procesado Incremental a CSV",
            description="Carga incremental desde pprocesado.dbf por fecha de corte, anexa en ld_producto_procesado y actualiza pprocesado.csv.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_producto_procesado_csv,
            supports_params=True,
            default_params={
                "fecha_inicio_incremental": settings.PPROCESADO_INCREMENTAL_START_DATE,
                "fecha_inicio_exportacion": settings.PPROCESADO_INCREMENTAL_START_DATE,
            },
            dependency_group="Producción",
            flow_group="02 - Fuentes y Base",
        ),
        ETLJobDefinition(
            job_id="proyecciones_csv",
            name="Proyecciones a CSV",
            description="Genera proyecciones.csv combinando Proyecciones*.dbf con presupuesto anual y catálogo de colores.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_proyecciones_csv,
            depends_on=["load_maestra_variedades", "load_maestra_colores"],
            dependency_group="Producción",
            flow_group="02 - Fuentes y Base",
            manual_before=[
                "Genera primero en el sistema de cultivo la consulta de proyecciones, para que los "
                "Proyecciones*.dbf que lee este job queden con la proyeccion recien cargada.",
            ],
            manual_after=[
                "Actualiza los Excel que correspondan con proyecciones.csv. Con esto cierra el ciclo semanal de "
                "proyecciones.",
            ],
        ),
        ETLJobDefinition(
            job_id="produccion_picos",
            name="Produccion por Picos",
            description="Genera un CSV semanal por finca, bloque, flor y cosecha a partir de proyecciones.csv para CLA y CM0.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_produccion_picos_report,
            depends_on=["proyecciones_csv"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
        ),
        ETLJobDefinition(
            job_id="proyectar_rosas",
            name="Proyección Rosas",
            description="Genera la proyección de rosas consultando la base de datos y no archivos CSV intermedios.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_proyectar_rosas_report,
            supports_params=True,
            default_params={"fecha_inicio": "2024-01-01", "fecha_fin": "2026-12-31"},
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
        ),
        ETLJobDefinition(
            job_id="quipus_vs_proy",
            name="Quipus vs Proyecciones",
            description=(
                "Genera quipus.csv, quipus_vs_proy.csv, datos.xlsx y tablas MySQL quipus_vs_proy / "
                "quipus_vs_proy_matas, y envia por correo el cumplimiento de las ultimas 10 semanas de "
                "Khipus. Lee la consulta semanal de Curvas Khipus descargada de Tika "
                "(tika-quipus<AASS>.csv); datos.xlsx es la fuente de la proyeccion que arma despues el "
                "paso 3 (Subir Proyeccion)."
            ),
            allows_parallel=True,
            timeout_seconds=2400,
            runner=generate_quipus_vs_proy_artifacts,
            supports_params=True,
            default_params={"enviar_email": True},
            depends_on=["proyecciones_csv"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
            manual_before=[
                "En Tika > Curvas Khipus genera la consulta del rango de semanas vigente (hoy 2601 a 2705) "
                "y descarga el CSV.",
                r"Guarda ese CSV en la carpeta QUIPUS_TIKA_DIR (\\172.10.18.2\Usuarios\Hilder\Data\tika\quipus) "
                "como tika-quipus<AASS>.csv. OJO con la convencion: los 4 ultimos caracteres del nombre son "
                "AASS = año y semana ISO actual (ej. tika-quipus2638.csv para la semana 38 de 2026). Si el "
                "archivo ya existe, reemplazalo.",
            ],
            manual_after=[
                "Del correo de cumplimiento de las ultimas 10 semanas de Khipus, sube el archivo al sistema "
                "de cultivo por la opcion 'Cumplimiento de proyecciones'.",
                "Actualiza el Excel para proyectar: genera el plano de siembra resumido desde el sistema de "
                "cultivo y actualiza las columnas. Cuando los agronomos entreguen la proyeccion hecha, usa el "
                "boton del Excel que envia los ajustes de proyeccion a la API; despues sigue con el paso 2.",
            ],
        ),
        ETLJobDefinition(
            job_id="pedidos_surtidos",
            name="Pedidos Surtidos (Despachos)",
            description="Lee PEDIDOS_surtido.dbf, procesa despachos y genera ventas ultimo año.xlsx usado por 'Comparar Tika Produccion Despachos'.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_pedidos_surtidos,
            supports_params=True,
            default_params={"proyeccion_anio": 2026},
            dependency_group="Planeación",
            flow_group="03 - Derivados Semanales",
        ),
        ETLJobDefinition(
            job_id="compare_tika_produccion_despachos",
            name="Comparar Tika Produccion Despachos",
            description="Genera comparar producción.csv y Excel consolidando Tika, quipus, demanda, despachos y proyecciones.",
            allows_parallel=True,
            timeout_seconds=2400,
            runner=generate_compare_tika_produccion_report,
            supports_params=True,
            default_params={"modelos_tika": [161, 328, 485, 405]},
            depends_on=["proyecciones_csv", "quipus_vs_proy", "pedidos_surtidos"],
            dependency_group="Planeación",
            flow_group="04 - Analitica",
        ),
        ETLJobDefinition(
            job_id="compare_proyecciones_tika",
            name="Comparar Proyecciones Tika (Escenarios)",
            description="Compara varios modelos/escenarios Tika entre si en un CSV con campo fuente: proyecciones (proy1/2/3), siembras (esquejes_futuros), rotaciones (salvamento) y guardes (guarde). Tambien lo guarda en la tabla tika_compara_escenarios. Sin cruzar con despachos/demanda/quipus.",
            allows_parallel=True,
            timeout_seconds=1200,
            runner=generate_compare_proyecciones_tika_report,
            supports_params=True,
            default_params={"modelos_tika": [161, 328, 485, 405]},
            dependency_group="Planeación",
            flow_group="04 - Analitica",
        ),
        ETLJobDefinition(
            job_id="comparar_picos_demanda",
            name="Comparar Picos vs Demanda",
            description="Genera compara_pto_proy_real.csv y flor_color_diferencias.csv consolidando proyecciones, quipus, Tika y demanda por pico/bloque.",
            allows_parallel=True,
            timeout_seconds=2400,
            runner=generate_comparar_picos_demanda_report,
            supports_params=True,
            default_params={"modelo_tika": 485},
            depends_on=["proyecciones_csv", "quipus_vs_proy"],
            dependency_group="Planeación",
            flow_group="04 - Analitica",
        ),
        ETLJobDefinition(
            job_id="dirigidas_analyzer",
            name="Analizador de Dirigidas",
            description="Genera análisis de dirigidas desde proyecciones, plano y tabla de arreglos. Distribuye muestras por día de la semana.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_dirigidas_analyzer,
            supports_params=True,
            default_params={"muestras": 5, "tallos_min": 1000, "lonas_semana": 65},
            depends_on=["proyecciones_csv", "load_plano_cultivo_fm", "load_tabla_nacional"],
            flow_group="04 - Analitica",
        ),
        ETLJobDefinition(
            job_id="anomalias_lonas",
            name="Anomalías en Lonas (Regla Física)",
            description=(
                "Detecta anomalías en ld_lonas usando una regla física simple: tallos > plantas/2. "
                "Filtra por rango YYWW, rellena fechas faltantes por grupo y marca huecos como sin_dato. "
                "Marca plantas nulas o en 0 (con tallos > 0) como plantas_invalidas. "
                "Genera anomalias_detectadas.csv con todos los registros del rango y "
                "correcciones_lonas.xlsx con el valor sugerido para corregir plantas_invalidas "
                "(plantas de la misma finca/bloque/variedad/semana de siembra) y tallos > plantas/2."
            ),
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_anomalias_lonas,
            supports_params=True,
            default_params={
                "semana_inicio": settings.ANOMALIAS_SEMANA_INICIO,
                "semana_fin": settings.ANOMALIAS_SEMANA_FIN,
            },
        ),
        ETLJobDefinition(
            job_id="tabla_curvas_clavel",
            name="Tabla Curvas Clavel",
            description="Carga Curvas_por_Tiqueteado_EC.dbf a la tabla ld_curvas_clavel y exporta CSV. Limpia fechas y filtra variedades.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_tabla_curvas_clavel,
            flow_group="02 - Fuentes y Base",
        ),
        ETLJobDefinition(
            job_id="production_pipeline_curvas",
            name="Pipeline de Curvas de Produccion",
            description="Lee tabla_curvas_clavel.csv, excluye las curvas registradas en ld_descarta_curva (finca/bloque/nvariedad/cosecha), filtra y suaviza las curvas restantes, y exporta el detalle, resumen y la salida filtrada a Outputs.",
            allows_parallel=True,
            timeout_seconds=2400,
            runner=generate_production_pipeline,
            supports_params=True,
            default_params={
                **dict(default_week_range),
                "sem_valle": 8,
                "peak_window_weeks": 4,
                "smooth_window_length": 7,
                "smooth_polyorder": 2,
                "force_valley_weeks_after_peak": 8,
            },
            depends_on=["tabla_curvas_clavel"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="desviacion_produccion",
            name="Desviacion de Produccion (Adelantada/Atrasada)",
            description=(
                "Compara el f_m acumulado real de cada bloque/cosecha activo contra su curva de referencia "
                "historica (finca/nvariedad/ciclo) generada por production_pipeline_curvas, y estima si va "
                "adelantada o atrasada en semanas equivalentes de curva. Exporta CSV y tabla MySQL desviacion_produccion."
            ),
            allows_parallel=True,
            timeout_seconds=1200,
            runner=generate_desviacion_produccion,
            supports_params=True,
            default_params={"umbral_semanas": settings.DESVIACION_PRODUCCION_UMBRAL_SEMANAS},
            depends_on=["production_pipeline_curvas"],
            dependency_group="Producción",
            flow_group="04 - Analitica",
        ),
        ETLJobDefinition(
            job_id="qualities_pipeline",
            name="Pipeline de Calidades",
            description="Lee pprocesado.csv y exporta el resumen de aportes por calidad a CSV en Outputs.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_qualities_pipeline,
            supports_params=True,
            default_params=dict(default_week_range),
            depends_on=["producto_procesado_csv"],
            dependency_group="Analítica",
            flow_group="03 - Derivados Semanales",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="fusarium_pipeline",
            name="Pipeline de Fusarium por Variedad",
            description="Consulta ld_fusarium, calcula el promedio por finca, variedad y ciclo dentro del rango de fechas y exporta un CSV en Outputs.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_fusarium_pipeline,
            supports_params=True,
            default_params=dict(default_week_range),
            depends_on=["load_maestra_fusarium"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="aportes_ponderados_problemas",
            name="Causas Nacional Dirigida + Fito",
            description="Calcula aportes ponderados por problema (fito cultivo + dirigida) y exporta un CSV en Outputs para un rango de fechas.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_aportes_ponderados_problemas,
            supports_params=True,
            default_params=dict(default_week_range),
            flow_group="04 - Analitica",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="productivity_varieties_report",
            name="Reporte de Productividad de Variedades",
            description="Regenera production_pipeline_curvas, qualities_pipeline y fusarium_pipeline por rango de fechas, y luego genera el Excel de productividades por variedad en Outputs.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_productivity_varieties_report,
            supports_params=True,
            default_params=dict(default_week_range),
            dependency_note="Este job autoprepara production_pipeline_curvas, qualities_pipeline y fusarium_pipeline antes de exportar.",
            dependency_group="Analítica",
            flow_group="04 - Analitica",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="exporta_cortes_lonas",
            name="Exportar Cortes de Lonas",
            description="Genera un Excel con cortes de ld_lonas agrupados por variedad/finca/bloque y semana en un rango de fechas.",
            allows_parallel=True,
            timeout_seconds=900,
            runner=generate_cortes_lonas,
            supports_params=True,
            default_params=dict(default_week_range),
            dependency_group="Analítica",
            flow_group="04 - Analitica",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="resumir_curvas_usadas",
            name="Resumir Curvas Usadas",
            description=(
                "Consolida curvas Tika por programa/variedad y exporta resumen_curvas (MySQL + curvas_resumen.csv); "
                "ademas construye curvas_resumen_todas.csv cruzando ld_curvas_clavel con ld_descarta_curva y ld_metas. "
                "Parametro final_filter_value: 0 exporta todo, 1 exporta filtradas y seleccionadas, 2 solo seleccionadas."
            ),
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_resumir_curvas_usadas,
            supports_params=True,
            default_params={
                "curve_paths": [
                    "//172.10.18.2/usuarios/Hilder/Data/tika-curvas2025.csv",
                    "//172.10.18.2/usuarios/Hilder/Data/tika-curvas2026v2.csv",
                ],
                "curve_years": [2025, 2026],
                "final_filter_value": 2,
            },
        ),
        ETLJobDefinition(
            job_id="load_maestra_colores",
            name="Load Maestra Colores",
            description="Carga ld_mgcol.dbf directo a MySQL en la tabla ld_colores.",
            allows_parallel=False,
            timeout_seconds=600,
            runner=load_maestra_colores,
        ),
        ETLJobDefinition(
            job_id="load_maestra_fiestas",
            name="Load Maestra Fiestas",
            description="Carga ld_mfies.dbf a MySQL en la tabla ld_fiestas, descartando registros sin observación y ordenando por mes.",
            allows_parallel=False,
            timeout_seconds=600,
            runner=load_maestra_fiestas,
        ),
        ETLJobDefinition(
            job_id="load_maestra_cosechas",
            name="Load Maestra Cosechas",
            description="Carga ld_mcose.dbf directo a MySQL en la tabla ld_cosechas.",
            allows_parallel=False,
            timeout_seconds=600,
            runner=load_maestra_cosechas,
        ),
        ETLJobDefinition(
            job_id="load_maestra_causas",
            name="Load Maestra Causas",
            description="Carga ld_mcaus.dbf directo a MySQL en la tabla ld_causas filtrando registros inactivos.",
            allows_parallel=False,
            timeout_seconds=600,
            runner=load_maestra_causas,
        ),
        ETLJobDefinition(
            job_id="load_maestra_variedades",
            name="Load Maestra Variedades",
            description="Carga ld_mvari.dbf directo a MySQL en la tabla ld_variedades con filtros de activo y flor.",
            allows_parallel=False,
            timeout_seconds=900,
            runner=load_maestra_variedades,
        ),
        ETLJobDefinition(
            job_id="load_tabla_metas",
            name="Load Tabla Metas",
            description="Carga hijos2026.dbf y enriquece variedades para insertar en ld_metas (modo append).",
            allows_parallel=False,
            timeout_seconds=900,
            runner=load_tabla_metas,
        ),
        ETLJobDefinition(
            job_id="load_tabla_descarta_curva",
            name="Load Tabla Descarta Curva",
            description="Carga descarta_curva.dbf y enriquece variedades para reemplazar ld_descarta_curva.",
            allows_parallel=False,
            timeout_seconds=900,
            runner=load_tabla_descarta_curva,
        ),
        ETLJobDefinition(
            job_id="load_tabla_nacional",
            name="Load Tabla Nacional",
            description="Carga una lista parametrizable de rflo*.dbf, cruza variedades y causas, y reemplaza la tabla ld_nacional.",
            allows_parallel=False,
            timeout_seconds=1200,
            runner=load_tabla_nacional,
            supports_params=True,
            default_params={"rflo_tables": settings.LOAD_RFLO_NACIONAL_TABLES},
        ),
        ETLJobDefinition(
            job_id="load_maestra_lonas",
            name="Load Maestra Lonas",
            description=(
                "Carga lonasYYYY.dbf, enriquece variedad desde ld_mvari y recarga en ld_lonas solo los "
                "ultimos LOAD_LONAS_ANIOS_RECARGA anios (los anteriores se conservan)."
            ),
            allows_parallel=False,
            timeout_seconds=1200,
            runner=load_maestra_lonas,
        ),
        ETLJobDefinition(
            job_id="load_maestra_arre",
            name="Load Maestra ARRE",
            description="Carga arreYYYY.dbf desde 2020 a 2026, excluye tipo MA y reemplaza la tabla ld_arre.",
            allows_parallel=False,
            timeout_seconds=1200,
            runner=load_maestra_arre,
        ),
        ETLJobDefinition(
            job_id="load_maestra_fusarium",
            name="Load Maestra Fusarium",
            description="Carga historico_fusarium.dbf, marca ultimo por grupo y reemplaza la tabla ld_fusarium.",
            allows_parallel=False,
            timeout_seconds=1200,
            runner=load_maestra_fusarium,
        ),
        ETLJobDefinition(
            job_id="load_plano_cultivo_fm",
            name="Load Plano Cultivo FM",
            description="Carga plano_de_siembra_resumido.dbf, genera ld_plano_cultivo_fm y actualiza plane.FM_pico_actual y plane.gh_id.",
            allows_parallel=False,
            timeout_seconds=1200,
            runner=load_plano_cultivo_fm,
        ),
        ETLJobDefinition(
            job_id="load_process_guarde",
            name="Procesar Guarde",
            description="Convierte un archivo tabular de cortes/guarde a Excel normalizando fecha, semana y variedad.",
            allows_parallel=True,
            timeout_seconds=1200,
            runner=generate_process_guarde,
            supports_params=True,
            default_params={"input_path": "", "output_path": settings.PROCESS_GUARDE_OUTPUT_PATH},
        ),
        ETLJobDefinition(
            job_id="load_process_siembras",
            name="Procesar Siembras",
            description="Genera el Excel de plano nuevo de siembra consultando plane cruzado con dates (fecha_siembra); calcula ciclos, y mapea cascarilla y tipo de goteo.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_process_siembras_report,
            dependency_group="Siembras",
        ),
        ETLJobDefinition(
            job_id="aportes_grados_pipeline",
            name="Pipeline de Aportes por Grado",
            description="Consulta ld_producto_procesado por fuente (procesado, dirigida_cultivo, dirigida_pc), cruza con la tabla dates para obtener aass y calcula el aporte porcentual de cada grado. Exporta CSV en Outputs.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_aportes_grados,
            supports_params=True,
            default_params=dict(default_week_range),
            depends_on=["producto_procesado_csv"],
            dependency_group="Analítica",
            flow_group="03 - Derivados Semanales",
            weekly_dates=True,
        ),
        ETLJobDefinition(
            job_id="load_siembras_teo_real",
            name="Siembras Teo vs Real",
            description="Consolida siembras teóricas y reales, cruza colores/fechas y exporta el comparativo a Excel.",
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_siembras_teo_real,
            dependency_group="Siembras",
        ),
        ETLJobDefinition(
            job_id="informes_jefes_area",
            name="Informe Jefes de Area Consolidado",
            description="Genera el libro con 6 hojas (Informes Consolidado, Palmas, Palermo, Propagacion, PC y Consolidado por flor). Reconstruye 'base' en vivo desde tablas<año>/*.xlsx + los datos_YYYY.xlsx de años cerrados (sin depender de refrescar Power Query); 'orden'/'distribuciones' se leen de base_datos.xlsx.",
            allows_parallel=True,
            timeout_seconds=1200,
            runner=generate_informes_jefes_area,
            supports_params=True,
            default_params={
                "file": settings.INFORMES_JEFES_AREA_INPUT_PATH,
                "out_dir": settings.INFORMES_JEFES_AREA_OUTPUT_DIR,
                "tablas_dir": settings.INFORMES_JEFES_AREA_TABLAS_DIR,
                "use_live_source": True,
                "mes_acumula": settings.INFORMES_JEFES_AREA_MES_ACUMULA,
            },
            dependency_group="Informes Mensuales",
        ),
        ETLJobDefinition(
            job_id="balance_masas",
            name="Balance de masas",
            description=(
                "Cruza exportado.dbf con lonas, presupuesto (pto), plantas (pblo) y areas (cre) de ld_bcult; "
                "reparte el exportado entre fincas segun el aporte de lonas y genera 'Producción Vs "
                "Despachado.xlsx', 'Datos de exportado.xlsx' (flor/mata y flor/m2 por finca, con finca 000), "
                "'Base balance de masas.xlsx' y datos_realxJI_pto.csv (real vs presupuesto)."
            ),
            allows_parallel=True,
            timeout_seconds=1800,
            runner=generate_balance_masas,
            supports_params=True,
            default_params={
                "anio_inicio": settings.BALANCE_MASAS_YEAR_START,
                "anio_pto_vs_real": settings.BALANCE_MASAS_PTO_VS_REAL_YEAR_START,
                "out_dir": settings.BALANCE_MASAS_OUTPUT_DIR,
            },
            dependency_group="Informes Mensuales",
        ),
        ETLJobDefinition(
            job_id="planos_proyeccion",
            name="Plano de Proyeccion (Sistemas Palermo + Palmas)",
            description=(
                "Lee stg_plano_proyeccion (subida por macro de Excel desde Palermo y Palmas via la API PHP) "
                "para ambas fincas, cruza con Lotes_de_siembra.csv para traer id_lote_siembra y exporta "
                "planos_proyeccion.csv (solo filas cruzadas). Genera ajustes_proyeccion.xlsx en Outputs con "
                "las filas cuyo Factor sea distinto de 1 o Mueve semanas distinto de 0 (columnas ID/Factor/"
                "Mueve semanas/Vigencia/Bloqueado) mas un Excel por finca (Palermo/Palmas), y envia un "
                "correo con los ajustes por finca para cargar a Tika."
            ),
            allows_parallel=True,
            timeout_seconds=600,
            runner=generate_planos_proyeccion,
            dependency_group="Producción",
            flow_group="02 - Fuentes y Base",
            manual_before=[
                "Los agronomos ya deben haber entregado la proyeccion y el Excel para proyectar ya debe haber "
                "enviado los ajustes de proyeccion a la API (boton del Excel): este job lee esa ultima subida.",
            ],
            manual_after=[
                "Del correo 'para Subir a Tika - Ajuste de proyección', importa en Tika > Khipus > Cumplimiento "
                "de proyecciones los archivos de las DOS fincas (Palermo y Palmas).",
                "Ya subidos los ajustes, vuelve a Tika > Curvas Khipus, genera otra vez la consulta del mismo "
                "rango de semanas (hoy 2601 a 2705) y REEMPLAZA tika-quipus<AASS>.csv en la carpeta de Khipus "
                "(misma convencion AASS del paso 1).",
                "Vuelve a ejecutar el paso 1 (Quipus vs Proyecciones) para que datos.xlsx quede con la consulta "
                "recien reemplazada (esta segunda corrida no reenvia el correo de cumplimiento: sale una "
                "sola vez por semana); solo despues corre el paso 3.",
            ],
        ),
        ETLJobDefinition(
            job_id="planos_proyeccion_hoja1",
            name="Subir Proyeccion (sistema de cultivo)",
            description=(
                "Genera Subir_Proyeccion.xlsx en Outputs a partir de la plantilla "
                "Subir_datos_de_proyecciones.xlsx, con sus dos hojas llenas y listas para subir al sistema de "
                "cultivo, y la envia por correo. La hoja de proyeccion (tipo/año/semana/finca/flor/bloque/cosecha/"
                "variedad/tallos) sale de la hoja 'datos' de datos.xlsx (job quipus_vs_proy), solo desde la "
                "semana siguiente a la actual: tipo es parametro (AJUSTE por defecto, o INICIAL), tallos es quipus-proyección y variedad el codigo de ld_variedades. La hoja de ajustes lleva las filas "
                "con Factor distinto de 1 o Mueve semanas distinto de 0 de planos_proyeccion.csv (job "
                "planos_proyeccion)."
            ),
            allows_parallel=True,
            timeout_seconds=600,
            runner=generate_planos_proyeccion_hoja1,
            supports_params=True,
            default_params={"tipo": "AJUSTE"},
            depends_on=["quipus_vs_proy", "planos_proyeccion"],
            dependency_group="Producción",
            flow_group="03 - Derivados Semanales",
            manual_before=[
                "CONFIRMA el parametro Tipo antes de generar: AJUSTE (por defecto) o INICIAL. Es el tipo con el "
                "que se cargara la proyeccion al sistema de cultivo y el que hay que borrar alli antes de subir.",
                "Verifica que tika-quipus<AASS>.csv ya fue reemplazado despues de subir los ajustes a Tika y que "
                "el paso 1 se volvio a ejecutar con ese archivo: la hoja de proyeccion sale de datos.xlsx.",
            ],
            manual_after=[
                "ANTES DE SUBIR: en el sistema de cultivo borra la proyeccion existente por tipo (el mismo "
                "AJUSTE/INICIAL que elegiste) y por flor, tanto CLA como CM0. Solo entonces carga "
                "Subir_Proyeccion.xlsx.",
                "El archivo trae la proyeccion desde la semana siguiente a la actual; el correo indica la primera "
                "semana incluida, revisala antes de cargar.",
                "Ya cargado, genera en el sistema de cultivo la consulta de proyecciones y sigue con el paso 4.",
            ],
        ),
        ETLJobDefinition(
            job_id="tika_demanda",
            name="Load Demanda Tika",
            description="Carga el CSV de demanda entregado por Tika (demanda_27-28v4.csv) a la tabla tika_demanda.",
            allows_parallel=False,
            timeout_seconds=600,
            runner=load_tika_demanda,
            dependency_group="Tika",
        ),
    ]
    return {job.job_id: job for job in jobs}
