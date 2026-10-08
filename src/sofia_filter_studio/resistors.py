from __future__ import annotations

import math
from bisect import bisect_left
from functools import lru_cache
from itertools import product

from .models import ResistorNetwork, ResistorSeries


SERIES_VALUES: dict[ResistorSeries, tuple[float, ...]] = {
    ResistorSeries.E12: (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2),
    ResistorSeries.E24: (
        1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
        3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
    ),
    ResistorSeries.E48: (
        1.00, 1.05, 1.10, 1.15, 1.21, 1.27, 1.33, 1.40, 1.47, 1.54, 1.62, 1.69,
        1.78, 1.87, 1.96, 2.05, 2.15, 2.26, 2.37, 2.49, 2.61, 2.74, 2.87, 3.01,
        3.16, 3.32, 3.48, 3.65, 3.83, 4.02, 4.22, 4.42, 4.64, 4.87, 5.11, 5.36,
        5.62, 5.90, 6.19, 6.49, 6.81, 7.15, 7.50, 7.87, 8.25, 8.66, 9.09, 9.53,
    ),
    ResistorSeries.E96: (
        1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30,
        1.33, 1.37, 1.40, 1.43, 1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74,
        1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
        2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09,
        3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
        4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
        5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32,
        7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76,
    ),
}


def commercial_values(series: ResistorSeries, decades: range = range(0, 8)) -> list[float]:
    values: list[float] = []
    base = SERIES_VALUES[series]
    for decade in decades:
        multiplier = 10 ** decade
        values.extend(value * multiplier for value in base)
    return values


@lru_cache(maxsize=4096)
def fit_resistor_ratio(
    ratio: float,
    series: ResistorSeries,
    low_ohms: float = 1e3,
    high_ohms: float = 100e3,
) -> tuple[float, float]:
    """Commercial (Rg, Rf) pair, Rg within [low, high], whose Rf/Rg is closest to ``ratio``.

    Gain-setting resistors only matter through their ratio, so picking both from the series is far
    more accurate than fixing Rg and rounding Rf alone.
    """
    pool = sorted(commercial_values(series, range(-1, 8)))
    best: tuple[float, float, float] | None = None
    for rg in pool:
        if not low_ohms <= rg <= high_ohms:
            continue
        index = bisect_left(pool, ratio * rg)
        for rf in pool[max(0, index - 1) : index + 1]:
            error = abs(rf / rg - ratio) / ratio
            if best is None or error < best[2] - 1e-12:
                best = (rg, rf, error)
    return best[0], best[1]


def _series_value(parts: tuple[float, ...]) -> float:
    return sum(parts)


def _parallel_value(parts: tuple[float, ...]) -> float:
    return 1.0 / sum(1.0 / part for part in parts)


def _candidate_pool(target_ohms: float, series: ResistorSeries) -> list[float]:
    if target_ohms <= 0:
        raise ValueError("target_ohms must be positive")
    return list(_decade_pool(int(math.floor(math.log10(target_ohms))), series))


@lru_cache(maxsize=256)
def _decade_pool(exponent: int, series: ResistorSeries) -> tuple[float, ...]:
    # Never return an empty pool: tiny targets fall back to the smallest decades (10 mohm and up).
    low = max(-2, exponent - 2)
    decades = range(low, max(low + 1, exponent + 3))
    return tuple(sorted(commercial_values(series, decades)))


def fit_resistor_network(
    label: str,
    target_ohms: float,
    series: ResistorSeries,
    allow_arrays: bool,
    max_parts: int,
) -> ResistorNetwork:
    candidates = _candidate_pool(target_ohms, series)
    best = ResistorNetwork(
        label=label,
        target_ohms=target_ohms,
        realized_ohms=candidates[0],
        connection="single",
        parts_ohms=[candidates[0]],
        relative_error=abs(candidates[0] - target_ohms) / target_ohms,
    )

    def consider(connection: str, parts: tuple[float, ...], realized: float) -> None:
        nonlocal best
        error = abs(realized - target_ohms) / target_ohms
        if error + 1e-12 < best.relative_error:
            best = ResistorNetwork(
                label=label,
                target_ohms=target_ohms,
                realized_ohms=realized,
                connection=connection,
                parts_ohms=list(parts),
                relative_error=error,
            )

    def nearest(value: float) -> list[float]:
        index = bisect_left(candidates, value)
        return candidates[max(0, index - 1) : index + 1]

    # The best single value is one of the two commercial neighbours of the target.
    for value in nearest(target_ohms):
        consider("single", (value,), value)

    if not allow_arrays or max_parts < 2:
        return best

    for size in range(2, max_parts + 1):
        # Choose size-1 parts freely, then the last part is the commercial value closest to the ideal
        # complement: the realized value is monotonic in that part, so its two neighbours bracket the optimum.
        for head in product(candidates, repeat=size - 1):
            remaining = target_ohms - sum(head)
            if remaining > 0:
                for last in nearest(remaining):
                    parts = (*head, last)
                    consider("series", parts, _series_value(parts))
            remaining_conductance = 1.0 / target_ohms - sum(1.0 / part for part in head)
            if remaining_conductance > 0:
                for last in nearest(1.0 / remaining_conductance):
                    parts = (*head, last)
                    consider("parallel", parts, _parallel_value(parts))
    return best
