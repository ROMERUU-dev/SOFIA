import math
import unittest

from sofia_filter_studio.design import design_filter
from sofia_filter_studio.models import (
    Approximation,
    DesignInputs,
    FilterKind,
    FilterSpec,
    OpAmpModel,
    ResistorSeries,
    Topology,
)
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

    def test_chebyshev_lowpass_uses_chebyshev_order_formula(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.CHEBYSHEV_I,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
        )
        result = design_filter(inputs)
        # acosh(sqrt((10^4 - 1)/(10^0.1 - 1))) / acosh(2) = 4.53 -> 5, not the Butterworth 8.
        self.assertEqual(result.order, 5)
        self.assertEqual([stage.order for stage in result.stages].count(1), 1)

    def test_odd_order_renders_first_order_section_for_every_topology(self) -> None:
        for topology in (Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU):
            for kind, fp, fs in ((FilterKind.LOWPASS, 1_000, 2_000), (FilterKind.HIGHPASS, 2_000, 1_000)):
                with self.subTest(topology=topology, kind=kind):
                    inputs = DesignInputs(
                        kind=kind,
                        approximation=Approximation.CHEBYSHEV_I,
                        spec=FilterSpec(passband_hz=fp, stopband_hz=fs),
                        passband_ripple_db=1,
                        stopband_attenuation_db=40,
                        topology=topology,
                    )
                    netlist = render_netlist(inputs, design_filter(inputs))
                    # Fifth order: two biquads plus the first-order stage 3 driving OUT.
                    self.assertIn("order=1", netlist)
                    self.assertIn("Xao13", netlist)
                    self.assertIn("VCC 0 OUT", netlist)

    def test_butterworth_bandpass_keeps_margin_inside_the_spec(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(800, 1_200), stopband_hz=(500, 2_000)),
            passband_ripple_db=1,
            stopband_attenuation_db=30,
        )
        result = design_filter(inputs)
        center = 2 * math.pi * math.sqrt(800 * 1_200)

        zeros_at_origin = len(result.poles) // 2

        def response(s: complex) -> complex:
            value = s**zeros_at_origin
            for pole in result.poles:
                value /= s - pole
            return value

        def gain_db(freq_hz: float) -> float:
            s = complex(0, 2 * math.pi * freq_hz)
            return 20 * math.log10(abs(response(s)) / abs(response(complex(0, center))))

        # The excess order is split: band edges inside the 1 dB ripple, stopband edges past 30 dB.
        for edge in (800, 1_200):
            self.assertLess(gain_db(edge), 0.0)
            self.assertGreater(gain_db(edge), -0.95)
        for edge in (500, 2_000):
            self.assertLess(gain_db(edge), -30.5)

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
            stage_capacitor_f=1e-3,
            auto_stage_capacitor=False,
        )
        result = design_filter(inputs)
        self.assertTrue(any("menores a 10 ohm" in warning for warning in result.warnings))

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
        # TL082 needs more than 5 V of rail: 15 V single supply with a 7.5 V virtual ground.
        self.assertIn("VTIERRA VREF 0 7.5V", netlist)
        self.assertIn("Vin IN 0 DC 7.5 AC 1", netlist)
        self.assertIn("RLOAD OUT 0 100k", netlist)
        self.assertIn("Xao11", netlist)
        self.assertIn("Xao12 32 42 VCC 0 12 TL082", netlist)
        # One commercial resistor per position by default (no series/parallel arrays).
        self.assertRegex(netlist, r"\nr32 11 22 \d")
        self.assertNotIn("_MID", netlist)

    def test_netlist_keeps_5v_rail_for_lm324(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
            opamp=OpAmpModel.LM324,
        )
        netlist = render_netlist(inputs, design_filter(inputs))
        self.assertIn("VTIERRA VREF 0 2.5V", netlist)
        self.assertIn("VCC VCC 0 DC 5", netlist)

    def test_netlist_uses_vendor_subckt_names(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.CHEBYSHEV_I,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
            opamp=OpAmpModel.LM7171,
        )
        netlist = render_netlist(inputs, design_filter(inputs))
        self.assertIn(" LM7171B/NS", netlist)
        self.assertNotIn(" LM7171\n", netlist)

    def test_nodeset_only_for_models_that_need_it(self) -> None:
        # TL082 and uA741 can latch at a rail without it; LM7171, LM6171 and LM6165 do not converge with it.
        for opamp, expected in ((OpAmpModel.TL082, True), (OpAmpModel.UA741, True), (OpAmpModel.LM7171, False), (OpAmpModel.LM6171, False), (OpAmpModel.LM6165, False)):
            inputs = DesignInputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, FilterSpec(1_000, 2_000), 1, 40, Topology.AUTO, opamp)
            self.assertEqual(".nodeset" in render_netlist(inputs, design_filter(inputs)), expected, opamp.value)

    def test_high_speed_opamps_avoid_tow_thomas_and_antoniou(self) -> None:
        specs = {
            FilterKind.LOWPASS: FilterSpec(1_000, 2_000),
            FilterKind.HIGHPASS: FilterSpec(2_000, 1_000),
            FilterKind.BANDPASS: FilterSpec((800, 1_200), (500, 2_000)),
        }
        for opamp in (OpAmpModel.LM7171, OpAmpModel.LM6171):
            for kind, spec in specs.items():
                for approximation in Approximation:
                    with self.subTest(opamp=opamp.value, kind=kind.value, approximation=approximation.value):
                        result = design_filter(DesignInputs(kind, approximation, spec, 1, 30, Topology.AUTO, opamp))
                        topologies = {stage.realization.topology for stage in result.stages if stage.realization is not None}
                        self.assertLessEqual(topologies, {Topology.SALLEN_KEY, Topology.MFB})
                        self.assertFalse(any("punto de operación" in warning for warning in result.warnings))
            bandstop = design_filter(DesignInputs(FilterKind.BANDSTOP, Approximation.BUTTERWORTH, FilterSpec((600, 1_600), (900, 1_100)), 1, 40, Topology.AUTO, opamp))
            self.assertTrue(any("TL082 o LM318" in warning for warning in bandstop.warnings))

    def test_inline_model_makes_a_self_contained_netlist(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
        )
        netlist = render_netlist(inputs, design_filter(inputs), inline_model=True)
        self.assertNotIn(".include", netlist)
        self.assertIn(".subckt TL082", netlist)
        self.assertLess(netlist.index(".ends"), netlist.index(".ac "))

    def test_ac_sweep_covers_the_specified_bands(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDSTOP,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=(600, 1_600), stopband_hz=(900, 1_100)),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
            topology=Topology.TOW_THOMAS,
        )
        netlist = render_netlist(inputs, design_filter(inputs))
        self.assertIn(".ac dec 100 60 16000", netlist)

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
        self.assertIn("Xao11 VREF 31 VCC 0", netlist)
        self.assertIn("c11 21 31", netlist)
        # The first stage must hang from the source node, not from a floating node.
        self.assertTrue("r31 IN 21" in netlist or "r31_1 IN 21" in netlist)


if __name__ == "__main__":
    unittest.main()
