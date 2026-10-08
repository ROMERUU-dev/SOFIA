"""End-to-end checks: generated netlists are simulated with SPICE and compared against the spec.

Skipped when no simulator is available (set SOFIA_SPICE to LTspice or ngspice to enable them).
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import simulate_case  # noqa: E402

from sofia_filter_studio.design import design_filter  # noqa: E402
from sofia_filter_studio.models import (  # noqa: E402
    Approximation,
    DesignInputs,
    FilterKind,
    FilterSpec,
    OpAmpModel,
    Topology,
)
from sofia_filter_studio.netlist import render_netlist  # noqa: E402

SIMULATOR = simulate_case.find_simulator()
PASSING = {"cumple", "cumple_con_tolerancia"}

SPECS = {
    FilterKind.LOWPASS: {"fp": 1_000, "fs": 2_000},
    FilterKind.HIGHPASS: {"fp": 2_000, "fs": 1_000},
    FilterKind.BANDPASS: {"fp1": 800, "fp2": 1_200, "fs1": 500, "fs2": 2_000},
    FilterKind.BANDSTOP: {"fp1": 600, "fp2": 1_600, "fs1": 900, "fs2": 1_100},
}


def _inputs(kind: FilterKind, approximation: Approximation, topology: Topology, opamp: OpAmpModel) -> tuple[DesignInputs, dict]:
    edges = SPECS[kind]
    if kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}:
        spec = FilterSpec(passband_hz=edges["fp"], stopband_hz=edges["fs"])
    else:
        spec = FilterSpec(passband_hz=(edges["fp1"], edges["fp2"]), stopband_hz=(edges["fs1"], edges["fs2"]))
    a_stop = 30 if kind is FilterKind.BANDPASS else 40
    inputs = DesignInputs(
        kind=kind,
        approximation=approximation,
        spec=spec,
        passband_ripple_db=1,
        stopband_attenuation_db=a_stop,
        topology=topology,
        opamp=opamp,
    )
    return inputs, {"kind": kind.value, "ap": 1, "as": a_stop, **edges}


@unittest.skipIf(SIMULATOR is None, "no SPICE simulator found")
class SimulatedResponseTests(unittest.TestCase):
    def _simulate(self, inputs: DesignInputs, spec: dict, ideal: bool) -> dict:
        with tempfile.TemporaryDirectory(prefix="sofia_test_") as tmp:
            path = Path(tmp) / "filter.cir"
            path.write_text(render_netlist(inputs, design_filter(inputs), path), encoding="utf-8")
            return simulate_case.simulate_netlist(SIMULATOR, path, spec, "OUT", 0.15, 0.5, ideal_opamp=ideal)

    def test_every_topology_and_kind_meets_spec_with_ideal_opamps(self) -> None:
        for topology in (Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU, Topology.AUTO):
            for kind in FilterKind:
                for approximation in Approximation:
                    with self.subTest(topology=topology.value, kind=kind.value, approximation=approximation.value):
                        inputs, spec = _inputs(kind, approximation, topology, OpAmpModel.TL082)
                        result = self._simulate(inputs, spec, ideal=True)
                        self.assertIn(result["verdict"], PASSING, result)

    def test_real_opamp_models_bias_and_meet_spec(self) -> None:
        # One low-pass per bundled model: catches wrong subcircuit names, bad rails and bias-current offsets.
        for opamp in OpAmpModel:
            with self.subTest(opamp=opamp.value):
                inputs, spec = _inputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, Topology.SALLEN_KEY, opamp)
                result = self._simulate(inputs, spec, ideal=False)
                self.assertIn(result["verdict"], PASSING, result)

    def test_bandpass_cascade_has_unity_gain_at_center(self) -> None:
        for topology in (Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU):
            with self.subTest(topology=topology.value):
                inputs, spec = _inputs(FilterKind.BANDPASS, Approximation.BUTTERWORTH, topology, OpAmpModel.TL082)
                result = self._simulate(inputs, spec, ideal=True)
                self.assertAlmostEqual(result["passband_gain_db"], 0.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
