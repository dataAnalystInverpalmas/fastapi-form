from __future__ import annotations

import pandas as pd

from app.core.settings import settings
from app.services.etl.helpers import dataframe_to_sql, execute_query, read_dbf, validate_columns


def load_plano_cultivo_fm() -> str:
    df = read_dbf(settings.LOAD_PLANO_SIEMBRA_RESUMIDO_PATH)
    if df.empty:
        raise RuntimeError("El archivo plano_de_siembra_resumido.dbf no contiene datos.")

    validate_columns(
        df,
        {"nfinca", "bloque", "nvari", "cosecha", "fm_p_act"},
        "plano_de_siembra_resumido.dbf",
    )

    df_export = (
        df.groupby(["nfinca", "bloque", "nvari", "cosecha"], dropna=False)["fm_p_act"]
        .max()
        .reset_index()
        .rename(columns={"nfinca": "finca"})
    )

    df_export["finca"] = df_export["finca"].astype(str).str.strip()
    df_export["nvari"] = df_export["nvari"].astype(str).str.strip()
    df_export["cosecha"] = df_export["cosecha"].astype(str).str.strip()
    df_export["bloque"] = pd.to_numeric(df_export["bloque"], errors="coerce").astype("Int64")
    df_export["fm_p_act"] = pd.to_numeric(df_export["fm_p_act"], errors="coerce")

    dataframe_to_sql(df_export, "ld_plano_cultivo_fm", if_exists="replace")

    update_fm_pico_actual = """
        UPDATE plane p
        JOIN ld_plano_cultivo_fm f
          ON p.finca = f.finca
         AND p.bloque = f.bloque
         AND p.variedad = f.nvari
         AND p.pico = f.cosecha
        SET p.FM_pico_actual = f.fm_p_act
    """
    execute_query(update_fm_pico_actual)

    update_gh_id = """
        UPDATE plane AS p
        JOIN greenhouses AS g
          ON p.bloque = g.bloque
         AND p.tabla = g.tabla
         AND p.nave = g.nave
         AND p.cama = g.cama
        JOIN farms AS f
          ON f.id = g.finca_id
         AND f.nombre = p.finca
        SET p.gh_id = g.id
    """
    execute_query(update_gh_id)

    return "mysql:informes.ld_plano_cultivo_fm"
