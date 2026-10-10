from __future__ import annotations

import math

from .models import DesignInputs, FilterKind, OpAmpModel

# Input bias current of each bundled macro-model, measured in LTspice through a 100 kohm source.
INPUT_BIAS_CURRENT_A = {
    OpAmpModel.LM324: 45e-9,
    OpAmpModel.LM318: 150e-9,
    OpAmpModel.UA741: 80e-9,
    OpAmpModel.TL082: 0.0,
    OpAmpModel.LM7171: 3.1e-6,
    OpAmpModel.LM6164: 2.3e-6,
    OpAmpModel.LM6165: 2.3e-6,
    OpAmpModel.LM6171: 1.0e-6,
}

# DC offset each stage may add through bias current; stages cascade, so keep it small.
MAX_BIAS_OFFSET_PER_STAGE_V = 0.01


# Decompensated models are only stable above this closed-loop (noise) gain; the filter sections here
# run at noise gains of about 1 to 3, and transient simulation shows them oscillating at 15-105 MHz.
MIN_STABLE_GAIN = {OpAmpModel.LM6164: 5, OpAmpModel.LM6165: 25}

# 100-200 MHz parts: with their macro-models LTspice rarely finds the operating point of Tow-Thomas
# and Antoniou sections (it keeps stepping and never finishes), so the automatic topology avoids them.
HIGH_SPEED_MODELS = {OpAmpModel.LM7171, OpAmpModel.LM6171}


def stability_warnings(inputs: DesignInputs, topologies: set) -> list[str]:
    from .models import Topology

    warnings: list[str] = []
    min_gain = MIN_STABLE_GAIN.get(inputs.opamp)
    if min_gain is not None:
        warnings.append(
            f"El {inputs.opamp.value} es descompensado (solo es estable con ganancia de lazo cerrado >= {min_gain}); en estas etapas trabaja cerca de ganancia 1 y va a oscilar. Usa LM6171, LM7171 o LM318."
        )
    if inputs.opamp in HIGH_SPEED_MODELS and topologies & {Topology.TOW_THOMAS, Topology.ANTONIOU}:
        if inputs.kind is FilterKind.BANDSTOP:
            advice = "Un rechaza banda solo se arma con Tow-Thomas: para simularlo usa TL082 o LM318."
        else:
            advice = "Usa Sallen-Key o MFB (la topología automática los elige) o un opamp más lento (TL082, LM318)."
        warnings.append(
            f"Con el modelo del {inputs.opamp.value} (100-200 MHz), LTspice casi nunca encuentra el punto de operación de las etapas Tow-Thomas o Antoniou y se queda calculando. {advice}"
        )
    return warnings


def max_bias_safe_resistance(model: OpAmpModel) -> float:
    current = INPUT_BIAS_CURRENT_A.get(model, 0.0)
    if current <= 0:
        return math.inf
    return MAX_BIAS_OFFSET_PER_STAGE_V / current


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
