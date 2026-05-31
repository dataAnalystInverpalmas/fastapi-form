import pandas as pd
from pathlib import Path


def procesar_calidades(
    ruta=r"\\svrinverpalmas\Produc\basetdinamica\pprocesado.csv"
):

    print("=" * 50)
    print("PROCESANDO CALIDADES")
    print("=" * 50)

    # --------------------------------------------------
    # leer
    # --------------------------------------------------
    df_cal = pd.read_csv(
        ruta,
        dtype={"finca": str}
    )

    df_cal = df_cal.query(" grado != 'CB' ")

    print(f"Registros originales: {len(df_cal):,}")

    # --------------------------------------------------
    # agrupar
    # --------------------------------------------------
    df_cal = (
        df_cal.groupby(
            [
                "fecha",
                "finca",
                "bloque",
                "grado",
                "fuente",
                "nvari"
            ]
        )["tallos"]
        .sum()
        .reset_index()
    )

    # --------------------------------------------------
    # calcular aporte
    # --------------------------------------------------
    df_cal["aporte"] = (
        df_cal.groupby(
            ["fecha", "finca", "bloque", "nvari"]
        )["tallos"]
        .transform(lambda x: x / x.sum())
    )

    # --------------------------------------------------
    # filtrar NAL <= 50%
    # --------------------------------------------------
    df_nal = df_cal.query(
        "grado == 'NAL' and aporte <= 0.5"
    )[
        ["finca", "fecha", "bloque", "nvari"]
    ]

    df_cal = pd.merge(
        df_cal,
        df_nal,
        on=["finca", "fecha", "bloque", "nvari"],
        how="inner"
    )

    print(f"Registros filtrados: {len(df_cal):,}")

    # --------------------------------------------------
    # resumen final correcto
    # --------------------------------------------------
    df_export = (
        df_cal.groupby(
            ["finca", "nvari", "grado"],
            as_index=False
        )["tallos"]
        .sum()
    )
    
    # recalcular aporte
    df_export["aporte"] = (
        df_export.groupby(
            ["finca", "nvari"]
        )["tallos"]
        .transform(lambda x: x / x.sum())
    )
    
    # opcional: dejar solo columnas finales
    df_export = df_export[
        ["finca", "nvari", "grado", "aporte"]
    ]

    print(f"Archivo exportado: {salida}")

    return df_export


if __name__ == "__main__":
    df = procesar_calidades()
    print(df.head())