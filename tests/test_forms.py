"""Form validation and the JSON view used by the web page."""

import json
import unittest

from sofia_filter_studio.forms import DEFAULT_FORM, FormError, design_view, design_view_json, options, read_form
from sofia_filter_studio.models import FilterKind, OpAmpModel, Topology


def form(**changes):
    return {**DEFAULT_FORM, **changes}


class ReadFormTests(unittest.TestCase):
    def test_defaults_give_a_low_pass(self) -> None:
        inputs = read_form(DEFAULT_FORM)
        self.assertIs(inputs.kind, FilterKind.LOWPASS)
        self.assertEqual(inputs.spec.passband_hz, 1000)
        self.assertAlmostEqual(inputs.stage_capacitor_f, 10e-9)
        self.assertIs(inputs.topology, Topology.AUTO)
        self.assertFalse(inputs.allow_resistor_arrays)

    def test_engineering_notation_and_band_edges(self) -> None:
        inputs = read_form(form(kind="bandpass", fp1="0.8k", fp2="1,2 kHz", opamp="LM324"))
        self.assertEqual(inputs.spec.passband_hz, (800, 1200))
        self.assertIs(inputs.opamp, OpAmpModel.LM324)

    def test_errors_name_the_fields_to_highlight(self) -> None:
        cases = [
            (form(fs="500"), ("fs",), "Fs debe ser mayor que Fp"),
            (form(kind="highpass"), ("fs",), "Fs debe ser menor que Fp"),
            (form(ap="0"), ("ap",), "rizo"),
            (form(**{"as": "0.5"}), ("as",), "atenuación"),
            (form(cap="abc"), ("cap",), "no es un número"),
            (form(kind="bandstop"), ("fp1", "fp2", "fs1", "fs2"), "Fp1 < Fs1 < Fs2 < Fp2"),
        ]
        for values, fields, text in cases:
            with self.subTest(fields=fields, text=text):
                with self.assertRaises(FormError) as caught:
                    read_form(values)
                self.assertEqual(caught.exception.fields, fields)
                self.assertIn(text.lower(), str(caught.exception).lower())


class DesignViewTests(unittest.TestCase):
    def test_valid_design_has_everything_the_page_shows(self) -> None:
        view = design_view(DEFAULT_FORM)
        self.assertTrue(view["ok"])
        self.assertEqual(view["headline"], "Pasa bajas Butterworth de orden 8")
        self.assertEqual(len(view["stages"]), 4)
        self.assertEqual(len(view["plot"]["freqs"]), len(view["plot"]["gains"]))
        self.assertIn(".subckt TL082", view["netlist"])
        self.assertTrue(view["filename"].endswith(".cir"))
        resistors = [part for stage in view["stages"] for part in stage["parts"] if part["value"].endswith("Ω")]
        self.assertTrue(resistors)
        self.assertTrue(all("+" not in part["detail"].split("(")[0] for part in resistors))

    def test_exact_values_netlist(self) -> None:
        commercial = design_view(DEFAULT_FORM)
        exact = design_view(form(exact_values=True))
        self.assertNotEqual(commercial["netlist"], exact["netlist"])
        self.assertTrue(exact["filename"].endswith("_valores_exactos.cir"))
        self.assertEqual(commercial["stages"], exact["stages"], "only the netlist changes")

    def test_margin_option_reaches_the_design(self) -> None:
        exact = dict(design_view(DEFAULT_FORM)["details"])
        margin = dict(design_view(form(margin=True))["details"])
        self.assertIn("exacta: Ap", exact["Atenuación en el borde de paso"])
        self.assertIn("margen", margin["Atenuación en el borde de paso"])
        self.assertTrue(read_form(form(margin=True)).design_margin)

    def test_invalid_form_returns_the_message(self) -> None:
        view = design_view(form(fs="500"))
        self.assertFalse(view["ok"])
        self.assertEqual(view["fields"], ["fs"])

    def test_json_round_trip_for_every_kind(self) -> None:
        bands = options()["default_bands"]
        for kind in ("lowpass", "highpass", "bandpass", "bandstop"):
            values = form(kind=kind, approximation="chebyshev")
            if kind == "highpass":
                values.update(fp="2k", fs="1k")
            if kind in bands:
                values.update(zip(("fp1", "fp2", "fs1", "fs2"), bands[kind]))
            with self.subTest(kind=kind):
                view = json.loads(design_view_json(json.dumps(values)))
                self.assertTrue(view["ok"], view.get("error"))
                self.assertTrue(view["headline"].endswith(f"de orden {len(view['poles'])}"))

    def test_options_cover_every_choice(self) -> None:
        data = options()
        self.assertEqual([item["value"] for item in data["kinds"]], ["lowpass", "highpass", "bandpass", "bandstop"])
        self.assertEqual(data["series"][0]["value"], "E96")
        self.assertEqual(set(data["hints"]), {"lowpass", "highpass", "bandpass", "bandstop"})
        json.dumps(data)


if __name__ == "__main__":
    unittest.main()
