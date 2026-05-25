from __future__ import annotations

from app.services.etl_jobs.bajas_exportado_generator import generate_bajas_exportado_reports
from app.services.etl_jobs.compare_tika_produccion_generator import generate_compare_tika_produccion_report
from app.services.etl_jobs.comparar_picos_demanda_generator import generate_comparar_picos_demanda_report
from app.services.etl_jobs.dirigidas_generator import generate_dirigidas_analyzer
from app.services.etl_jobs.excel_generator import generate_excel_file
from app.services.etl_jobs.produccion_picos_generator import generate_produccion_picos_report
from app.services.etl_jobs.producto_procesado_generator import generate_producto_procesado_csv
from app.services.etl_jobs.proyecciones_generator import generate_proyecciones_csv
from app.services.etl_jobs.anomalias_lonas_generator import generate_anomalias_lonas
from app.services.etl_jobs.pedidos_surtidos_generator import generate_pedidos_surtidos
from app.services.etl_jobs.quipus_vs_proy_generator import generate_quipus_vs_proy_artifacts
from app.services.etl_jobs.resumir_curvas_usadas_generator import generate_resumir_curvas_usadas
from app.services.etl_jobs.tabla_curvas_clavel_generator import generate_tabla_curvas_clavel
from app.services.etl_jobs.load_fusarium_generator import load_maestra_fusarium
from app.services.etl_jobs.process_guarde_generator import generate_process_guarde
from app.services.etl_jobs.process_siembras_generator import generate_process_siembras_report
from app.services.etl_jobs.siembras_teo_real_generator import generate_siembras_teo_real

__all__ = [
    "generate_excel_file",
    "generate_bajas_exportado_reports",
    "generate_producto_procesado_csv",
    "generate_proyecciones_csv",
    "generate_produccion_picos_report",
    "generate_quipus_vs_proy_artifacts",
    "generate_compare_tika_produccion_report",
    "generate_comparar_picos_demanda_report",
    "generate_dirigidas_analyzer",
    "generate_anomalias_lonas",
    "generate_pedidos_surtidos",
    "generate_resumir_curvas_usadas",
    "generate_tabla_curvas_clavel",
    "load_maestra_fusarium",
    "generate_process_guarde",
    "generate_process_siembras_report",
    "generate_siembras_teo_real",
]
