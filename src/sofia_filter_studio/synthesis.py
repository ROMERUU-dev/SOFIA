from __future__ import annotations

import math

from .models import DesignInputs, FilterKind, ResistorNetwork, Stage, StageRealization, Topology
from .resistors import fit_resistor_network

MIN_PRACTICAL_RESISTANCE = 100.0
MAX_PRACTICAL_RESISTANCE = 1_000_000.0


def synthesize_stage_realizations(inputs: DesignInputs, stages: list[Stage]) -> None:
    for stage in stages:
        stage.realization = synthesize_stage_realization(inputs, stage)


def practical_notes_for_stage(inputs: DesignInputs, stage: Stage) -> list[str]:
    realization = stage.realization
    if realization is None:
        return []
    target_values = list(realization.resistor_targets_ohms.values())
    if not target_values:
        return []
    notes: list[str] = []
    min_target = min(target_values)
    max_target = max(target_values)
    if min_target < 10:
        factor = max(10, math.ceil(10 / max(min_target, 1e-12)))
        suggested_cap = realization.capacitor_values_f["C1"] / factor
        notes.append(
            f"Stage {stage.index} requests resistors below 10 ohm. A capacitor near {suggested_cap:.3e} F would move the design toward a saner range."
        )
    if max_target > MAX_PRACTICAL_RESISTANCE:
        factor = max(10, math.ceil(max_target / MAX_PRACTICAL_RESISTANCE))
        suggested_cap = realization.capacitor_values_f["C1"] * factor
        notes.append(
            f"Stage {stage.index} requests resistors above 1 Mohm. A capacitor near {suggested_cap:.3e} F would reduce noise and sensitivity."
        )
    return notes


def synthesize_stage_realization(inputs: DesignInputs, stage: Stage) -> StageRealization:
    topology = _select_topology(inputs, stage)
    if inputs.auto_stage_capacitor:
        return _optimize_stage_realization(inputs, stage, topology)
    return _synthesize_for_topology(inputs, stage, topology, inputs.stage_capacitor_f)


def _select_topology(inputs: DesignInputs, stage: Stage) -> Topology:
    if inputs.topology is not Topology.AUTO:
        return inputs.topology
    q = stage.q or 0.707
    if stage.order == 1:
        return Topology.SALLEN_KEY
    if inputs.kind is FilterKind.BANDPASS:
        return Topology.MFB if q <= 3 else Topology.TOW_THOMAS
    if inputs.kind is FilterKind.BANDSTOP:
        return Topology.TOW_THOMAS
    if q <= 1.2:
        return Topology.SALLEN_KEY
    if q <= 4:
        return Topology.ANTONIOU
    return Topology.TOW_THOMAS


def _optimize_stage_realization(inputs: DesignInputs, stage: Stage, topology: Topology) -> StageRealization:
    candidates = [inputs.stage_capacitor_f * factor for factor in (0.01, 0.1, 1.0, 10.0, 100.0)]
    scored: list[tuple[float, StageRealization]] = []
    for capacitor in candidates:
        realization = _synthesize_for_topology(inputs, stage, topology, capacitor)
        scored.append((_score_realization(realization), realization))
    scored.sort(key=lambda item: item[0])
    best = scored[0][1]
    if abs(best.capacitor_values_f["C1"] - inputs.stage_capacitor_f) > 1e-30:
        best.notes.append(
            f"Stage capacitor auto-tuned from {inputs.stage_capacitor_f:.3e} F to {best.capacitor_values_f['C1']:.3e} F."
        )
    return best


def _score_realization(realization: StageRealization) -> float:
    penalty = 0.0
    for network in realization.resistor_networks.values():
        value = network.realized_ohms
        penalty += network.relative_error * 200
        if value < MIN_PRACTICAL_RESISTANCE:
            penalty += MIN_PRACTICAL_RESISTANCE / max(value, 1e-12)
        if value > MAX_PRACTICAL_RESISTANCE:
            penalty += value / MAX_PRACTICAL_RESISTANCE
    return penalty


def _fit(inputs: DesignInputs, label: str, target_ohms: float) -> ResistorNetwork:
    return fit_resistor_network(
        label=label,
        target_ohms=target_ohms,
        series=inputs.resistor_series,
        allow_arrays=inputs.allow_resistor_arrays,
        max_parts=inputs.max_resistors_per_network,
    )


def _synthesize_for_topology(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    if stage.order == 1:
        return _synthesize_first_order(inputs, stage, topology, capacitor)
    if topology is Topology.SALLEN_KEY:
        return _synthesize_sallen_key(inputs, stage, topology, capacitor)
    if topology is Topology.TOW_THOMAS:
        return _synthesize_tow_thomas(inputs, stage, topology, capacitor)
    if topology is Topology.MFB:
        return _synthesize_mfb(inputs, stage, topology, capacitor)
    if topology is Topology.ANTONIOU:
        return _synthesize_antoniou(inputs, stage, topology, capacitor)
    return _synthesize_generic_placeholder(inputs, stage, topology, capacitor)


def _synthesize_first_order(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    target_r = 1 / (omega_0 * capacitor)
    network = _fit(inputs, "R1", target_r)
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=1.0,
        resistor_targets_ohms={"R1": target_r},
        capacitor_values_f={"C1": capacitor},
        resistor_networks={"R1": network},
        notes=["First-order RC section synthesized from stage frequency."],
    )


def _synthesize_sallen_key(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    if stage.q is None:
        return _synthesize_first_order(inputs, stage, topology, capacitor)
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    r_target = 1 / (omega_0 * capacitor)
    gain = 3 - (1 / stage.q)
    notes: list[str] = []
    if gain <= 1:
        gain = 1.0
        notes.append("Requested Q is below the non-unity-gain Sallen-Key region. The stage was clamped to unity gain.")
    if gain >= 3:
        gain = 2.9
        notes.append("Requested Q would require gain >= 3. The stage was clipped to a safer value.")
    rg_target = 10_000.0
    rf_target = rg_target * (gain - 1)
    networks = {
        "R1": _fit(inputs, "R1", r_target),
        "R2": _fit(inputs, "R2", r_target),
        "Rg": _fit(inputs, "Rg", rg_target),
        "Rf": _fit(inputs, "Rf", max(rf_target, 1.0)),
    }
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=gain,
        resistor_targets_ohms={"R1": r_target, "R2": r_target, "Rg": rg_target, "Rf": rf_target},
        capacitor_values_f={"C1": capacitor, "C2": capacitor},
        resistor_networks=networks,
        notes=notes + ["Equal-C, equal-R Sallen-Key synthesis derived from the legacy gain/Q relation Av = 3 - 1/Q."],
    )


def _synthesize_tow_thomas(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q or 0.707
    base_r = 1 / (omega_0 * capacitor)
    q_r = max(base_r * q, 1.0)
    resistor_targets = {"Rbase": base_r, "Rq": q_r}
    notes = ["Tow-Thomas synthesis anchored to the legacy relations R = 1/(C*w0) and Rq = Q*R."]
    if inputs.kind is FilterKind.BANDPASS:
        bw_hz = stage.natural_frequency_hz / max(q, 1e-9)
        resistor_targets["Rbw"] = 1 / (2 * math.pi * capacitor * bw_hz)
        notes.append("Band-pass extra resistor uses the legacy relation Rbw = 1/(C*BW).")
    elif inputs.kind is FilterKind.BANDSTOP:
        resistor_targets["Rnotch"] = 1 / (capacitor * omega_0)
        notes.append("Band-stop extra resistor uses the legacy notch relation around the center frequency.")
    networks = {name: _fit(inputs, name, target) for name, target in resistor_targets.items()}
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=1.0,
        resistor_targets_ohms=resistor_targets,
        capacitor_values_f={"C1": capacitor, "C2": capacitor},
        resistor_networks=networks,
        notes=notes,
    )


def _synthesize_mfb(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q or 0.707
    notes: list[str] = []
    if inputs.kind is FilterKind.BANDPASS:
        alpha = omega_0 / q
        bandwidth_hz = stage.natural_frequency_hz / max(q, 1e-9)
        r_input = 2 / (capacitor * alpha)
        r_bandwidth = 1 / (2 * math.pi * capacitor * bandwidth_hz)
        r_feedback = 1 / (capacitor**2 * r_bandwidth * r_input * omega_0**2)
        targets = {"R1": r_input, "R2": r_feedback, "R3": r_bandwidth}
        notes.append("MFB band-pass synthesis follows the legacy relations R1 = 2/(C*alpha), R3 = 1/(C*BW) and R2 from w0.")
    else:
        base_r = 1 / (omega_0 * capacitor)
        targets = {"R1": base_r / max(q, 0.1), "R2": base_r, "R3": base_r * max(q, 0.1)}
        notes.append("Non-band MFB remains a practical heuristic; the legacy code only implemented explicit MFB sizing for band-pass.")
    networks = {name: _fit(inputs, name, target) for name, target in targets.items()}
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=1.0,
        resistor_targets_ohms=targets,
        capacitor_values_f={"C1": capacitor, "C2": capacitor},
        resistor_networks=networks,
        notes=notes,
    )


def _synthesize_antoniou(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    base_r = 1 / (omega_0 * capacitor)
    q = stage.q or 0.707
    q_r = base_r * q
    resistor_targets = {"R1": base_r, "R2": base_r, "R3": base_r, "R4": base_r, "Rq": q_r}
    notes = ["Antoniou synthesis follows the legacy base relation R = 1/(C*w0) with the Q-setting resistor Rq = Q*R."]
    if inputs.kind is FilterKind.BANDPASS:
        bw_hz = stage.natural_frequency_hz / max(q, 1e-9)
        resistor_targets["Rbw"] = 1 / (2 * math.pi * capacitor * bw_hz)
        notes.append("Band-pass extra resistor uses the same BW-driven relation found in the legacy synthesis flow.")
    elif inputs.kind is FilterKind.BANDSTOP:
        resistor_targets["Rnotch"] = 1 / (capacitor * omega_0)
        notes.append("Band-stop extra resistor is derived around the notch center frequency.")
    networks = {name: _fit(inputs, name, target) for name, target in resistor_targets.items()}
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=1.0,
        resistor_targets_ohms=resistor_targets,
        capacitor_values_f={"C1": capacitor, "C2": capacitor},
        resistor_networks=networks,
        notes=notes,
    )


def _synthesize_generic_placeholder(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    target_r = 1 / (omega_0 * capacitor)
    network = _fit(inputs, "R1", target_r)
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=1.0,
        resistor_targets_ohms={"R1": target_r},
        capacitor_values_f={"C1": capacitor},
        resistor_networks={"R1": network},
        notes=["Generic placeholder synthesis."],
    )
