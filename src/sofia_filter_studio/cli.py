from __future__ import annotations

import argparse
from pathlib import Path

from .design import design_filter, format_result
from .models import Approximation, DesignInputs, FilterKind, FilterSpec, OpAmpModel, ResistorSeries, Topology
from .netlist import render_netlist


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Modern analog filter synthesis CLI for SOFIA.")
    parser.add_argument("--kind", choices=[item.value for item in FilterKind], required=True)
    parser.add_argument("--approx", choices=[item.value for item in Approximation], required=True)
    parser.add_argument("--ap", type=float, required=True, help="Passband ripple in dB, positive value.")
    parser.add_argument("--as", dest="a_stop", type=float, required=True, help="Stopband attenuation in dB.")
    parser.add_argument("--topology", choices=[item.value for item in Topology], default=Topology.SALLEN_KEY.value)
    parser.add_argument("--opamp", choices=[item.value for item in OpAmpModel], default=OpAmpModel.TL082.value)
    parser.add_argument("--cap", type=float, default=10e-9, help="Stage capacitor in farads.")
    parser.add_argument("--resistor-series", choices=[item.value for item in ResistorSeries], default=ResistorSeries.E24.value)
    parser.add_argument("--no-resistor-arrays", action="store_true", help="Disable series/parallel commercial resistor fitting.")
    parser.add_argument("--max-network-size", type=int, default=2, help="Maximum number of resistors per commercial network.")
    parser.add_argument("--no-auto-stage-capacitor", action="store_true", help="Disable automatic capacitor retuning per stage.")
    parser.add_argument("--fp", type=float, help="Passband edge for lowpass/highpass.")
    parser.add_argument("--fs", type=float, help="Stopband edge for lowpass/highpass.")
    parser.add_argument("--fp1", type=float, help="Lower passband edge for band filters.")
    parser.add_argument("--fp2", type=float, help="Upper passband edge for band filters.")
    parser.add_argument("--fs1", type=float, help="Lower stopband edge for band filters.")
    parser.add_argument("--fs2", type=float, help="Upper stopband edge for band filters.")
    parser.add_argument("--netlist-out", type=Path, help="Optional path to save the generated SPICE netlist.")
    return parser


def _build_spec(args: argparse.Namespace, kind: FilterKind) -> FilterSpec:
    if kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        if args.fp is None or args.fs is None:
            raise SystemExit("--fp and --fs are required for lowpass/highpass")
        return FilterSpec(passband_hz=args.fp, stopband_hz=args.fs)
    if None in {args.fp1, args.fp2, args.fs1, args.fs2}:
        raise SystemExit("--fp1 --fp2 --fs1 --fs2 are required for bandpass/bandstop")
    return FilterSpec(passband_hz=(args.fp1, args.fp2), stopband_hz=(args.fs1, args.fs2))


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    kind = FilterKind(args.kind)
    inputs = DesignInputs(
        kind=kind,
        approximation=Approximation(args.approx),
        spec=_build_spec(args, kind),
        passband_ripple_db=args.ap,
        stopband_attenuation_db=args.a_stop,
        topology=Topology(args.topology),
        opamp=OpAmpModel(args.opamp),
        stage_capacitor_f=args.cap,
        resistor_series=ResistorSeries(args.resistor_series),
        allow_resistor_arrays=not args.no_resistor_arrays,
        max_resistors_per_network=args.max_network_size,
        auto_stage_capacitor=not args.no_auto_stage_capacitor,
    )
    result = design_filter(inputs)
    print(format_result(result))
    if args.netlist_out:
        args.netlist_out.write_text(render_netlist(inputs, result), encoding="utf-8")
        print(f"Netlist written to {args.netlist_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
