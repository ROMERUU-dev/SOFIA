from __future__ import annotations

import cmath
import json
import math
from dataclasses import asdict

from .models import Approximation, DesignInputs, DesignResult, FilterKind, Stage, Topology
from .opamps import recommend_opamps, stability_warnings
from .synthesis import practical_notes_for_stage, synthesize_stage_realizations


def _epsilon(passband_ripple_db: float) -> float:
    return math.sqrt(10 ** (passband_ripple_db / 10) - 1)


def _asinh(value: float) -> float:
    return math.asinh(value)


def _butterworth_poles(order: int) -> list[complex]:
    poles: list[complex] = []
    for k in range(1, order + 1):
        angle = math.pi * (2 * k + order - 1) / (2 * order)
        pole = complex(math.cos(angle), math.sin(angle))
        if pole.real < 0:
            poles.append(pole)
    return poles


def _chebyshev_poles(order: int, epsilon: float) -> list[complex]:
    poles: list[complex] = []
    alpha = _asinh(1 / epsilon) / order
    for k in range(1, order + 1):
        theta = math.pi * (2 * k - 1) / (2 * order)
        sigma = -math.sinh(alpha) * math.sin(theta)
        omega = math.cosh(alpha) * math.cos(theta)
        pole = complex(sigma, omega)
        if pole.real < 0:
            poles.append(pole)
    return poles


def _pair_poles(poles: list[complex], pair_real_poles: bool = False) -> list[tuple[complex, ...]]:
    ordered = sorted(poles, key=lambda pole: (round(abs(pole.imag), 12), pole.imag), reverse=True)
    groups: list[tuple[complex, ...]] = []
    used: set[int] = set()
    for index, pole in enumerate(ordered):
        if index in used:
            continue
        if abs(pole.imag) < 1e-9:
            groups.append((pole,))
            used.add(index)
            continue
        for other_index in range(index + 1, len(ordered)):
            other = ordered[other_index]
            if other_index in used:
                continue
            if abs(pole.real - other.real) < 1e-9 and abs(pole.imag + other.imag) < 1e-9:
                groups.append((pole, other))
                used.add(index)
                used.add(other_index)
                break
        else:
            groups.append((pole,))
            used.add(index)
    if pair_real_poles:
        # Band filters need second-order sections; very wide bands can yield real pole pairs (Q < 0.5).
        singles = [group[0] for group in groups if len(group) == 1]
        groups = [group for group in groups if len(group) == 2]
        singles.sort(key=lambda pole: pole.real)
        while len(singles) >= 2:
            groups.append((singles.pop(0), singles.pop(0)))
        groups.extend((pole,) for pole in singles)
    return groups


def _section_from_pole_group(index: int, group: tuple[complex, ...]) -> Stage:
    if len(group) == 1:
        pole = group[0]
        omega_0 = abs(pole)
        return Stage(
            index=index,
            natural_frequency_hz=omega_0 / (2 * math.pi),
            q=None,
            order=1,
            poles=group,
            damping_hz=abs(pole.real) / (2 * math.pi),
        )

    first, second = group
    omega_0 = math.sqrt(abs(first * second))
    q = omega_0 / -(first + second).real
    return Stage(
        index=index,
        natural_frequency_hz=omega_0 / (2 * math.pi),
        q=q,
        order=2,
        poles=group,
        damping_hz=-(first + second).real / (2 * math.pi),
    )


def _prototype_poles(order: int, approximation: Approximation, epsilon: float) -> list[complex]:
    if approximation is Approximation.BUTTERWORTH:
        return _butterworth_poles(order)
    if approximation is Approximation.CHEBYSHEV_I:
        return _chebyshev_poles(order, epsilon)
    raise ValueError(f"Unsupported approximation: {approximation}")


def _low_high_ratios(inputs: DesignInputs) -> tuple[float, float]:
    wp = float(inputs.spec.passband_hz)
    ws = float(inputs.spec.stopband_hz)
    if inputs.kind is FilterKind.LOWPASS:
        if ws <= wp:
            raise ValueError("For lowpass, stopband frequency must be greater than passband frequency")
        return wp, ws / wp
    if inputs.kind is FilterKind.HIGHPASS:
        if ws >= wp:
            raise ValueError("For highpass, stopband frequency must be smaller than passband frequency")
        return wp, wp / ws
    raise ValueError("Only lowpass/highpass are valid in _low_high_ratios")


def _bandpass_bandstop_terms(inputs: DesignInputs) -> tuple[float, float, float]:
    wp1, wp2 = map(float, inputs.spec.passband_hz)
    ws1, ws2 = map(float, inputs.spec.stopband_hz)
    if not (wp1 < wp2 and ws1 < ws2):
        raise ValueError("Band edges must be ordered increasingly")
    omega_0 = 2 * math.pi * math.sqrt(wp1 * wp2)
    bandwidth = 2 * math.pi * (wp2 - wp1)
    if bandwidth <= 0:
        raise ValueError("Bandwidth must be positive")
    if inputs.kind is FilterKind.BANDPASS:
        candidates = [
            abs((2 * math.pi * ws1) ** 2 - omega_0**2) / (bandwidth * 2 * math.pi * ws1),
            abs((2 * math.pi * ws2) ** 2 - omega_0**2) / (bandwidth * 2 * math.pi * ws2),
        ]
    else:
        candidates = [
            bandwidth * 2 * math.pi * ws1 / abs((2 * math.pi * ws1) ** 2 - omega_0**2),
            bandwidth * 2 * math.pi * ws2 / abs((2 * math.pi * ws2) ** 2 - omega_0**2),
        ]
    ratio = min(candidates)
    if ratio <= 1:
        raise ValueError("Band transformation produced an invalid selectivity ratio")
    return omega_0, bandwidth, ratio


def _order_for_ratio(inputs: DesignInputs, ratio: float) -> int:
    ap = inputs.passband_ripple_db
    a_stop = inputs.stopband_attenuation_db
    discrimination = (10 ** (a_stop / 10) - 1) / (10 ** (ap / 10) - 1)
    if inputs.approximation is Approximation.CHEBYSHEV_I:
        exact = math.acosh(math.sqrt(discrimination)) / math.acosh(ratio)
    else:
        exact = math.log10(discrimination) / (2 * math.log10(ratio))
    # Guard against values like 4.0000000001 caused by floating point noise.
    return max(1, math.ceil(exact - 1e-9))


def _estimate_order(inputs: DesignInputs, epsilon: float) -> tuple[int, dict[str, float]]:
    if inputs.kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        wp, ratio = _low_high_ratios(inputs)
        order = _order_for_ratio(inputs, ratio)
        return order, {"passband_hz": wp, "ratio": ratio}

    omega_0, bandwidth, ratio = _bandpass_bandstop_terms(inputs)
    prototype_order = _order_for_ratio(inputs, ratio)
    return prototype_order, {
        "center_frequency_hz": omega_0 / (2 * math.pi),
        "bandwidth_hz": bandwidth / (2 * math.pi),
        "ratio": ratio,
    }


def _scale_prototype_poles(inputs: DesignInputs, order: int, epsilon: float, poles: list[complex]) -> list[complex]:
    if inputs.kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        wp = 2 * math.pi * float(inputs.spec.passband_hz)
        if inputs.approximation is Approximation.BUTTERWORTH:
            omega_c = wp / (epsilon ** (1 / order)) if inputs.kind is FilterKind.LOWPASS else wp * (epsilon ** (1 / order))
        else:
            omega_c = wp
        if inputs.kind is FilterKind.LOWPASS:
            return [omega_c * pole for pole in poles]
        return [omega_c / pole for pole in poles]

    omega_0, bandwidth, _ = _bandpass_bandstop_terms(inputs)
    if inputs.approximation is Approximation.BUTTERWORTH:
        # Normalize the prototype so its -Ap point (not its -3 dB point) lands on the band edges.
        poles = [pole * epsilon ** (-1 / order) for pole in poles]
    transformed: list[complex] = []
    for pole in poles:
        if inputs.kind is FilterKind.BANDPASS:
            term = cmath.sqrt((bandwidth * pole) ** 2 - 4 * omega_0**2)
            transformed.extend(((bandwidth * pole + term) / 2, (bandwidth * pole - term) / 2))
        else:
            term = cmath.sqrt((bandwidth / pole) ** 2 - 4 * omega_0**2)
            transformed.extend(((bandwidth / pole + term) / 2, (bandwidth / pole - term) / 2))
    return [pole for pole in transformed if pole.real < 0]


def design_filter(inputs: DesignInputs) -> DesignResult:
    inputs.validate()
    epsilon = _epsilon(inputs.passband_ripple_db)
    prototype_order, summary = _estimate_order(inputs, epsilon)
    prototype_poles = _prototype_poles(prototype_order, inputs.approximation, epsilon)
    poles = _scale_prototype_poles(inputs, prototype_order, epsilon, prototype_poles)
    is_band = inputs.kind in {FilterKind.BANDPASS, FilterKind.BANDSTOP}
    order = prototype_order * 2 if is_band else prototype_order
    stages = [
        _section_from_pole_group(index, group)
        for index, group in enumerate(_pair_poles(poles, pair_real_poles=is_band), start=1)
    ]
    if inputs.kind is FilterKind.BANDSTOP:
        # Every band-stop section carries its transmission zeros at the band center.
        notch_hz = summary["center_frequency_hz"]
        for stage in stages:
            stage.zero_frequency_hz = notch_hz
    if inputs.kind is FilterKind.BANDPASS:
        # Staggered sections are scaled for unity gain at the band center, not at their own peaks.
        for stage in stages:
            stage.gain_reference_hz = summary["center_frequency_hz"]
    warnings: list[str] = []
    if inputs.topology is not Topology.OTA and any(stage.q is not None and stage.q > 10 for stage in stages):
        warnings.append("At least one section has high Q; a Tow-Thomas or MFB realization may be safer than unity-gain Sallen-Key.")
    summary.update(
        {
            "kind": inputs.kind,
            "approximation": inputs.approximation,
            "topology": inputs.topology,
            "opamp": inputs.opamp,
            "resistor_series": inputs.resistor_series,
            "allow_resistor_arrays": inputs.allow_resistor_arrays,
            "recommended_opamps": [model.value for model in recommend_opamps(inputs)],
        }
    )
    synthesize_stage_realizations(inputs, stages)
    for stage in stages:
        warnings.extend(practical_notes_for_stage(inputs, stage))
    warnings.extend(stability_warnings(inputs, {stage.realization.topology for stage in stages}))
    return DesignResult(order=order, epsilon=epsilon, poles=poles, stages=stages, summary=summary, warnings=warnings)


def format_result(result: DesignResult) -> str:
    return json.dumps(result.as_dict(), indent=2, default=str)


def summarize_inputs(inputs: DesignInputs) -> str:
    return json.dumps(asdict(inputs), indent=2, default=str)
