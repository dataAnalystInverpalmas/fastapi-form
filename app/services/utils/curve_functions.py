"""
Funciones de curva de producción usadas en producción.

Extraídas de load_tests/functions.py para eliminar la dependencia de producción
en el directorio de desarrollo/notebooks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

# Curva de referencia de producción (86 semanas desde EDAD_INI)
arr = [
    0, 0, 0, 0.01, 0.04, 0.1, 0.25, 0.48, 0.65, 0.82, 0.83, 0.75, 0.59, 0.43,
    0.3, 0.18, 0.12, 0.1, 0.06, 0.04, 0.03, 0.02, 0.01, 0, 0, 0, 0, 0, 0.01,
    0.02, 0.05, 0.07, 0.12, 0.17, 0.24, 0.3, 0.37, 0.43, 0.46, 0.48, 0.49,
    0.46, 0.45, 0.44, 0.37, 0.31, 0.31, 0.23, 0.18, 0.11, 0.08, 0.06, 0.07,
    0.05, 0.04, 0.09, 0.08, 0.1, 0.09, 0.07, 0.11, 0.09, 0.07, 0.1, 0.11,
    0.14, 0.13, 0.21, 0.24, 0.25, 0.3, 0.3, 0.27, 0.31, 0.36, 0.3, 0.3, 0.33,
    0.24, 0.18, 0.19, 0.15, 0.17, 0.12, 0.13,
]

EDAD_INI = 18
SEM_VALLE = 8
PEAK_WINDOW_WEEKS = 4
SMOOTH_WINDOW_LENGTH = 7
SMOOTH_POLYORDER = 2


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

def _resolve_curve_column(df_group: pd.DataFrame) -> str | None:
    return next(
        (col for col in ["fm_aj", "f_m"] if col in df_group.columns),
        None,
    )


def _smooth_segment_once(
    segment: np.ndarray,
    window_length: int = SMOOTH_WINDOW_LENGTH,
    polyorder: int = SMOOTH_POLYORDER,
) -> np.ndarray:
    segment = np.asarray(segment, dtype=float)
    if len(segment) < 3:
        return segment.copy()
    window_length = max(3, int(window_length))
    window_length = min(window_length, len(segment))
    if window_length % 2 == 0:
        window_length -= 1
    if window_length < 3:
        return segment.copy()
    polyorder = max(0, min(int(polyorder), window_length - 1))
    return savgol_filter(segment, window_length, polyorder)


def _peak_window_end_index(values: np.ndarray, window_size: int = PEAK_WINDOW_WEEKS) -> int:
    values = np.asarray(values, dtype=float)
    window_size = max(1, int(window_size))
    if len(values) == 0:
        return 0
    best_sum = float("-inf")
    best_end = min(len(values), window_size) - 1
    for index in range(len(values)):
        current_sum = float(np.sum(values[index : index + window_size]))
        current_end = min(index + window_size - 1, len(values) - 1)
        if current_sum > best_sum:
            best_sum = current_sum
            best_end = current_end
    return best_end


def _build_zero_mask(
    largo: int,
    ppi_zeros: int,
    ppf_izeros: int,
    ppf_fzeros: int,
    spf_izeros: int,
    spf_fzeros: int,
) -> np.ndarray:
    mask = np.zeros(largo, dtype=bool)
    for i in range(largo):
        if (
            (i < ppi_zeros)
            or (i > ppf_izeros and i <= ppf_fzeros)
            or (i >= spf_izeros and i <= spf_fzeros)
        ):
            mask[i] = True
    return mask


def _iter_active_segments(active_mask: np.ndarray):
    start = None
    for index, is_active in enumerate(active_mask):
        if is_active and start is None:
            start = index
        elif not is_active and start is not None:
            yield start, index
            start = None
    if start is not None:
        yield start, len(active_mask)


def _preserve_total(
    curva_original: np.ndarray,
    curva_suavizada: np.ndarray,
    active_mask: np.ndarray,
) -> np.ndarray:
    curva_original = np.asarray(curva_original, dtype=float)
    curva_suavizada = np.asarray(curva_suavizada, dtype=float)
    total_original = float(curva_original.sum())
    if total_original <= 0:
        curva_suavizada[:] = 0
        return curva_suavizada
    total_suavizada = float(curva_suavizada.sum())
    if total_suavizada <= 0:
        curva_suavizada = curva_original.copy()
        curva_suavizada[~active_mask] = 0
        total_suavizada = float(curva_suavizada.sum())
    if total_suavizada <= 0:
        return curva_suavizada
    curva_suavizada *= total_original / total_suavizada
    diferencia = total_original - float(curva_suavizada.sum())
    active_indexes = np.flatnonzero(active_mask)
    if len(active_indexes) > 0 and abs(diferencia) > 1e-12:
        target_index = active_indexes[np.argmax(curva_suavizada[active_indexes])]
        curva_suavizada[target_index] += diferencia
    return curva_suavizada


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def zeros(x: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(x, dtype=float), 0, None)


def rescale_to_total(values: np.ndarray, target_total: float) -> np.ndarray:
    """Reescala un array para que su suma sea exactamente target_total."""
    values = np.asarray(values, dtype=float).copy()
    target_total = float(target_total)
    if target_total <= 0:
        return np.zeros_like(values)
    current_total = float(values.sum())
    if current_total <= 0:
        return values
    values *= target_total / current_total
    difference = target_total - float(values.sum())
    if len(values) > 0 and abs(difference) > 1e-12:
        values[np.argmax(values)] += difference
    return values


def curve_values_by_age(df_group: pd.DataFrame, curve_values: np.ndarray) -> np.ndarray:
    """Mapea los valores de curva a las edades presentes en df_group."""
    edades = np.arange(EDAD_INI, EDAD_INI + len(curve_values))
    curve_map = pd.Series(np.asarray(curve_values, dtype=float), index=edades)
    return df_group["edad"].astype(int).map(curve_map).fillna(0.0).to_numpy()


def curve_ini(df_group: pd.DataFrame) -> list[float]:
    """Retorna los valores promedio de la curva de producción por edad."""
    edades = np.arange(EDAD_INI, 70)
    value_column = _resolve_curve_column(df_group)
    if value_column is None:
        raise KeyError("curve_ini requiere una columna 'fm_aj' o 'f_m'")
    valores_por_edad = df_group.groupby("edad")[value_column].mean().to_dict()
    return [float(valores_por_edad.get(edad, 0)) for edad in edades]


def datos_curva(
    curva: np.ndarray,
    *,
    sem_valle: int = SEM_VALLE,
    peak_window_weeks: int = PEAK_WINDOW_WEEKS,
    smooth_window_length: int = SMOOTH_WINDOW_LENGTH,
    smooth_polyorder: int = SMOOTH_POLYORDER,
) -> tuple[np.ndarray, int, np.ndarray]:
    """Suaviza una curva una sola vez y conserva el total original.

    Returns:
        (curva_original, indice_pico, curva_suavizada)
    """
    dic = {
        23: [-4, 6, 8], 24: [-4, 6, 8], 25: [-3, 6, 8], 26: [-2, 7, 8],
        27: [-1, 7, 8], 28: [0, 7, 7], 29: [1, 8, 6], 30: [2, 8, 6],
        31: [3, 8, 6], 32: [4, 8, 6],
    }
    curva = np.asarray(curva, dtype=float)
    largo = len(curva)
    if largo == 0:
        return curva.copy(), 0, curva.copy()

    sem_valle = max(0, int(sem_valle))
    peak_window_weeks = max(1, int(peak_window_weeks))
    smooth_window_length = max(3, int(smooth_window_length))
    smooth_polyorder = max(0, int(smooth_polyorder))

    i_final = _peak_window_end_index(curva, window_size=peak_window_weeks)
    ciclo_key = i_final + EDAD_INI
    ciclo_data = dic.get(ciclo_key)
    if ciclo_data is None:
        nearest_key = min(dic, key=lambda k: abs(k - ciclo_key))
        ciclo_data = dic[nearest_key]

    ppi_zeros = i_final - ciclo_data[1]
    ppf_izeros = i_final + ciclo_data[2]
    ppf_fzeros = i_final + 8 + sem_valle
    spf_izeros = (ppf_izeros * 2) + EDAD_INI + ciclo_data[0]
    spf_fzeros = spf_izeros + sem_valle

    zero_mask = _build_zero_mask(largo, ppi_zeros, ppf_izeros, ppf_fzeros, spf_izeros, spf_fzeros)
    active_mask = ~zero_mask

    suavizada = curva.copy()
    suavizada[zero_mask] = 0
    for start, end in _iter_active_segments(active_mask):
        suavizada[start:end] = _smooth_segment_once(
            curva[start:end],
            window_length=smooth_window_length,
            polyorder=smooth_polyorder,
        )

    suavizada[zero_mask] = 0
    suavizada = zeros(suavizada)
    suavizada[zero_mask] = 0
    suavizada = _preserve_total(curva, suavizada, active_mask)
    suavizada[zero_mask] = 0

    return curva.copy(), i_final, suavizada
