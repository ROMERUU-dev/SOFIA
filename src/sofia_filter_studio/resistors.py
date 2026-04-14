from __future__ import annotations

import math
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
}


def commercial_values(series: ResistorSeries, decades: range = range(0, 8)) -> list[float]:
    values: list[float] = []
    base = SERIES_VALUES[series]
    for decade in decades:
        multiplier = 10 ** decade
        values.extend(value * multiplier for value in base)
    return values


def _series_value(parts: tuple[float, ...]) -> float:
    return sum(parts)


def _parallel_value(parts: tuple[float, ...]) -> float:
    return 1.0 / sum(1.0 / part for part in parts)


def _candidate_pool(target_ohms: float, series: ResistorSeries) -> list[float]:
    if target_ohms <= 0:
        raise ValueError("target_ohms must be positive")
    exponent = int(math.floor(math.log10(target_ohms)))
    decades = range(max(0, exponent - 2), exponent + 3)
    values = commercial_values(series, decades)
    values.sort()
    return values


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

    for value in candidates:
        consider("single", (value,), value)

    if not allow_arrays or max_parts < 2:
        return best

    limited = candidates[:]
    for size in range(2, max_parts + 1):
        for parts in product(limited, repeat=size):
            consider("series", parts, _series_value(parts))
            consider("parallel", parts, _parallel_value(parts))
    return best
