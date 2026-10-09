"""Form handling shared by the user interfaces: choices, validation of the typed text and a ready-to-show
summary of a design. The desktop app uses the validation; the web page (Pyodide) uses all of it."""

from __future__ import annotations

import json
import time
from typing import Any

from . import __version__
from .design import design_filter
from .models import (
    Approximation,
    DesignInputs,
    DesignResult,
    FilterKind,
    FilterSpec,
    OpAmpModel,
    ResistorSeries,
    Topology,
)
from .board import BoardOptions, Mounting, bom_csv, build_board
from .netlist import render_netlist, supply_voltage_for
from .response import design_response, spec_bands
from .synthesis import KIND_NAMES, TOPOLOGY_NAMES
from .units import format_quantity, format_resistor_value, parse_quantity

KINDS = [
    (FilterKind.LOWPASS, "Pasa bajas"),
    (FilterKind.HIGHPASS, "Pasa altas"),
    (FilterKind.BANDPASS, "Pasa banda"),
    (FilterKind.BANDSTOP, "Rechaza banda"),
]
APPROXIMATIONS = [
    (Approximation.BUTTERWORTH, "Butterworth", "Respuesta plana"),
    (Approximation.CHEBYSHEV_I, "Chebyshev", "Corte más abrupto"),
]
TOPOLOGIES = [
    (Topology.AUTO, "Automática (recomendada)"),
    (Topology.SALLEN_KEY, "Sallen-Key"),
    (Topology.MFB, "MFB · realimentación múltiple"),
    (Topology.TOW_THOMAS, "Tow-Thomas · 3 opamps"),
    (Topology.ANTONIOU, "Antoniou · GIC"),
]
OPAMPS = [
    (OpAmpModel.TL082, "TL082 · JFET, uso general"),
    (OpAmpModel.LM324, "LM324 · funciona con 5 V"),
    (OpAmpModel.UA741, "uA741 · clásico"),
    (OpAmpModel.LM318, "LM318 · rápido"),
    (OpAmpModel.LM7171, "LM7171 · alta velocidad"),
    (OpAmpModel.LM6171, "LM6171 · alta velocidad"),
    (OpAmpModel.LM6164, "LM6164 · descompensado"),
    (OpAmpModel.LM6165, "LM6165 · descompensado"),
]
SERIES = [
    (ResistorSeries.E96, "E96 · 1 % (recomendada)"),
    (ResistorSeries.E48, "E48 · 2 %"),
    (ResistorSeries.E24, "E24 · 5 %"),
    (ResistorSeries.E12, "E12 · 10 %"),
]
SPEC_HINTS = {
    FilterKind.LOWPASS: "Pasa todo debajo de Fp y atenúa arriba de Fs (Fs > Fp).",
    FilterKind.HIGHPASS: "Pasa todo arriba de Fp y atenúa debajo de Fs (Fs < Fp).",
    FilterKind.BANDPASS: "Pasa entre Fp1 y Fp2; atenúa fuera de Fs1–Fs2 (Fs1 < Fp1 < Fp2 < Fs2).",
    FilterKind.BANDSTOP: "Atenúa entre Fs1 y Fs2; pasa fuera de Fp1–Fp2 (Fp1 < Fs1 < Fs2 < Fp2).",
}
DEFAULT_BANDS = {
    FilterKind.BANDPASS: ["800", "1.2k", "500", "2k"],
    FilterKind.BANDSTOP: ["600", "1.6k", "900", "1.1k"],
}
DEFAULT_FORM: dict[str, Any] = {
    "kind": FilterKind.LOWPASS.value,
    "approximation": Approximation.BUTTERWORTH.value,
    "fp": "1k",
    "fs": "2k",
    "fp1": DEFAULT_BANDS[FilterKind.BANDPASS][0],
    "fp2": DEFAULT_BANDS[FilterKind.BANDPASS][1],
    "fs1": DEFAULT_BANDS[FilterKind.BANDPASS][2],
    "fs2": DEFAULT_BANDS[FilterKind.BANDPASS][3],
    "ap": "1",
    "as": "40",
    "topology": Topology.AUTO.value,
    "opamp": OpAmpModel.TL082.value,
    "cap": "10n",
    "series": ResistorSeries.E96.value,
    "auto_cap": True,
    "mounting": Mounting.SMD.value,
}
MOUNTINGS = [
    (Mounting.SMD, "SMD · 0805 y SOIC"),
    (Mounting.THT, "Through-hole · axiales y DIP"),
]
UNITS = {"fp": "Hz", "fs": "Hz", "fp1": "Hz", "fp2": "Hz", "fs1": "Hz", "fs2": "Hz", "ap": "dB", "as": "dB", "cap": "F"}
LABELS = {"ap": "Rizo", "as": "Atenuación", "cap": "Capacitor"}


class FormError(ValueError):
    """Invalid form; ``fields`` names the inputs to highlight."""

    def __init__(self, message: str, *fields: str) -> None:
        super().__init__(message)
        self.fields = fields


def _value(form: dict[str, Any], name: str) -> float:
    try:
        return parse_quantity(str(form.get(name, "")), UNITS[name])
    except ValueError as exc:
        raise FormError(f"{LABELS.get(name, name.capitalize())}: {exc}", name) from None


def read_form(form: dict[str, Any]) -> DesignInputs:
    """Validate the text typed in a form and build the design inputs (messages in Spanish)."""
    kind = FilterKind(form.get("kind", FilterKind.LOWPASS))
    ripple, attenuation = _value(form, "ap"), _value(form, "as")
    if ripple <= 0:
        raise FormError("El rizo máximo debe ser mayor que cero.", "ap")
    if attenuation <= ripple:
        raise FormError("La atenuación mínima debe ser mayor que el rizo máximo.", "as")
    if kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        fp, fs = _value(form, "fp"), _value(form, "fs")
        if fp <= 0 or fs <= 0:
            raise FormError("Las frecuencias deben ser mayores que cero.", "fp", "fs")
        if kind is FilterKind.LOWPASS and fs <= fp:
            raise FormError("En un pasa bajas, Fs debe ser mayor que Fp.", "fs")
        if kind is FilterKind.HIGHPASS and fs >= fp:
            raise FormError("En un pasa altas, Fs debe ser menor que Fp.", "fs")
        spec = FilterSpec(passband_hz=fp, stopband_hz=fs)
    else:
        fp1, fp2 = _value(form, "fp1"), _value(form, "fp2")
        fs1, fs2 = _value(form, "fs1"), _value(form, "fs2")
        edges = ("fp1", "fp2", "fs1", "fs2")
        if min(fp1, fp2, fs1, fs2) <= 0:
            raise FormError("Las frecuencias deben ser mayores que cero.", *edges)
        if kind is FilterKind.BANDPASS and not fs1 < fp1 < fp2 < fs2:
            raise FormError("En un pasa banda se necesita Fs1 < Fp1 < Fp2 < Fs2.", *edges)
        if kind is FilterKind.BANDSTOP and not fp1 < fs1 < fs2 < fp2:
            raise FormError("En un rechaza banda se necesita Fp1 < Fs1 < Fs2 < Fp2.", *edges)
        spec = FilterSpec(passband_hz=(fp1, fp2), stopband_hz=(fs1, fs2))
    capacitor = _value(form, "cap")
    if capacitor <= 0:
        raise FormError("El capacitor debe ser mayor que cero.", "cap")
    return DesignInputs(
        kind=kind,
        approximation=Approximation(form.get("approximation", Approximation.BUTTERWORTH)),
        spec=spec,
        passband_ripple_db=ripple,
        stopband_attenuation_db=attenuation,
        topology=Topology(form.get("topology", Topology.AUTO)),
        opamp=OpAmpModel(form.get("opamp", OpAmpModel.TL082)),
        stage_capacitor_f=capacitor,
        resistor_series=ResistorSeries(form.get("series", ResistorSeries.E96)),
        allow_resistor_arrays=False,
        auto_stage_capacitor=bool(form.get("auto_cap", True)),
    )


def netlist_filename(inputs: DesignInputs, result: DesignResult) -> str:
    kind = KIND_NAMES[inputs.kind].replace(" ", "")
    return f"filtro_{kind}_{inputs.approximation.value}_orden{result.order}.cir"


def options() -> dict[str, Any]:
    """Choices and defaults of the form, for interfaces that build it themselves."""
    return {
        "version": __version__,
        "kinds": [{"value": k.value, "label": label} for k, label in KINDS],
        "approximations": [{"value": a.value, "label": label, "detail": detail} for a, label, detail in APPROXIMATIONS],
        "topologies": [{"value": t.value, "label": label} for t, label in TOPOLOGIES],
        "opamps": [{"value": o.value, "label": label} for o, label in OPAMPS],
        "series": [{"value": s.value, "label": label} for s, label in SERIES],
        "mountings": [{"value": m.value, "label": label} for m, label in MOUNTINGS],
        "hints": {k.value: hint for k, hint in SPEC_HINTS.items()},
        "default_bands": {k.value: values for k, values in DEFAULT_BANDS.items()},
        "defaults": DEFAULT_FORM,
    }


def _stage_view(stage) -> dict[str, Any]:
    realization = stage.realization
    metrics = [f"f0 {format_quantity(stage.natural_frequency_hz, 'Hz')}"]
    if stage.q is not None:
        metrics.append(f"Q {stage.q:.3f}")
    if realization.gain is not None:
        gain = realization.gain
        metrics.append(f"ganancia {abs(gain):.3g}" + (" (inversora)" if gain < 0 else ""))
    parts = [
        {"name": name, "value": format_quantity(value, "F"), "detail": ""}
        for name, value in realization.capacitor_values_f.items()
    ]
    for name, network in realization.resistor_networks.items():
        error = (network.realized_ohms - network.target_ohms) / network.target_ohms * 100
        detail = f"({error:+.2f} %)"
        if network.connection != "single":
            joiner = " ∥ " if network.connection == "parallel" else " + "
            detail = joiner.join(format_resistor_value(part) for part in network.parts_ohms) + "  " + detail
        parts.append({"name": name, "value": format_quantity(network.realized_ohms, "Ω"), "detail": detail})
    return {
        "title": f"Etapa {stage.index}",
        "topology": TOPOLOGY_NAMES[realization.topology],
        "order": "1er orden" if stage.order == 1 else "2º orden",
        "metrics": "   ·   ".join(metrics),
        "parts": parts,
    }


def design_view(form: dict[str, Any], points_per_decade: int = 160) -> dict[str, Any]:
    """Validate, design and return everything a page shows, as JSON-friendly data."""
    try:
        inputs = read_form(form)
        started = time.perf_counter()
        result = design_filter(inputs)
    except FormError as exc:
        return {"ok": False, "error": str(exc), "fields": list(exc.fields)}
    except ValueError as exc:
        return {"ok": False, "error": f"No se pudo diseñar con estos valores: {exc}", "fields": []}
    elapsed_ms = (time.perf_counter() - started) * 1e3

    kind_name = dict(KINDS)[inputs.kind]
    approx = next(name for value, name, _ in APPROXIMATIONS if value is inputs.approximation)
    topologies: list[str] = []
    for stage in result.stages:
        name = TOPOLOGY_NAMES[stage.realization.topology]
        if name not in topologies:
            topologies.append(name)
    supply = supply_voltage_for(inputs)
    stages, warnings = len(result.stages), len(result.warnings)
    chips = [
        {"text": f"{stages} etapa{'s' if stages != 1 else ''}", "tone": "info"},
        {"text": " + ".join(topologies), "tone": "info"},
        {"text": f"{inputs.opamp.value} · {supply:g} V", "tone": "info"},
        {"text": f"{warnings} aviso{'s' if warnings != 1 else ''}", "tone": "warn"}
        if warnings
        else {"text": "Sin avisos", "tone": "ok"},
    ]

    freqs, gains = design_response(inputs, result, points_per_decade=points_per_decade)
    passbands, stopbands = spec_bands(inputs, freqs[0], freqs[-1])

    summary = result.summary
    ripple, attenuation = summary["design_ripple_db"], summary["design_attenuation_db"]
    details = [
        ["Orden del filtro", str(result.order)],
        ["Rizo del diseño", f"{ripple:.3f} dB  (margen {inputs.passband_ripple_db - ripple:.3f} dB)"],
        ["Atenuación del diseño", f"{attenuation:.2f} dB  (margen {attenuation - inputs.stopband_attenuation_db:.2f} dB)"],
        ["Épsilon (rizo pedido)", f"{result.epsilon:.5f}"],
        ["Selectividad", f"{summary['ratio']:.4g}"],
        ["Alimentación", f"{supply:g} V, tierra virtual en {supply / 2:g} V"],
    ]
    if "center_frequency_hz" in summary:
        details.insert(2, ["Frecuencia central", format_quantity(summary["center_frequency_hz"], "Hz")])
        details.insert(3, ["Ancho de banda", format_quantity(summary["bandwidth_hz"], "Hz")])
    details.append(["Opamps adecuados a esta frecuencia", ", ".join(summary.get("recommended_opamps", [])) or "ninguno"])

    return {
        "ok": True,
        "headline": f"{kind_name} {approx} de orden {result.order}",
        "chips": chips,
        "plot": {
            "freqs": freqs,
            "gains": gains,
            "passbands": passbands,
            "stopbands": stopbands,
            "ripple_db": inputs.passband_ripple_db,
            "attenuation_db": inputs.stopband_attenuation_db,
        },
        "stages": [_stage_view(stage) for stage in result.stages],
        "warnings": list(result.warnings),
        "details": details,
        "poles": [[f"{pole.real:,.2f}", f"{pole.imag:+,.2f} j"] for pole in result.poles],
        "netlist": render_netlist(inputs, result, inline_model=True),
        "filename": netlist_filename(inputs, result),
        "elapsed_ms": elapsed_ms,
    }


def design_view_json(form_json: str) -> str:
    """JSON in, JSON out: the web worker calls this through Pyodide."""
    return json.dumps(design_view(json.loads(form_json)), ensure_ascii=False)


def board_options(form: dict[str, Any]) -> BoardOptions:
    return BoardOptions(Mounting(form.get("mounting", Mounting.SMD)))


def _board(form: dict[str, Any]):
    inputs = read_form(form)
    result = design_filter(inputs)
    return inputs, result, build_board(inputs, result, board_options(form))


def schematic_view(form: dict[str, Any]) -> dict[str, Any]:
    """Schematic SVG (cropped to the drawing) for the Esquemático tab."""
    from .schematic import build_schematic, to_svg

    try:
        _, _, board = _board(form)
    except (FormError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    schematic = build_schematic(board)
    return {"ok": True, "svg": to_svg(schematic, standalone=False), "paper": schematic.paper}


EXPORTS = {
    # KiCad projects (ZIP): the schematic alone, or the schematic with the routed board.
    "kicad_sch": ("_kicad.zip", "application/zip"),
    "svg": ("_esquematico.svg", "image/svg+xml"),
    "bom": ("_materiales.csv", "text/csv"),
    "kicad_pcb": ("_kicad.zip", "application/zip"),
    "gerber": ("_gerber.zip", "application/zip"),
    "cpl": ("_posiciones.csv", "text/csv"),
}
_PCB_CACHE: dict[str, Any] = {}


def _pcb(form: dict[str, Any]):
    """Board, schematic and routed PCB of a form; the last one is kept so exports do not re-route."""
    from .pcb import build_pcb
    from .schematic import build_schematic

    key = json.dumps({name: form.get(name) for name in DEFAULT_FORM}, sort_keys=True)
    if key not in _PCB_CACHE:
        inputs, result, board = _board(form)
        schematic = build_schematic(board)
        _PCB_CACHE.clear()
        _PCB_CACHE[key] = (inputs, result, board, build_pcb(board, schematic))
    return _PCB_CACHE[key]


def pcb_view(form: dict[str, Any], side: str = "top") -> dict[str, Any]:
    """Routed board preview and its status, for the PCB tab."""
    from .pcb import to_svg

    try:
        _, _, board, pcb = _pcb(form)
    except (FormError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    packages = sum(1 for component in board.components if component.symbol == "OPAMP")
    return {
        "ok": True,
        "svg": to_svg(pcb, side),
        "width": round(pcb.width, 1),
        "height": round(pcb.height, 1),
        "parts": sum(1 for component in board.components if component.in_bom),
        "packages": packages,
        "vias": len(pcb.vias),
        "unrouted": len(pcb.unrouted),
        "problems": pcb.problems[:20],
        "smd": board.options.mounting is Mounting.SMD,
    }


def export_file(form: dict[str, Any], what: str) -> dict[str, Any]:
    """A file to download (see EXPORTS); binary files come as base64."""
    import base64

    from .kicad import project_zip
    from .schematic import build_schematic, to_svg

    try:
        inputs, result, board = _board(form)
    except (FormError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    suffix, mime = EXPORTS[what]
    base = netlist_filename(inputs, result).removesuffix(".cir")
    data = None
    if what in ("kicad_pcb", "gerber", "cpl"):
        from .pcbfiles import gerber_zip, placement_csv

        pcb = _pcb(form)[3]
        if what == "gerber":
            data = gerber_zip(pcb, base)
        elif what == "kicad_pcb":
            data = project_zip(build_schematic(board), base, pcb)
        else:
            content = placement_csv(pcb)
    elif what == "bom":
        content = bom_csv(board)
    elif what == "kicad_sch":
        data = project_zip(build_schematic(board), base)
    else:
        content = to_svg(build_schematic(board))
    if data is not None:
        return {"ok": True, "filename": base + suffix, "mime": mime, "base64": base64.b64encode(data).decode("ascii")}
    return {"ok": True, "filename": base + suffix, "mime": mime, "content": content}


def schematic_view_json(form_json: str) -> str:
    return json.dumps(schematic_view(json.loads(form_json)), ensure_ascii=False)


def export_file_json(form_json: str, what: str) -> str:
    return json.dumps(export_file(json.loads(form_json), what), ensure_ascii=False)


def pcb_view_json(form_json: str, side: str = "top") -> str:
    return json.dumps(pcb_view(json.loads(form_json), side), ensure_ascii=False)
