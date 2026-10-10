import math
import unittest

from sofia_filter_studio.design import design_filter
from sofia_filter_studio.models import Approximation, DesignInputs, FilterKind, FilterSpec, Topology
from sofia_filter_studio.response import ideal_response_db
from sofia_filter_studio.units import format_quantity, format_resistor_value, parse_quantity


class UnitsTests(unittest.TestCase):
    def test_parse_engineering_notation(self) -> None:
        self.assertAlmostEqual(parse_quantity("10n", "F"), 10e-9)
        self.assertAlmostEqual(parse_quantity("0,1 uF", "F"), 0.1e-6)
        self.assertAlmostEqual(parse_quantity("1.5k"), 1500)
        self.assertAlmostEqual(parse_quantity("2 kHz", "Hz"), 2000)
        self.assertAlmostEqual(parse_quantity("1e-8", "F"), 1e-8)
        self.assertAlmostEqual(parse_quantity("4.7µ", "F"), 4.7e-6)

    def test_parse_rejects_garbage_and_wrong_units(self) -> None:
        with self.assertRaises(ValueError):
            parse_quantity("abc")
        with self.assertRaises(ValueError):
            parse_quantity("5 V", "F")

    def test_format_quantities(self) -> None:
        self.assertEqual(format_quantity(146266.05, "Ω"), "146.3 kΩ")
        self.assertEqual(format_quantity(1e-9, "F"), "1 nF")
        self.assertEqual(format_quantity(1000, "Hz"), "1 kHz")
        self.assertEqual(format_resistor_value(5_600_000), "5.6M")
        self.assertEqual(format_resistor_value(39), "39")


class ResponseTests(unittest.TestCase):
    def _response(self, inputs: DesignInputs, freqs: list[float]) -> list[float]:
        return ideal_response_db(inputs, design_filter(inputs), freqs)

    def test_butterworth_lowpass_passband_edge_is_exact(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.LOWPASS,
            approximation=Approximation.BUTTERWORTH,
            spec=FilterSpec(passband_hz=1_000, stopband_hz=2_000),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
        )
        dc, edge, stop = self._response(inputs, [1.0, 1_000.0, 2_000.0])
        self.assertAlmostEqual(dc, 0.0, delta=0.01)
        # Exactly -1 dB at the passband edge; order 8 has slack, so the stopband edge passes -40 dB.
        self.assertAlmostEqual(edge, -1.0, places=6)
        self.assertLess(stop, -40.5)

    def test_bandstop_has_a_notch_at_the_center(self) -> None:
        inputs = DesignInputs(
            kind=FilterKind.BANDSTOP,
            approximation=Approximation.CHEBYSHEV_I,
            spec=FilterSpec(passband_hz=(600, 1_600), stopband_hz=(900, 1_100)),
            passband_ripple_db=1,
            stopband_attenuation_db=40,
            topology=Topology.TOW_THOMAS,
        )
        center = math.sqrt(600 * 1_600)
        low, notch, high = self._response(inputs, [10.0, center, 100_000.0])
        self.assertGreater(low, -1.01)
        self.assertGreater(high, -1.01)
        self.assertLess(notch, -60.0)


if __name__ == "__main__":
    unittest.main()
