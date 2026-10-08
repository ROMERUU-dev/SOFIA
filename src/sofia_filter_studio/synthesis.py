from __future__ import annotations

import math

from .models import DesignInputs, FilterKind, ResistorNetwork, Stage, StageRealization, Topology
from .opamps import INPUT_BIAS_CURRENT_A, max_bias_safe_resistance
from .resistors import fit_resistor_network

MIN_PRACTICAL_RESISTANCE = 100.0
MAX_PRACTICAL_RESISTANCE = 1_000_000.0
E12_CAPACITORS = (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2)

# Gain-setting resistor shared by the non-inverting Sallen-Key stages.
SALLEN_KEY_RG = 10_000.0
SALLEN_KEY_MAX_GAIN_LP_HP = 2.9
SALLEN_KEY_MAX_GAIN_BP = 3.9
SALLEN_KEY_BP_SENSITIVE_Q = 5.0

# Realization notes that mean the stage deviates from the request; they are surfaced as warnings.
COMPROMISE_MARKERS = ("cannot realize", "clamped", "clipped", "too low", "very sensitive")

# Topologies that can realize each section type. Band-stop needs a finite transmission zero,
# which plain Sallen-Key and MFB sections cannot produce.
SUPPORTED_KINDS = {
    Topology.SALLEN_KEY: {FilterKind.LOWPASS, FilterKind.HIGHPASS, FilterKind.BANDPASS},
    Topology.MFB: {FilterKind.LOWPASS, FilterKind.HIGHPASS, FilterKind.BANDPASS},
    Topology.TOW_THOMAS: set(FilterKind),
    Topology.ANTONIOU: set(FilterKind),
}


def synthesize_stage_realizations(inputs: DesignInputs, stages: list[Stage]) -> None:
    for stage in stages:
        stage.realization = synthesize_stage_realization(inputs, stage)


def practical_notes_for_stage(inputs: DesignInputs, stage: Stage) -> list[str]:
    realization = stage.realization
    if realization is None:
        return []
    notes = [
        f"Stage {stage.index}: {note}"
        for note in realization.notes
        if any(marker in note for marker in COMPROMISE_MARKERS)
    ]
    target_values = list(realization.resistor_targets_ohms.values())
    if not target_values:
        return notes
    min_target = min(target_values)
    max_target = max(target_values)
    base_cap = realization.capacitor_values_f["C1"]
    if min_target < 10:
        factor = max(10, math.ceil(10 / max(min_target, 1e-12)))
        notes.append(
            f"Stage {stage.index} requests resistors below 10 ohm. A capacitor near {base_cap / factor:.3e} F would move the design toward a saner range."
        )
    if max_target > MAX_PRACTICAL_RESISTANCE:
        factor = max(10, math.ceil(max_target / MAX_PRACTICAL_RESISTANCE))
        notes.append(
            f"Stage {stage.index} requests resistors above 1 Mohm. A capacitor near {base_cap * factor:.3e} F would reduce noise and sensitivity."
        )
    bias_limit = max_bias_safe_resistance(inputs.opamp)
    if bias_limit < max_target <= MAX_PRACTICAL_RESISTANCE:
        offset_mv = max_target * INPUT_BIAS_CURRENT_A[inputs.opamp] * 1e3
        notes.append(
            f"Stage {stage.index} uses resistors up to {max_target:.0f} ohm; the {inputs.opamp.value} bias current adds about {offset_mv:.0f} mV of DC offset. A larger capacitor would lower it."
        )
    return notes


def synthesize_stage_realization(inputs: DesignInputs, stage: Stage) -> StageRealization:
    topology, fallback_note = _select_topology(inputs, stage)
    if inputs.auto_stage_capacitor:
        realization = _optimize_stage_realization(inputs, stage, topology)
    else:
        realization = _synthesize_for_topology(inputs, stage, topology, inputs.stage_capacitor_f)
    if fallback_note:
        realization.notes.insert(0, fallback_note)
    return realization


def _select_topology(inputs: DesignInputs, stage: Stage) -> tuple[Topology, str | None]:
    if inputs.topology is Topology.AUTO:
        return _auto_topology(inputs, stage), None
    topology = inputs.topology
    supported = SUPPORTED_KINDS.get(topology)
    if supported is not None and stage.order == 2 and inputs.kind not in supported:
        return Topology.TOW_THOMAS, (
            f"{topology.value} cannot realize a {inputs.kind.value} section; this stage uses tow_thomas instead."
        )
    return topology, None


def _auto_topology(inputs: DesignInputs, stage: Stage) -> Topology:
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
    max_resistance = _max_resistance(inputs)
    scored: list[tuple[float, float, StageRealization]] = []
    for capacitor in candidates:
        realization = _synthesize_for_topology(inputs, stage, topology, capacitor)
        scored.append((_score_realization(realization, max_resistance), capacitor, realization))
    scored.sort(key=lambda item: item[0])
    _, capacitor, best = scored[0]
    if abs(capacitor - inputs.stage_capacitor_f) > 1e-30:
        best.notes.append(f"Stage capacitor auto-tuned from {inputs.stage_capacitor_f:.3e} F to {capacitor:.3e} F.")
    return best


def _max_resistance(inputs: DesignInputs) -> float:
    return min(MAX_PRACTICAL_RESISTANCE, max_bias_safe_resistance(inputs.opamp))


def _score_realization(realization: StageRealization, max_resistance: float = MAX_PRACTICAL_RESISTANCE) -> float:
    penalty = 0.0
    for network in realization.resistor_networks.values():
        value = network.realized_ohms
        penalty += network.relative_error * 200
        if value < MIN_PRACTICAL_RESISTANCE:
            penalty += MIN_PRACTICAL_RESISTANCE / max(value, 1e-12)
        if value > max_resistance:
            penalty += value / max_resistance
    return penalty


def _fit(inputs: DesignInputs, label: str, target_ohms: float) -> ResistorNetwork:
    return fit_resistor_network(
        label=label,
        target_ohms=target_ohms,
        series=inputs.resistor_series,
        allow_arrays=inputs.allow_resistor_arrays,
        max_parts=inputs.max_resistors_per_network,
    )


def _realization(
    inputs: DesignInputs,
    stage: Stage,
    topology: Topology,
    gain: float | None,
    targets: dict[str, float],
    capacitors: dict[str, float],
    notes: list[str],
) -> StageRealization:
    return StageRealization(
        topology=topology,
        stage_index=stage.index,
        kind=inputs.kind,
        gain=gain,
        resistor_targets_ohms=targets,
        capacitor_values_f=capacitors,
        resistor_networks={name: _fit(inputs, name, target) for name, target in targets.items()},
        notes=notes,
    )


def _bandpass_peak_gain_target(stage: Stage) -> float:
    """Peak gain that gives this band-pass section unity gain at the filter center."""
    if stage.gain_reference_hz is None or stage.q is None:
        return 1.0
    omega = stage.gain_reference_hz / stage.natural_frequency_hz
    bandwidth_term = omega / stage.q
    relative = bandwidth_term / math.hypot(1 - omega * omega, bandwidth_term)
    return 1 / relative


def _next_e12_capacitor(minimum: float) -> float:
    exponent = math.floor(math.log10(minimum))
    for decade in (exponent, exponent + 1):
        for value in E12_CAPACITORS:
            candidate = value * 10**decade
            if candidate >= minimum * (1 - 1e-9):
                return candidate
    return minimum


def _synthesize_for_topology(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    if stage.order == 1:
        if topology in {Topology.MFB, Topology.TOW_THOMAS}:
            return _synthesize_first_order_inverting(inputs, stage, topology, capacitor)
        return _synthesize_first_order_follower(inputs, stage, topology, capacitor)
    if topology is Topology.SALLEN_KEY:
        return _synthesize_sallen_key(inputs, stage, topology, capacitor)
    if topology is Topology.TOW_THOMAS:
        return _synthesize_tow_thomas(inputs, stage, topology, capacitor)
    if topology is Topology.MFB:
        return _synthesize_mfb(inputs, stage, topology, capacitor)
    if topology is Topology.ANTONIOU:
        return _synthesize_antoniou(inputs, stage, topology, capacitor)
    return _synthesize_generic_placeholder(inputs, stage, topology, capacitor)


def _synthesize_first_order_follower(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    target_r = 1 / (omega_0 * capacitor)
    return _realization(
        inputs,
        stage,
        topology,
        1.0,
        {"R1": target_r},
        {"C1": capacitor},
        ["First-order passive RC section buffered by a voltage follower."],
    )


def _synthesize_first_order_inverting(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    target_r = 1 / (omega_0 * capacitor)
    return _realization(
        inputs,
        stage,
        topology,
        -1.0,
        {"R1": target_r, "R2": target_r},
        {"C1": capacitor},
        ["First-order inverting active section with unity gain, R1 = R2 = 1/(C*w0)."],
    )


def _synthesize_sallen_key(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q
    notes: list[str] = []
    if inputs.kind is FilterKind.BANDPASS:
        # Equal-R, equal-C positive-feedback band-pass: w0 = sqrt(2)/(R*C), Q = sqrt(2)/(4 - K).
        r_target = math.sqrt(2) / (omega_0 * capacitor)
        gain = 4 - math.sqrt(2) / q
        max_gain = SALLEN_KEY_MAX_GAIN_BP
        targets = {"R1": r_target, "R2": r_target, "R3": r_target}
        notes.append("Equal-C, equal-R Sallen-Key band-pass with K = 4 - sqrt(2)/Q and center gain K/(4 - K).")
        if q > SALLEN_KEY_BP_SENSITIVE_Q:
            notes.append(
                f"Q = {q:.2f} makes this Sallen-Key band-pass very sensitive to resistor tolerance and op amp bandwidth; MFB or Tow-Thomas is more robust."
            )
    else:
        # Equal-R, equal-C low-pass/high-pass with the legacy gain/Q relation K = 3 - 1/Q.
        r_target = 1 / (omega_0 * capacitor)
        gain = 3 - 1 / q
        max_gain = SALLEN_KEY_MAX_GAIN_LP_HP
        targets = {"R1": r_target, "R2": r_target}
        notes.append("Equal-C, equal-R Sallen-Key synthesis derived from the legacy gain/Q relation Av = 3 - 1/Q.")
    if gain < 1:
        gain = 1.0
        notes.append("Requested Q is below the equal-component Sallen-Key region; the stage was clamped to unity gain and its Q will be off.")
    if gain > max_gain:
        gain = max_gain
        notes.append(f"Requested Q needs a gain above {max_gain}; the gain was clipped and the realized Q will be lower.")
    if gain - 1 > 1e-9:
        targets["Rg"] = SALLEN_KEY_RG
        targets["Rf"] = SALLEN_KEY_RG * (gain - 1)
    stage_gain = gain
    if inputs.kind is FilterKind.BANDPASS:
        stage_gain = gain / (4 - gain)
        target = _bandpass_peak_gain_target(stage)
        if stage_gain > target:
            # Center gain grows like Q; split R1 into a divider with the same Thevenin resistance
            # so the cascade passes unity at the band center and does not saturate.
            attenuation = target / stage_gain
            r1 = targets.pop("R1")
            targets["R1a"] = r1 / attenuation
            targets["R1b"] = r1 / (1 - attenuation)
            notes.append(f"Input divider R1a/R1b (Thevenin = R1) scales the peak gain from {stage_gain:.2f} to {target:.3f}.")
            stage_gain = target
    return _realization(inputs, stage, topology, stage_gain, targets, {"C1": capacitor, "C2": capacitor}, notes)


def _synthesize_tow_thomas(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q
    base_r = 1 / (omega_0 * capacitor)
    targets = {"R": base_r, "Rq": q * base_r, "Rinv": base_r}
    capacitors = {"C1": capacitor, "C2": capacitor}
    notes = ["Tow-Thomas synthesis anchored to the legacy relations R = 1/(C*w0) and Rq = Q*R."]
    if inputs.kind is FilterKind.LOWPASS:
        targets["R1"] = base_r
        notes.append("Low-pass output taken at the second integrator, DC gain -R/R1 = -1.")
    elif inputs.kind is FilterKind.BANDPASS:
        gain = _bandpass_peak_gain_target(stage)
        targets["R1"] = q * base_r / gain
        notes.append("Band-pass output taken at the lossy integrator; R1 = Q*R/G = 1/(G*C*BW) sets the peak gain G.")
    elif inputs.kind is FilterKind.HIGHPASS:
        capacitors["Cff"] = capacitor
        notes.append("High-pass realized with capacitive feed-forward into the lossy integrator, HF gain -1.")
    else:
        notch_ratio = omega_0 / (2 * math.pi * stage.zero_frequency_hz)
        capacitors["Cff"] = capacitor
        targets["Rff"] = base_r * notch_ratio**2
        notes.append("Band-stop realized with feed-forward Cff = C and Rff = R*(w0/wz)^2, placing the notch at the band center.")
    return _realization(inputs, stage, topology, 1.0, targets, capacitors, notes)


def _synthesize_mfb(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q
    notes: list[str] = []
    if inputs.kind is FilterKind.BANDPASS:
        # Peak gain G = R1/(2*R3); the shunt R2 restores w0 and needs G < 2*Q^2.
        gain = _bandpass_peak_gain_target(stage)
        r_feedback = 2 * q / (omega_0 * capacitor)
        shunt_term = 2 * q * q - gain
        if shunt_term > 0.02 * gain:
            r_input = q / (gain * omega_0 * capacitor)
            targets = {"R1": r_feedback, "R2": q / (omega_0 * capacitor * shunt_term), "R3": r_input}
        else:
            gain = 2 * q * q
            r_input = 1 / (2 * q * omega_0 * capacitor)
            targets = {"R1": r_feedback, "R3": r_input}
            notes.append("Q is too low for the requested center gain; the shunt resistor was removed and the peak gain is 2*Q^2.")
        notes.append("MFB band-pass synthesis: R1 = 2Q/(C*w0) feedback, R3 = Q/(G*C*w0) input, R2 = Q/((2Q^2-G)*C*w0) shunt.")
        return _realization(inputs, stage, topology, gain, targets, {"C1": capacitor, "C2": capacitor}, notes)

    if inputs.kind is FilterKind.HIGHPASS:
        targets = {"R1": 1 / (3 * q * omega_0 * capacitor), "R2": 3 * q / (omega_0 * capacitor)}
        notes.append("Equal-C MFB high-pass: R1 = 1/(3Q*C*w0) to ground, R2 = 3Q/(C*w0) feedback, HF gain -1.")
        return _realization(
            inputs, stage, topology, 1.0, targets, {"C1": capacitor, "C2": capacitor, "C3": capacitor}, notes
        )

    # Low-pass with unity DC gain: the grounded capacitor must satisfy C1 >= 4*Q^2*(1 + H0)*C2.
    dc_gain = 1.0
    c2 = capacitor
    c1 = _next_e12_capacitor(4 * q * q * (1 + dc_gain) * c2)
    a = 1 + dc_gain
    b = omega_0 * c1 / q
    c = omega_0**2 * c1 * c2
    root = math.sqrt(max(b * b - 4 * a * c, 0.0))
    best: dict[str, float] | None = None
    for g2 in ((b + root) / (2 * a), (b - root) / (2 * a)):
        if g2 <= 0:
            continue
        g3 = c / g2
        candidate = {"R1": 1 / (dc_gain * g2), "R2": 1 / g2, "R3": 1 / g3}
        spread = max(candidate.values()) / min(candidate.values())
        if best is None or spread < max(best.values()) / min(best.values()):
            best = candidate
    notes.append("MFB low-pass with unity DC gain: C1 is the next E12 value above 8*Q^2*C2 and R1..R3 solve w0 and Q exactly.")
    return _realization(inputs, stage, topology, 1.0, best, {"C1": c1, "C2": c2}, notes)


def _synthesize_antoniou(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q
    base_r = 1 / (omega_0 * capacitor)
    targets = {"R": base_r, "Rq": q * base_r}
    capacitors = {"C1": capacitor}
    notes = [
        "Antoniou GIC resonator: L = C*R^2 with R = 1/(C*w0), Q set by Rq = Q*R, output buffered from the resonator node."
    ]
    gain = 1.0
    if inputs.kind is FilterKind.BANDSTOP:
        notch_ratio = 2 * math.pi * stage.zero_frequency_hz / omega_0
        if notch_ratio >= 1:
            # Zero above the poles: split the resonator capacitor between the input and ground.
            lifted = capacitor / notch_ratio**2
            capacitors["C2a"] = lifted
            if capacitor - lifted > capacitor * 1e-6:
                capacitors["C2b"] = capacitor - lifted
            targets["R5"] = base_r
        else:
            # Zero below the poles: drive the GIC ground resistor through a divider k = (wz/w0)^2.
            # Its DC gain is k, so the output amplifier restores 1/k; paired sections then pass unity.
            k = notch_ratio**2
            capacitors["C2a"] = capacitor
            targets["R5a"] = base_r / k
            targets["R5b"] = base_r / (1 - k)
            gain = 1 / k
        notes.append("Band-stop zero placed at the band center by splitting the lifted resonator elements.")
    else:
        capacitors["C2"] = capacitor
        targets["R5"] = base_r
        if inputs.kind is FilterKind.BANDPASS:
            gain = _bandpass_peak_gain_target(stage)
    if gain > 1 + 1e-6:
        targets["Rg"] = SALLEN_KEY_RG
        targets["Rf"] = SALLEN_KEY_RG * (gain - 1)
        notes.append(f"Output buffer turned into a non-inverting amplifier with gain {gain:.3f}.")
    return _realization(inputs, stage, topology, gain, targets, capacitors, notes)


def _synthesize_generic_placeholder(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    target_r = 1 / (omega_0 * capacitor)
    return _realization(inputs, stage, topology, 1.0, {"R1": target_r}, {"C1": capacitor}, ["Generic placeholder synthesis."])
