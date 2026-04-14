from __future__ import annotations

from .models import DesignInputs, FilterKind, OpAmpModel


def design_frequency_hz(inputs: DesignInputs) -> float:
    if inputs.kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        return float(inputs.spec.passband_hz)
    passband = inputs.spec.passband_hz
    return max(float(passband[0]), float(passband[1]))


def recommend_opamps(inputs: DesignInputs) -> list[OpAmpModel]:
    wpa = design_frequency_hz(inputs)
    if wpa <= 50e3:
        return [
            OpAmpModel.LM324,
            OpAmpModel.LM318,
            OpAmpModel.UA741,
            OpAmpModel.TL082,
            OpAmpModel.LM7171,
            OpAmpModel.LM6164,
            OpAmpModel.LM6165,
            OpAmpModel.LM6171,
        ]
    if wpa <= 300e3:
        return [
            OpAmpModel.LM318,
            OpAmpModel.TL082,
            OpAmpModel.LM7171,
            OpAmpModel.LM6164,
            OpAmpModel.LM6165,
            OpAmpModel.LM6171,
        ]
    if wpa <= 1e6:
        return [
            OpAmpModel.LM318,
            OpAmpModel.LM7171,
            OpAmpModel.LM6164,
            OpAmpModel.LM6165,
            OpAmpModel.LM6171,
        ]
    if wpa <= 5e6:
        return [
            OpAmpModel.LM7171,
            OpAmpModel.LM6164,
            OpAmpModel.LM6165,
        ]
    if wpa <= 7e6:
        return [
            OpAmpModel.LM6164,
            OpAmpModel.LM6165,
        ]
    if wpa <= 30e6:
        return [OpAmpModel.LM6165]
    return []
