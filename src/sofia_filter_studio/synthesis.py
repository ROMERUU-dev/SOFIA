from __future__ import annotations

import math

from .models import DesignInputs, FilterKind, ResistorNetwork, ResistorSeries, Stage, StageRealization, Topology
from .opamps import INPUT_BIAS_CURRENT_A, max_bias_safe_resistance
from .resistors import fit_resistor_network, fit_resistor_ratio

MIN_PRACTICAL_RESISTANCE = 100.0
MAX_PRACTICAL_RESISTANCE = 1_000_000.0
E12_CAPACITORS = (1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2)

# Gain-setting resistor shared by the non-inverting Sallen-Key stages.
SALLEN_KEY_RG = 10_000.0
SALLEN_KEY_MAX_GAIN_LP_HP = 2.9
SALLEN_KEY_MAX_GAIN_BP = 3.9
SALLEN_KEY_BP_SENSITIVE_Q = 5.0

# Realization notes that mean the stage deviates from the request; they are surfaced as warnings.
COMPROMISE_MARKERS = ("no puede realizar", "se limitó", "se recortó", "muy bajo", "muy sensible")

# Topologies that can realize each section type. Band-stop needs a finite transmission zero,
# which plain Sallen-Key and MFB sections cannot produce.
SUPPORTED_KINDS = {
    Topology.SALLEN_KEY: {FilterKind.LOWPASS, FilterKind.HIGHPASS, FilterKind.BANDPASS},
    Topology.MFB: {FilterKind.LOWPASS, FilterKind.HIGHPASS, FilterKind.BANDPASS},
    Topology.TOW_THOMAS: set(FilterKind),
    Topology.ANTONIOU: set(FilterKind),
}

TOPOLOGY_NAMES = {
    Topology.AUTO: "Automática",
    Topology.SALLEN_KEY: "Sallen-Key",
    Topology.MFB: "MFB",
    Topology.TOW_THOMAS: "Tow-Thomas",
    Topology.ANTONIOU: "Antoniou",
    Topology.OTA: "OTA",
}
KIND_NAMES = {
    FilterKind.LOWPASS: "pasa bajas",
    FilterKind.HIGHPASS: "pasa altas",
    FilterKind.BANDPASS: "pasa banda",
    FilterKind.BANDSTOP: "rechaza banda",
}


def synthesize_stage_realizations(inputs: DesignInputs, stages: list[Stage]) -> None:
    for stage in stages:
        stage.realization = synthesize_stage_realization(inputs, stage)


def practical_notes_for_stage(inputs: DesignInputs, stage: Stage) -> list[str]:
    realization = stage.realization
    if realization is None:
        return []
    notes = [
        f"Etapa {stage.index}: {note}"
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
            f"La etapa {stage.index} pide resistencias menores a 10 ohm. Un capacitor cercano a {base_cap / factor:.3e} F las llevaría a un rango práctico."
        )
    if max_target > MAX_PRACTICAL_RESISTANCE:
        factor = max(10, math.ceil(max_target / MAX_PRACTICAL_RESISTANCE))
        notes.append(
            f"La etapa {stage.index} pide resistencias mayores a 1 Mohm. Un capacitor cercano a {base_cap * factor:.3e} F reduciría ruido y sensibilidad."
        )
    worst_rounding = max((network.relative_error for network in realization.resistor_networks.values()), default=0.0)
    if worst_rounding > 0.01 and inputs.resistor_series is not ResistorSeries.E96:
        notes.append(
            f"La etapa {stage.index} redondea resistencias hasta {worst_rounding * 100:.1f} % con la serie {inputs.resistor_series.value}; con E96 (1 %) el filtro se apega mejor a la especificación."
        )
    bias_limit = max_bias_safe_resistance(inputs.opamp)
    if bias_limit < max_target <= MAX_PRACTICAL_RESISTANCE:
        offset_mv = max_target * INPUT_BIAS_CURRENT_A[inputs.opamp] * 1e3
        notes.append(
            f"La etapa {stage.index} usa resistencias de hasta {max_target:.0f} ohm; la corriente de polarización del {inputs.opamp.value} agrega unos {offset_mv:.0f} mV de offset en DC. Un capacitor más grande lo reduce."
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
            f"{TOPOLOGY_NAMES[topology]} no puede realizar una etapa {KIND_NAMES[inputs.kind]}; esta etapa usa Tow-Thomas."
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


def _capacitor_candidates(base: float) -> list[float]:
    """E12 capacitor values from base/100 to base*100 (the auto-tuning search space)."""
    first = math.floor(math.log10(base)) - 2
    return [value * 10 ** decade for decade in range(first, first + 5) for value in E12_CAPACITORS]


def _optimize_stage_realization(inputs: DesignInputs, stage: Stage, topology: Topology) -> StageRealization:
    # Every E12 capacitor value is tried, so the resistors can land close to commercial values.
    candidates = _capacitor_candidates(inputs.stage_capacitor_f)
    max_resistance = _max_resistance(inputs)
    scored: list[tuple[float, float, StageRealization]] = []
    for capacitor in candidates:
        realization = _synthesize_for_topology(inputs, stage, topology, capacitor)
        # Tiny preference for values near the requested capacitor when the fits are equally good.
        closeness = 0.01 * abs(math.log10(capacitor / inputs.stage_capacitor_f))
        scored.append((_score_realization(realization, max_resistance) + closeness, capacitor, realization))
    scored.sort(key=lambda item: item[0])
    _, capacitor, best = scored[0]
    if abs(capacitor - inputs.stage_capacitor_f) > 1e-30:
        best.notes.append(f"Capacitor de la etapa ajustado de {inputs.stage_capacitor_f:.3e} F a {capacitor:.3e} F.")
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
        ["Sección RC pasiva de primer orden con seguidor de voltaje."],
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
        ["Sección activa inversora de primer orden con ganancia unitaria, R1 = R2 = 1/(C*w0)."],
    )


def _gain_resistor_targets(inputs: DesignInputs, gain: float) -> dict[str, float]:
    """Rg/Rf targets of a non-inverting gain K = 1 + Rf/Rg.

    With single commercial resistors both are picked from the series so their ratio is accurate
    (Sallen-Key Q depends on K through 1/(3 - K)); with arrays Rg stays at 10 kohm.
    """
    if inputs.allow_resistor_arrays:
        return {"Rg": SALLEN_KEY_RG, "Rf": SALLEN_KEY_RG * (gain - 1)}
    # Keep the pair inside the op amp's bias-current budget (high-Ib parts want a few kohm).
    high = min(100e3, _max_resistance(inputs) / max(1.0, gain - 1))
    rg, _ = fit_resistor_ratio(gain - 1, inputs.resistor_series, low_ohms=min(1e3, high / 10), high_ohms=high)
    return {"Rg": rg, "Rf": rg * (gain - 1)}


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
        notes.append("Sallen-Key pasa banda de componentes iguales: K = 4 - sqrt(2)/Q y ganancia al centro K/(4 - K).")
        if q > SALLEN_KEY_BP_SENSITIVE_Q:
            notes.append(
                f"Con Q = {q:.2f} este Sallen-Key pasa banda es muy sensible a la tolerancia de las resistencias y al ancho de banda del opamp; MFB o Tow-Thomas son más robustos."
            )
    else:
        # Equal-R, equal-C low-pass/high-pass with the legacy gain/Q relation K = 3 - 1/Q.
        r_target = 1 / (omega_0 * capacitor)
        gain = 3 - 1 / q
        max_gain = SALLEN_KEY_MAX_GAIN_LP_HP
        targets = {"R1": r_target, "R2": r_target}
        notes.append("Sallen-Key de componentes iguales con la relación del legado Av = 3 - 1/Q.")
    if gain < 1:
        gain = 1.0
        notes.append("El Q pedido queda debajo de la región de Sallen-Key de componentes iguales; la etapa se limitó a ganancia 1 y su Q no será exacto.")
    if gain > max_gain:
        gain = max_gain
        notes.append(f"El Q pedido necesita una ganancia mayor a {max_gain}; la ganancia se recortó y el Q real será menor.")
    if gain - 1 > 1e-9:
        targets.update(_gain_resistor_targets(inputs, gain))
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
            notes.append(f"Divisor de entrada R1a/R1b (Thevenin = R1) que lleva la ganancia pico de {stage_gain:.2f} a {target:.3f}.")
            stage_gain = target
    return _realization(inputs, stage, topology, stage_gain, targets, {"C1": capacitor, "C2": capacitor}, notes)


def _synthesize_tow_thomas(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q
    base_r = 1 / (omega_0 * capacitor)
    targets = {"R": base_r, "Rq": q * base_r, "Rinv": base_r}
    capacitors = {"C1": capacitor, "C2": capacitor}
    notes = ["Tow-Thomas con las relaciones del legado R = 1/(C*w0) y Rq = Q*R."]
    if inputs.kind is FilterKind.LOWPASS:
        targets["R1"] = base_r
        notes.append("Salida pasa bajas en el segundo integrador, ganancia en DC -R/R1 = -1.")
    elif inputs.kind is FilterKind.BANDPASS:
        gain = _bandpass_peak_gain_target(stage)
        targets["R1"] = q * base_r / gain
        notes.append("Salida pasa banda en el integrador con pérdidas; R1 = Q*R/G = 1/(G*C*BW) fija la ganancia pico G.")
    elif inputs.kind is FilterKind.HIGHPASS:
        capacitors["Cff"] = capacitor
        notes.append("Pasa altas con alimentación directa capacitiva al integrador con pérdidas, ganancia en alta frecuencia -1.")
    else:
        notch_ratio = omega_0 / (2 * math.pi * stage.zero_frequency_hz)
        capacitors["Cff"] = capacitor
        targets["Rff"] = base_r * notch_ratio**2
        notes.append("Rechaza banda con alimentación directa Cff = C y Rff = R*(w0/wz)^2; la muesca queda al centro de la banda.")
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
            notes.append("El Q es muy bajo para la ganancia pedida; se quitó la resistencia a tierra y la ganancia pico es 2*Q^2.")
        notes.append("MFB pasa banda: R1 = 2Q/(C*w0) de realimentación, R3 = Q/(G*C*w0) de entrada, R2 = Q/((2Q^2-G)*C*w0) a tierra.")
        return _realization(inputs, stage, topology, gain, targets, {"C1": capacitor, "C2": capacitor}, notes)

    if inputs.kind is FilterKind.HIGHPASS:
        targets = {"R1": 1 / (3 * q * omega_0 * capacitor), "R2": 3 * q / (omega_0 * capacitor)}
        notes.append("MFB pasa altas de capacitores iguales: R1 = 1/(3Q*C*w0) a tierra, R2 = 3Q/(C*w0) de realimentación, ganancia en alta frecuencia -1.")
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
    notes.append("MFB pasa bajas con ganancia 1 en DC: C1 es el siguiente valor E12 arriba de 8*Q^2*C2 y R1..R3 dan w0 y Q exactos.")
    return _realization(inputs, stage, topology, 1.0, best, {"C1": c1, "C2": c2}, notes)


def _synthesize_antoniou(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    q = stage.q
    base_r = 1 / (omega_0 * capacitor)
    targets = {"R": base_r, "Rq": q * base_r}
    capacitors = {"C1": capacitor}
    notes = [
        "Resonador GIC de Antoniou: L = C*R^2 con R = 1/(C*w0), Q fijado por Rq = Q*R, salida reforzada desde el nodo resonante."
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
        notes.append("Cero de rechazo al centro de la banda repartiendo los elementos levantados del resonador.")
    else:
        capacitors["C2"] = capacitor
        targets["R5"] = base_r
        if inputs.kind is FilterKind.BANDPASS:
            gain = _bandpass_peak_gain_target(stage)
    if gain > 1 + 1e-6:
        targets.update(_gain_resistor_targets(inputs, gain))
        notes.append(f"El seguidor de salida se convirtió en amplificador no inversor con ganancia {gain:.3f}.")
    return _realization(inputs, stage, topology, gain, targets, capacitors, notes)


def _synthesize_generic_placeholder(inputs: DesignInputs, stage: Stage, topology: Topology, capacitor: float) -> StageRealization:
    omega_0 = 2 * math.pi * stage.natural_frequency_hz
    target_r = 1 / (omega_0 * capacitor)
    return _realization(inputs, stage, topology, 1.0, {"R1": target_r}, {"C1": capacitor}, ["Síntesis genérica de marcador."])
