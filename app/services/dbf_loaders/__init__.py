from __future__ import annotations

from app.services.dbf_loaders.load_causas_generator import load_maestra_causas
from app.services.dbf_loaders.load_colores_generator import load_maestra_colores
from app.services.dbf_loaders.load_cosechas_generator import load_maestra_cosechas
from app.services.dbf_loaders.load_fiestas_generator import load_maestra_fiestas
from app.services.dbf_loaders.load_fusarium_generator import load_maestra_fusarium
from app.services.dbf_loaders.load_lonas_generator import load_maestra_lonas
from app.services.dbf_loaders.load_plano_cultivo_fm_generator import load_plano_cultivo_fm
from app.services.dbf_loaders.load_tabla_descarta_curva_generator import load_tabla_descarta_curva
from app.services.dbf_loaders.load_tabla_metas_generator import load_tabla_metas
from app.services.dbf_loaders.load_tabla_nacional_generator import load_tabla_nacional
from app.services.dbf_loaders.load_variedades_generator import load_maestra_variedades

__all__ = [
    "load_maestra_colores",
    "load_maestra_fiestas",
    "load_maestra_cosechas",
    "load_maestra_causas",
    "load_maestra_variedades",
    "load_tabla_metas",
    "load_tabla_descarta_curva",
    "load_tabla_nacional",
    "load_maestra_lonas",
    "load_maestra_fusarium",
    "load_plano_cultivo_fm",
]
