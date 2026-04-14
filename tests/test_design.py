import math
import unittest

from sofia_filter_studio.design import design_filter
from sofia_filter_studio.models import Approximation, DesignInputs, FilterKind, FilterSpec, ResistorSeries, Topology
from sofia_filter_studio.netlist import render_netlist
from sofia_filter_studio.opamps import recommend_opamps
from sofia_filter_studio.resistors import fit_resistor_network


class DesignFilterTests(unittest.TestCase):
    def test_butterworth_lowpass_order_and_stage_count(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
        )
        result = design_filter(inputs)
        self.assertEqual(result.order, 8)
        self.assertEqual(len(result.stages), 4)
        self.assertTrue(math.isclose(result.epsilon, math.sqrt(10 ** 0.1 - 1), rel_tol=1e-9))

    def test_chebyshev_highpass_has_negative_real_poles(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.HIGHPASS,
            approximation=Approximation.CHEBYSHEV_I,
            spec=FilterSpec(passband_hz=2_000, stopband_hz=1_000),
            passband_ripple_db=1,
            stopband_attenuation_db=30,
        )
        result = design_filter(inputs)
        self.assertGreaterEqual(result.order, 1)
        self.assertTrue(all(pole.real < 0 for pole in result.poles))

    def test_bandpass_expands_prototype_order(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(1_000, 2_000), stopband_hz=(700, 2_600)),
            passband_ripple_db=1,
            stopband_attenuation_db=25,
        )
        result = design_filter(inputs)
        self.assertEqual(result.order % 2, 0)
        self.assertGreaterEqual(result.order, 2)
        self.assertGreaterEqual(len(result.stages), 1)

    def test_stage_realization_is_attached(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
            topology=Topology.SALLEN_KEY,
        )
        result = design_filter(inputs)
        self.assertIsNotNone(result.stages[0].realization)
        realization = result.stages[0].realization
        self.assertIn("R1", realization.resistor_networks)
        self.assertIn("C1", realization.capacitor_values_f)

    def test_resistor_array_can_improve_fit(self) -> None:
        single = fit_resistor_network("Rtest", 1_500, ResistorSeries.E12, allow_arrays=False, max_parts=1)
        with_array = fit_resistor_network("Rtest", 1_500, ResistorSeries.E12, allow_arrays=True, max_parts=2)
        self.assertLessEqual(with_array.relative_error, single.relative_error)
        self.assertIn(with_array.connection, {"single", "series", "parallel"})

    def test_legacy_opamp_recommendation_is_available(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=100_000, stopband_hz=200_000),
            passband_ripple_db=1,
            stopband_attenuation_db=20,
        )
        recommended = recommend_opamps(inputs)
        self.assertTrue(recommended)
        self.assertNotIn("LM324", [item.value for item in recommended])

    def test_impractical_resistor_range_adds_warning(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(1_000, 2_000), stopband_hz=(700, 2_600)),
            passband_ripple_db=1,
            stopband_attenuation_db=25,
            topology=Topology.MFB,
        )
        result = design_filter(inputs)
        self.assertTrue(any("below 10 ohm" in warning for warning in result.warnings))

    def test_auto_topology_selects_non_sallen_for_high_q_bandpass(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(1_000, 2_000), stopband_hz=(700, 2_600)),
            passband_ripple_db=1,
            stopband_attenuation_db=25,
            topology=Topology.AUTO,
        )
        result = design_filter(inputs)
        self.assertIn(result.stages[0].realization.topology, {Topology.MFB, Topology.TOW_THOMAS})

    def test_auto_stage_capacitor_can_change_from_requested_value(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(1_000, 2_000), stopband_hz=(700, 2_600)),
            passband_ripple_db=1,
            stopband_attenuation_db=25,
            topology=Topology.AUTO,
            stage_capacitor_f=10e-9,
            auto_stage_capacitor=True,
        )
        result = design_filter(inputs)
        self.assertTrue(
            any(
                abs(stage.realization.capacitor_values_f["C1"] - inputs.stage_capacitor_f) > 1e-30
                for stage in result.stages
            )
        )

    def test_netlist_cascades_stage_outputs(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
            topology=Topology.SALLEN_KEY,
        )
        result = design_filter(inputs)
        netlist = render_netlist(inputs, result)
        self.assertIn("VTIERRA VREF 0 2.5V", netlist)
        self.assertIn("RLOAD OUT 0 100k", netlist)
        self.assertIn("1", netlist)
        self.assertIn("Xao11", netlist)

    def test_netlist_uses_realized_stage_topology_under_auto(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(1_000, 2_000), stopband_hz=(700, 2_600)),
            passband_ripple_db=1,
            stopband_attenuation_db=25,
            topology=Topology.AUTO,
        )
        result = design_filter(inputs)
        netlist = render_netlist(inputs, result)
        self.assertIn("Xao", netlist)
        self.assertIn("VREF", netlist)

    def test_mfb_netlist_uses_legacyish_node_pattern(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(1_000, 2_000), stopband_hz=(700, 2_600)),
            passband_ripple_db=1,
            stopband_attenuation_db=25,
            topology=Topology.MFB,
        )
        result = design_filter(inputs)
        netlist = render_netlist(inputs, result)
        self.assertIn("Xao11", netlist)
        self.assertIn("c11 21 31", netlist)
        self.assertTrue("r31 10 21" in netlist or "r311 10 21" in netlist)


if __name__ == "__main__":
    unittest.main()
