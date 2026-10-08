"""Ideal frequency response of a design, computed from its poles and zeros (no SPICE needed)."""

from __future__ import annotations

import math

from .models import DesignInputs, DesignResult, FilterKind
from .netlist import ac_sweep_limits


def log_frequencies(start_hz: float, stop_hz: float, points_per_decade: int = 100) -> list[float]:
    decades = math.log10(stop_hz / start_hz)
    count = max(2, int(decades * points_per_decade) + 1)
    return [start_hz * 10 ** (decades * index / (count - 1)) for index in range(count)]


def spec_bands(inputs: DesignInputs, start_hz: float, stop_hz: float) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """(passbands, stopbands) of the specification, clipped to the plotted range."""
    if inputs.kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        fp, fs = float(inputs.spec.passband_hz), float(inputs.spec.stopband_hz)
        if inputs.kind is FilterKind.LOWPASS:
            return [(start_hz, fp)], [(fs, stop_hz)]
        return [(fp, stop_hz)], [(start_hz, fs)]
    fp1, fp2 = map(float, inputs.spec.passband_hz)
    fs1, fs2 = map(float, inputs.spec.stopband_hz)
    if inputs.kind is FilterKind.BANDPASS:
        return [(fp1, fp2)], [(start_hz, fs1), (fs2, stop_hz)]
    return [(start_hz, fp1), (fp2, stop_hz)], [(fs1, fs2)]


def ideal_response_db(inputs: DesignInputs, result: DesignResult, freqs_hz: list[float]) -> list[float]:
    """Magnitude in dB, normalized so the passband peak sits at 0 dB."""
    magnitudes: list[float] = []
    for freq in freqs_hz:
        s = complex(0, 2 * math.pi * freq)
        value = complex(1, 0)
        for stage in result.stages:
            if inputs.kind is FilterKind.HIGHPASS:
                numerator = s**stage.order
            elif inputs.kind is FilterKind.BANDPASS:
                numerator = s
            elif inputs.kind is FilterKind.BANDSTOP:
                omega_z = 2 * math.pi * stage.zero_frequency_hz
                numerator = s * s + omega_z * omega_z
            else:
                numerator = 1
            for pole in stage.poles:
                numerator /= s - pole
            value *= numerator
        magnitudes.append(abs(value))
    passbands, _ = spec_bands(inputs, freqs_hz[0], freqs_hz[-1])
    in_band = [mag for freq, mag in zip(freqs_hz, magnitudes) if any(lo <= freq <= hi for lo, hi in passbands)]
    reference = max(in_band or magnitudes) or 1.0
    return [20 * math.log10(max(mag / reference, 1e-15)) for mag in magnitudes]


def design_response(inputs: DesignInputs, result: DesignResult, points_per_decade: int = 100) -> tuple[list[float], list[float]]:
    start_hz, stop_hz = ac_sweep_limits(inputs)
    freqs = log_frequencies(start_hz, stop_hz, points_per_decade)
    return freqs, ideal_response_db(inputs, result, freqs)
