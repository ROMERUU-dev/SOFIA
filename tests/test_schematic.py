"""Board model, schematic drawing (checked net by net against the circuit) and bill of materials."""

import base64
import io
import itertools
import unittest
import xml.etree.ElementTree as ET
import zipfile

from sofia_filter_studio.board import BoardOptions, Mounting, bom_rows, build_board, net_name
from sofia_filter_studio.circuit import OPAMP, build_circuit
from sofia_filter_studio.design import design_filter
from sofia_filter_studio.forms import DEFAULT_FORM, export_file, schematic_view
from sofia_filter_studio.models import Approximation, DesignInputs, FilterKind, FilterSpec, OpAmpModel, Topology
from sofia_filter_studio.netlist import render_netlist
from sofia_filter_studio.schematic import build_schematic, check_connectivity, kicad_net_names, to_kicad, to_svg

SPECS = {
    FilterKind.LOWPASS: [FilterSpec(1000, 2000), FilterSpec(1000, 1300)],
    FilterKind.HIGHPASS: [FilterSpec(2000, 1000), FilterSpec(1300, 1000)],
    FilterKind.BANDPASS: [FilterSpec((800, 1200), (500, 2000)), FilterSpec((300, 3000), (100, 9000))],
    FilterKind.BANDSTOP: [FilterSpec((600, 1600), (900, 1100)), FilterSpec((400, 2500), (800, 1250))],
}
TOPOLOGIES = [Topology.AUTO, Topology.SALLEN_KEY, Topology.MFB, Topology.TOW_THOMAS, Topology.ANTONIOU]


def designs():
    """Every filter type, approximation and topology, with two specifications each."""
    for (kind, specs), approx, topology in itertools.product(SPECS.items(), Approximation, TOPOLOGIES):
        for index, spec in enumerate(specs):
            opamp = (OpAmpModel.TL082, OpAmpModel.LM324, OpAmpModel.UA741)[index % 3 if topology is Topology.AUTO else index]
            yield DesignInputs(kind, approx, spec, 1.0, 40.0, topology, opamp)


class CircuitModelTests(unittest.TestCase):
    def test_netlist_lists_every_part_of_the_model(self) -> None:
        inputs = DesignInputs(FilterKind.BANDSTOP, Approximation.CHEBYSHEV_I, FilterSpec((600, 1600), (900, 1100)), 1, 40, Topology.TOW_THOMAS)
        result = design_filter(inputs)
        netlist = render_netlist(inputs, result)
        for stage in build_circuit(inputs, result):
            for part in stage.parts:
                if part.kind == OPAMP:
                    plus, minus, out = part.nodes
                    self.assertIn(f"\n{part.name} {plus} {minus} VCC 0 {out} ", netlist)
                else:
                    self.assertIn(f"\n{part.name} {' '.join(part.nodes)} ", netlist)

    def test_roles_name_the_stage_ports(self) -> None:
        inputs = DesignInputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, FilterSpec(1000, 2000), 1, 40, Topology.SALLEN_KEY)
        stages = build_circuit(inputs, design_filter(inputs))
        first = stages[0].parts
        self.assertTrue(any(part.role[:1] == ("in",) for part in first))
        self.assertEqual(stages[0].input, "IN")
        self.assertEqual(stages[-1].output, "OUT")


class BoardTests(unittest.TestCase):
    def test_packages_and_virtual_ground(self) -> None:
        inputs = DesignInputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, FilterSpec(1000, 2000), 1, 40, Topology.AUTO)
        result = design_filter(inputs)
        board = build_board(inputs, result)
        sections = sum(1 for stage in board.stages for part in stage.parts if part.kind == OPAMP)
        packages = [component for component in board.components if component.symbol == "OPAMP"]
        self.assertEqual(len(packages), -(-(sections + 1) // 2))  # TL082 is dual
        purposes = [unit.purpose for unit in board.units]
        self.assertEqual(purposes.count("vref"), 1)
        nets = board.nets()
        self.assertGreaterEqual(len(nets["VREF"]), 3)
        self.assertIn(("C3", "1"), nets["IN"])
        self.assertIn(("C4", "1"), nets["OUT"])
        for package in packages:
            self.assertEqual(package.pins["8"], "VCC")
            self.assertEqual(package.pins["4"], "GND")

    def test_quad_package_for_lm324_and_spares_as_followers(self) -> None:
        inputs = DesignInputs(FilterKind.LOWPASS, Approximation.CHEBYSHEV_I, FilterSpec(1000, 2000), 1, 40, Topology.SALLEN_KEY, OpAmpModel.LM324)
        board = build_board(inputs, design_filter(inputs))
        package = board.component("U1")
        self.assertEqual(package.package.name, "quad")
        self.assertTrue(package.footprint.endswith("SOIC-14_3.9x8.7mm_P1.27mm"))
        spares = [unit for unit in board.units if unit.purpose == "spare"]
        for unit in spares:
            plus, minus, out = unit.component.package.sections[unit.unit - 1]
            self.assertEqual(unit.component.pins[plus], "VREF")
            self.assertEqual(unit.component.pins[minus], unit.component.pins[out])

    def test_through_hole_footprints(self) -> None:
        inputs = DesignInputs(FilterKind.HIGHPASS, Approximation.BUTTERWORTH, FilterSpec(2000, 1000), 1, 40, Topology.MFB)
        board = build_board(inputs, design_filter(inputs), BoardOptions(Mounting.THT))
        footprints = {component.footprint.split(":")[0] for component in board.components}
        self.assertLessEqual(footprints, {"Resistor_THT", "Capacitor_THT", "Package_DIP", "Connector_PinHeader_2.54mm", "MountingHole"})
        self.assertEqual(board.component("C1").symbol, "CP")

    def test_bill_of_materials_covers_every_part_once(self) -> None:
        inputs = DesignInputs(FilterKind.BANDPASS, Approximation.CHEBYSHEV_I, FilterSpec((800, 1200), (500, 2000)), 1, 40, Topology.AUTO)
        board = build_board(inputs, design_filter(inputs))
        rows = bom_rows(board)
        refs = [ref for row in rows for ref in row["Referencias"].split(", ")]
        expected = [component.ref for component in board.components if component.in_bom]
        self.assertEqual(sorted(refs), sorted(expected))
        self.assertEqual(sum(int(row["Cantidad"]) for row in rows), len(expected))

    def test_net_names(self) -> None:
        self.assertEqual(net_name("12"), "E2")
        self.assertEqual(net_name("23"), "N23")
        self.assertEqual(net_name("VREF"), "VREF")


class SchematicTests(unittest.TestCase):
    def test_drawing_matches_the_circuit_for_every_design(self) -> None:
        checked = 0
        for index, inputs in enumerate(designs()):
            mounting = Mounting.THT if index % 2 else Mounting.SMD
            board = build_board(inputs, design_filter(inputs), BoardOptions(mounting))
            report = check_connectivity(build_schematic(board))
            with self.subTest(kind=inputs.kind.value, approx=inputs.approximation.value, topology=inputs.topology.value):
                self.assertEqual(report.problems, [])
            checked += 1
        self.assertEqual(checked, 80)

    def test_svg_is_valid_xml(self) -> None:
        inputs = DesignInputs(FilterKind.BANDSTOP, Approximation.BUTTERWORTH, FilterSpec((600, 1600), (900, 1100)), 1, 40, Topology.ANTONIOU)
        schematic = build_schematic(build_board(inputs, design_filter(inputs)))
        for svg in (to_svg(schematic), to_svg(schematic, standalone=False), to_svg(schematic, standalone=False, inline=True)):
            root = ET.fromstring(svg)
            self.assertTrue(root.tag.endswith("svg"))
        self.assertIn('width="', to_svg(schematic))

    def test_kicad_file_is_well_formed(self) -> None:
        inputs = DesignInputs(FilterKind.LOWPASS, Approximation.CHEBYSHEV_I, FilterSpec(1000, 2000), 1, 40, Topology.AUTO)
        board = build_board(inputs, design_filter(inputs))
        text = to_kicad(build_schematic(board))
        depth = 0
        in_string = False
        escaped = False
        for char in text:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                self.assertGreaterEqual(depth, 0)
        self.assertEqual(depth, 0)
        self.assertTrue(text.startswith("(kicad_sch"))
        for component in board.components:
            self.assertIn(f'(property "Reference" "{component.ref}"', text)
        self.assertEqual(text, to_kicad(build_schematic(build_board(inputs, design_filter(inputs)))), "deterministic output")
        # The op amp drives the reference: a global label in KiCad, never a PWR_FLAG on an op amp output.
        self.assertIn('(global_label "VREF"', text)
        self.assertNotIn('lib_id "SOFIA:VREF', text)
        self.assertEqual(text.count('lib_id "SOFIA:PWR_FLAG"'), 2)

    def test_kicad_net_names_follow_kicad_rules(self) -> None:
        inputs = DesignInputs(FilterKind.BANDPASS, Approximation.BUTTERWORTH, FilterSpec((800, 1200), (500, 2000)), 1, 30, Topology.MFB)
        board = build_board(inputs, design_filter(inputs))
        names = kicad_net_names(build_schematic(board))
        self.assertEqual(set(names), set(board.nets()))
        self.assertEqual(names["GND"], "GND")
        self.assertEqual(names["VREF"], "VREF")
        self.assertEqual(names["OUT"], "/OUT")
        self.assertEqual(len(set(names.values())), len(names), "one KiCad name per net")
        for net, name in names.items():
            if net not in ("GND", "VCC", "VREF") and not name.startswith("/"):
                self.assertRegex(name, r"^Net-\([A-Z]+\d+[A-Z]?-")


class ExportTests(unittest.TestCase):
    def test_exports_from_the_form(self) -> None:
        form = dict(DEFAULT_FORM, kind="bandpass", approximation="chebyshev", mounting="tht")
        self.assertTrue(schematic_view(form)["svg"].startswith("<svg"))
        for what, suffix in (("kicad_sch", "_kicad.zip"), ("svg", "_esquematico.svg"), ("bom", "_materiales.csv")):
            exported = export_file(form, what)
            self.assertTrue(exported["ok"])
            self.assertTrue(exported["filename"].endswith(suffix))
        self.assertIn("Capacitor de película", export_file(form, "bom")["content"])
        project = zipfile.ZipFile(io.BytesIO(base64.b64decode(export_file(form, "kicad_sch")["base64"])))
        base = export_file(form, "svg")["filename"].removesuffix("_esquematico.svg")
        self.assertEqual(
            sorted(project.namelist()),
            sorted(f"{base}/{name}" for name in (f"{base}.kicad_pro", f"{base}.kicad_sch", "sym-lib-table", "SOFIA.kicad_sym")),
        )
        self.assertTrue(project.read(f"{base}/SOFIA.kicad_sym").startswith(b"(kicad_symbol_lib"))
        self.assertIn(f'(project "{base}"'.encode(), project.read(f"{base}/{base}.kicad_sch"))
        self.assertFalse(export_file(dict(form, fs1="900"), "bom")["ok"])


if __name__ == "__main__":
    unittest.main()
