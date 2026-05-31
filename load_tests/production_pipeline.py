"""Pipeline principal para construir y suavizar curvas de producción de clavel.

Este script:
1. Lee la tabla base desde la ruta compartida.
2. Filtra registros válidos por edad y producción.
3. Calcula curvas base por finca, variedad, cosecha, edad y pico.
4. Suaviza cada curva preservando el total de FM.
5. Exporta el resultado detallado y un resumen por variedad.
"""

import numpy as np
import pandas as pd
import os
import warnings
from datetime import datetime
from functions import datos_curva, curve_ini, curve_values_by_age, rescale_to_total

warnings.filterwarnings("ignore")


# ======================================================
# FUNCIONES AUXILIARES
# ======================================================

def diagnostico(df, nombre):
    """Imprime un resumen corto del DataFrame para depuración."""
    print("\n" + "=" * 50)
    print(nombre)
    print("=" * 50)
    print("registros:", len(df))

    if df.empty:
        print("DATAFRAME VACÍO")
        return

    print(df.head(3))

    nulos = df.isnull().sum()
    nulos = nulos[nulos > 0]

    if len(nulos) > 0:
        print("\nNulos:")
        print(nulos)


def asignar_pico(edad):
    """Asigna el pico productivo según la edad de la curva."""
    if edad <= 35:
        return 1
    elif edad <= 70:
        return 2
    return np.nan


# ======================================================
# EXTRACCIÓN
# ======================================================

def get_data():
    """Lee y normaliza la fuente principal usada por el pipeline."""

    print("Leyendo datos...")

    ruta = "//172.10.18.2/usuarios/Hilder/Data/tabla_curvas_clavel.csv"

    if not os.path.exists(ruta):
        raise FileNotFoundError(ruta)

    columnas = [
        "finca",
        "bloque",
        "cosecha",
        "nvariedad",
        "cflor",
        "edad",
        "lunes",
        "matas",
        "corte"
    ]

    df = pd.read_csv(
        ruta,
        usecols=columnas,
        converters={
            "finca": str,
            "cosecha": str
        },
        na_values=["(en blanco)"]
    )

    df.rename(
        columns={"lunes": "fecha"},
        inplace=True
    )

    df["cosecha"] = df["cosecha"].fillna("")

    df = df.query("fecha >= '2024-12-30'")

    # usar muestra para pruebas rápidas
    # quitar comentario si quieres
    # df = df.sample(50000)

    diagnostico(df, "DATA ORIGINAL")

    return df


# ======================================================
# TRANSFORMACIÓN
# ======================================================

def procesar_picos_y_ceros(df_raw):
    """Construye la base filtrada sobre la que luego se aplica suavizado."""

    print("\nProcesando curvas base...")

    df = df_raw.copy()

    df["edad"] = df["edad"].astype(int)

    diagnostico(df, "ANTES FILTRO EDAD")

    df = df[df["edad"] <= 70]

    diagnostico(df, "DESPUÉS FILTRO EDAD <= 70")

    df["pico"] = df["edad"].apply(asignar_pico)

    print("\nDistribución pico:")
    print(df["pico"].value_counts())

    df["f_m"] = np.where(
        df["matas"] > 0,
        df["corte"] / df["matas"],
        np.nan
    )

    diagnostico(df, "DESPUÉS CALCULAR F_M")

    print("\nResumen f_m:")
    print(df["f_m"].describe())

    df.dropna(
        subset=["f_m"],
        inplace=True
    )

    final_dfs = []

    for pico in [1, 2]:

        print(f"\n--- PROCESANDO PICO {pico} ---")

        df_f = df[
            df["pico"] == pico
        ][[
            "finca",
            "bloque",
            "nvariedad",
            "cosecha",
            "f_m",
            "edad",
            "pico"
        ]]

        diagnostico(df_f, f"PICO {pico}")

        gr = (
            df_f.groupby(
                [
                    "finca",
                    "bloque",
                    "nvariedad",
                    "cosecha"
                ]
            )["f_m"]
            .sum()
            .reset_index()
        )

        diagnostico(gr, f"GROUP PICO {pico}")

        print("\nAplicando filtro f_m >= 3.5")
        gr = gr.query("f_m >= 3.5")

        diagnostico(gr, f"DESPUÉS FILTRO 3.5 PICO {pico}")

        if gr.empty:
            print("Este filtro eliminó todo.")
            continue

        filtrados = []

        for var in gr["nvariedad"].unique():

            temp = gr[
                gr["nvariedad"] == var
            ]

            print(f"\nVariedad {var}: {len(temp)}")

            if len(temp) < 5:
                print("menos de 5 -> pasa directo")
                filtrados.append(temp)
                continue

            q1 = temp["f_m"].quantile(0.15)
            q3 = temp["f_m"].quantile(0.85)

            print(f"q1={q1} q3={q3}")

            filtrados.append(
                temp[
                    (temp["f_m"] >= q1)
                    &
                    (temp["f_m"] <= q3)
                ]
            )

        if filtrados:

            filtro = pd.concat(filtrados)

            nuevo = pd.merge(
                df_f,
                filtro,
                on=[
                    "finca",
                    "bloque",
                    "nvariedad",
                    "cosecha"
                ],
                how="left"
            )

            nuevo.rename(
                columns={
                    "f_m_x": "f_m"
                },
                inplace=True
            )

            nuevo["filtro"] = np.where(
                nuevo["f_m_y"].isna(),
                0,
                1
            )

            final_dfs.append(nuevo)

    if not final_dfs:
        return pd.DataFrame()

    df_final = pd.concat(final_dfs)

    df_final = df_final.query(
        "filtro == 1"
    )

    diagnostico(df_final, "FINAL FILTRADO")

    df_final = (
        df_final.groupby(
            [
                "finca",
                "bloque",
                "nvariedad",
                "cosecha",
                "edad",
                "pico"
            ]
        )["f_m"]
        .mean()
        .reset_index()
    )

    diagnostico(df_final, "AGRUPADO FINAL")

    return df_final


# ======================================================
# SUAVIZADO
# ======================================================

def suavizar_curvas(df):
    """Suaviza las curvas por finca y variedad conservando el total de FM."""

    print("\nAplicando suavizado...")

    resultados = []

    grupos = df[
        ["finca", "nvariedad"]
    ].drop_duplicates()

    print("grupos:", len(grupos))

    for _, row in grupos.iterrows():

        finca = row["finca"]
        variedad = row["nvariedad"]

        temp = df[
            (df["finca"] == finca)
            &
            (df["nvariedad"] == variedad)
        ].copy()

        try:

            curva = np.array(
                curve_ini(temp)
            )

            _, ciclo, suavizada = datos_curva(curva)

            temp["fm_suave"] = rescale_to_total(
                curve_values_by_age(
                    temp,
                    suavizada
                ),
                temp["f_m"].sum()
            )
            temp["ciclo"] = ciclo + 18

            resultados.append(temp)

        except Exception as e:
            print(
                f"Error {finca}-{variedad}: {e}"
            )

    if not resultados:
        return pd.DataFrame()

    return pd.concat(
        resultados,
        ignore_index=True
    )


def resumir_variedades(df):
    """Resume la producción total FM por finca, variedad y pico."""
    return (
        df.groupby(
            ["finca", "nvariedad", "pico"],
            as_index=False,
        )["f_m"]
        .sum()
        .sort_values(["finca", "nvariedad", "pico"])
        .reset_index(drop=True)
    )


# ======================================================
# EXPORTAR
# ======================================================

def exportar(df):
    """Exporta el detalle del pipeline y el resumen agregado por variedad."""

    os.makedirs(
        "./files",
        exist_ok=True
    )

    salida = "./files/bd_pipeline.xlsx"
    salida_resumen = "./files/resumen_variedades.csv"
    resumen = resumir_variedades(df)

    try:
        df.to_excel(
            salida,
            index=False
        )
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        salida = f"./files/bd_pipeline_{timestamp}.xlsx"
        df.to_excel(
            salida,
            index=False
        )

    resumen.to_csv(
        salida_resumen,
        index=False,
        encoding="utf-8-sig"
    )

    print("\nArchivo exportado:")
    print(salida)
    print("Resumen exportado:")
    print(salida_resumen)


# ======================================================
# MAIN
# ======================================================

def main():
    """Ejecuta el pipeline completo de extracción, transformación y exportación."""

    print("=" * 50)
    print("PIPELINE CURVAS")
    print("=" * 50)

    df_raw = get_data()

    base = procesar_picos_y_ceros(df_raw)

    if base.empty:
        raise ValueError(
            "No se generó información base"
        )

    final = suavizar_curvas(base)

    if final.empty:
        raise ValueError(
            "No se generaron curvas"
        )

    exportar(final)

    print("\nProceso finalizado")


if __name__ == "__main__":
    main()