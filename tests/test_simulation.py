"""End-to-end checks: generated netlists are simulated with SPICE and compared against the spec.

Skipped when no simulator is available (set SOFIA_SPICE to LTspice or ngspice to enable them).
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import simulate  # noqa: E402

from sofia_filter_studio.design import design_filter  # noqa: E402
from sofia_filter_studio.models import (  # noqa: E402
    Approximation,
    DesignInputs,
    FilterKind,
    FilterSpec,
    OpAmpModel,
    ResistorSeries,
    Topology,
)
from sofia_filter_studio.netlist import render_netlist  # noqa: E402

SIMULATOR = simulate.find_simulator()
PASSING = {"cumple", "cumple_con_tolerancia"}

SPECS = {
    FilterKind.LOWPASS: {"fp": 1_000, "fs": 2_000},
    FilterKind.HIGHPASS: {"fp": 2_000, "fs": 1_000},
    FilterKind.BANDPASS: {"fp1": 800, "fp2": 1_200, "fs1": 500, "fs2": 2_000},
    FilterKind.BANDSTOP: {"fp1": 600, "fp2": 1_600, "fs1": 900, "fs2": 1_100},
}


def _inputs(
    kind: FilterKind, approximation: Approximation, topology: Topology, opamp: OpAmpModel, margin: bool = False
) -> tuple[DesignInputs, dict]:
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
        resistor_series=ResistorSeries.E96,
        design_margin=margin,
    )
    return inputs, {"kind": kind.value, "ap": 1, "as": a_stop, **edges}


@unittest.skipIf(SIMULATOR is None, "no SPICE simulator found")
class SimulatedResponseTests(unittest.TestCase):
    def _simulate(self, inputs: DesignInputs, spec: dict, ideal: bool, exact: bool = False) -> dict:
        with tempfile.TemporaryDirectory(prefix="sofia_test_") as tmp:
            path = Path(tmp) / "filter.cir"
            path.write_text(render_netlist(inputs, design_filter(inputs), path, exact_values=exact), encoding="utf-8")
            return simulate.simulate_netlist(SIMULATOR, path, spec, "OUT", 0.15, 0.5, ideal_opamp=ideal)

    def test_exact_values_meet_the_spec_exactly_with_ideal_opamps(self) -> None:
        # The textbook design sits on Ap at the passband edge: Ap of ripple, at least As. The 200-point-
        # per-decade sweep, interpolated at the sharp band edges, reads up to ~0.04 dB more ripple; the
        # exact match with the design is checked by test_netlists_realize_the_designed_transfer_function.
        for topology in (Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU, Topology.AUTO):
            for kind in FilterKind:
                for approximation in Approximation:
                    with self.subTest(topology=topology.value, kind=kind.value, approximation=approximation.value):
                        inputs, spec = _inputs(kind, approximation, topology, OpAmpModel.TL082)
                        result = self._simulate(inputs, spec, ideal=True, exact=True)
                        self.assertAlmostEqual(result["passband_ripple_db"], 1.0, delta=0.05, msg=result)
                        self.assertGreaterEqual(result["stopband_attenuation_db"], spec["as"], result)

    def test_commercial_values_meet_the_spec_with_the_margin_option(self) -> None:
        # With the margin option the E96 values (one resistor per position) still meet the spec.
        for topology in (Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU, Topology.AUTO):
            for kind in FilterKind:
                for approximation in Approximation:
                    with self.subTest(topology=topology.value, kind=kind.value, approximation=approximation.value):
                        inputs, spec = _inputs(kind, approximation, topology, OpAmpModel.TL082, margin=True)
                        result = self._simulate(inputs, spec, ideal=True)
                        self.assertIn(result["verdict"], PASSING, result)

    def test_netlists_realize_the_designed_transfer_function(self) -> None:
        # Exact (non-rounded) values and ideal op amps: the simulated circuit must match the poles/zeros
        # the design computed, which catches any wrong connection or formula in the netlist writer.
        from sofia_filter_studio.response import ideal_response_db

        for topology in (Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU):
            for kind in FilterKind:
                for approximation in Approximation:
                    with self.subTest(topology=topology.value, kind=kind.value, approximation=approximation.value):
                        inputs, spec = _inputs(kind, approximation, topology, OpAmpModel.TL082)
                        result = design_filter(inputs)
                        with tempfile.TemporaryDirectory(prefix="sofia_test_") as tmp:
                            path = Path(tmp) / "filter.cir"
                            path.write_text(render_netlist(inputs, result, path, exact_values=True), encoding="utf-8")
                            freqs, simulated = simulate.simulated_response(SIMULATOR, path, spec, ideal_opamp=True)
                        ideal = ideal_response_db(inputs, result, freqs)
                        passbands, _ = simulate.spec_bands(spec)
                        reference = max(g for f, g in zip(freqs, simulated) if any(lo <= f <= hi for lo, hi in passbands))
                        worst = max(abs((s - reference) - i) for s, i in zip(simulated, ideal) if i > -60)
                        self.assertLess(worst, 0.05)

    def test_real_opamp_models_bias_and_meet_spec(self) -> None:
        # One low-pass per bundled model: catches wrong subcircuit names, bad rails and bias-current offsets.
        for opamp in OpAmpModel:
            with self.subTest(opamp=opamp.value):
                inputs, spec = _inputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, Topology.SALLEN_KEY, opamp, margin=True)
                result = self._simulate(inputs, spec, ideal=False)
                self.assertIn(result["verdict"], PASSING, result)

    def test_high_speed_opamps_simulate_with_the_automatic_topology(self) -> None:
        # With the LM7171/LM6171 macro-models LTspice only finishes without .nodeset and without
        # Tow-Thomas or Antoniou sections, which is what SOFIA writes for them.
        for opamp in (OpAmpModel.LM7171, OpAmpModel.LM6171):
            for kind in (FilterKind.LOWPASS, FilterKind.BANDPASS):
                with self.subTest(opamp=opamp.value, kind=kind.value):
                    inputs, spec = _inputs(kind, Approximation.CHEBYSHEV_I, Topology.AUTO, opamp, margin=True)
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
