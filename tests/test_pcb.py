"""PCB: placement, routing checked by the design-rule check, and the manufacturing files."""

import base64
import io
import json
import re
import unittest
import zipfile

from sofia_filter_studio.board import BoardOptions, Mounting, build_board
from sofia_filter_studio.design import design_filter
from sofia_filter_studio.footprints import FOOTPRINTS
from sofia_filter_studio.forms import DEFAULT_FORM, export_file, pcb_view
from sofia_filter_studio.geometry import Box, Capsule, circle, distance
from sofia_filter_studio.models import Approximation, DesignInputs, FilterKind, FilterSpec, OpAmpModel, Topology
from sofia_filter_studio.pcb import build_pcb, check_design_rules
from sofia_filter_studio.pcbfiles import gerber_files, gerber_zip, placement_csv, to_kicad_pcb
from sofia_filter_studio.router import Router, Rules, Terminal
from sofia_filter_studio.schematic import build_schematic, kicad_net_names

DESIGNS = [
    DesignInputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, FilterSpec(1000, 2000), 1, 40, Topology.AUTO),
    DesignInputs(FilterKind.HIGHPASS, Approximation.CHEBYSHEV_I, FilterSpec(2000, 1000), 1, 40, Topology.MFB),
    DesignInputs(FilterKind.BANDPASS, Approximation.CHEBYSHEV_I, FilterSpec((800, 1200), (500, 2000)), 1, 40, Topology.AUTO),
    DesignInputs(FilterKind.BANDSTOP, Approximation.BUTTERWORTH, FilterSpec((600, 1600), (900, 1100)), 1, 40, Topology.ANTONIOU),
    DesignInputs(FilterKind.LOWPASS, Approximation.CHEBYSHEV_I, FilterSpec(1000, 2000), 1, 40, Topology.SALLEN_KEY, OpAmpModel.LM324),
]


class GeometryTests(unittest.TestCase):
    def test_distances(self) -> None:
        self.assertAlmostEqual(distance(circle(0, 0, 1), circle(3, 0, 1)), 1.0)
        self.assertAlmostEqual(distance(Box(0, 0, 1, 1), Box(2, 0, 3, 1)), 1.0)
        self.assertAlmostEqual(distance(Capsule(0, 0, 10, 0, 0.5), Box(4, 1, 5, 2)), 0.5)
        self.assertEqual(distance(Capsule(0, 0, 10, 10, 0.1), Capsule(0, 10, 10, 0, 0.1)), 0.0)


class RouterTests(unittest.TestCase):
    def test_routes_around_an_obstacle(self) -> None:
        rules = Rules()
        terminals = [
            Terminal(("A", "1"), "N1", circle(5, 10, 0.8), (0, 1), 5, 10),
            Terminal(("B", "1"), "N1", circle(25, 10, 0.8), (0, 1), 25, 10),
        ]
        wall = [Box(14, 2, 16, 18)]
        result = Router((0, 0, 30.48, 20.32), terminals, wall, rules).route()
        self.assertEqual(result.unrouted, [])
        self.assertTrue(result.tracks)
        for track in result.tracks:
            self.assertGreaterEqual(distance(Capsule(track.x1, track.y1, track.x2, track.y2, track.width / 2), wall[0]), rules.clearance - 1e-6)


class PcbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.boards = []
        for index, inputs in enumerate(DESIGNS):
            for mounting in Mounting:
                board = build_board(inputs, design_filter(inputs), BoardOptions(mounting))
                cls.boards.append((inputs, mounting, build_pcb(board)))

    def test_every_board_is_routed_without_rule_errors(self) -> None:
        for inputs, mounting, pcb in self.boards:
            with self.subTest(kind=inputs.kind.value, topology=inputs.topology.value, mounting=mounting.value):
                self.assertEqual(pcb.unrouted, [])
                self.assertEqual(pcb.problems, [])
                self.assertLess(pcb.width, 220)

    def test_parts_keep_room_for_their_references(self) -> None:
        # Snapping to the grid must not eat the gap left above each part for its silkscreen reference.
        for inputs, mounting, pcb in self.boards:
            gap = 1.4 if mounting is Mounting.SMD else 1.6
            parts = [item for item in pcb.footprints if item.component.symbol != "HOLE"]
            for index, a in enumerate(parts):
                ax1, ay1, ax2, ay2 = a.courtyard(gap / 2)
                for b in parts[index + 1 :]:
                    bx1, by1, bx2, by2 = b.courtyard(gap / 2)
                    overlap = min(min(ax2, bx2) - max(ax1, bx1), min(ay2, by2) - max(ay1, by1))
                    self.assertLessEqual(overlap, 1e-6, f"{a.component.ref} y {b.component.ref} ({inputs.kind.value}, {mounting.value})")

    def test_no_connect_pins_of_single_op_amps(self) -> None:
        inputs = DesignInputs(FilterKind.LOWPASS, Approximation.BUTTERWORTH, FilterSpec(1000, 2000), 1, 40, Topology.SALLEN_KEY, OpAmpModel.UA741)
        pcb = build_pcb(build_board(inputs, design_filter(inputs)))
        text = to_kicad_pcb(pcb)
        # KiCad gives each no-connect pin its own net; the pads carry it so the board matches the schematic.
        self.assertIn('(net "unconnected-(U1B-NC-Pad1)")', re.sub(r"\(net \d+ ", "(net ", text))

    def test_rule_check_catches_a_short(self) -> None:
        _, _, pcb = self.boards[0]
        track = pcb.tracks[0]
        other = next(t for t in pcb.tracks if t.net != track.net and t.layer == track.layer)
        pcb.tracks.append(type(track)(track.layer, track.x1, track.y1, other.x1, other.y1, track.net, track.width))
        try:
            self.assertTrue(any("separación" in problem for problem in check_design_rules(pcb)))
        finally:
            pcb.tracks.pop()

    def test_footprints_exist_for_every_part(self) -> None:
        for _, _, pcb in self.boards:
            for component in pcb.board.components:
                self.assertIn(component.footprint, FOOTPRINTS)

    def test_gerber_files(self) -> None:
        _, mounting, pcb = self.boards[2]
        files = gerber_files(pcb, "placa")
        expected = {"F_Cu.gtl", "B_Cu.gbl", "F_Mask.gts", "B_Mask.gbs", "F_Silkscreen.gto", "Edge_Cuts.gm1", "PTH.drl", "NPTH.drl", "F_Paste.gtp"}
        self.assertEqual({name.split("-", 1)[1] for name in files}, expected)
        for name, text in files.items():
            if name.endswith(".drl"):
                self.assertTrue(text.startswith("M48") and text.rstrip().endswith("M30"))
                tools = set(re.findall(r"^T(\d+)C", text, re.M))
                used = set(re.findall(r"^T(\d+)$", text, re.M)) - {"0"}
                self.assertEqual(tools, used)
                continue
            self.assertTrue(text.rstrip().endswith("M02*"), name)
            defined = set(re.findall(r"%ADD(\d+)", text))
            used = set(re.findall(r"^D(\d+)\*$", text, re.M))
            self.assertLessEqual(used, defined, name)
            self.assertIn("%FSLAX46Y46*%", text)
        # The bottom copper carries the ground plane: a region and clear polarity around other nets.
        bottom = files["placa-B_Cu.gbl"]
        self.assertIn("G36*", bottom)
        self.assertIn("%LPC*%", bottom)
        holes = len(re.findall(r"^X", files["placa-PTH.drl"], re.M))
        self.assertEqual(holes, len(pcb.vias) + sum(1 for item in pcb.footprints for pad, *_ in item.pads() if pad.tht and pad.plated))

    def test_gerber_zip_and_placement(self) -> None:
        _, _, pcb = self.boards[0]
        archive = zipfile.ZipFile(io.BytesIO(gerber_zip(pcb, "placa")))
        self.assertIn("LEEME.txt", archive.namelist())
        rows = placement_csv(pcb).strip().splitlines()
        smd_parts = [item for item in pcb.footprints if item.footprint.smd and item.component.in_bom]
        self.assertEqual(len(rows) - 1, len(smd_parts))

    def test_kicad_board_is_well_formed(self) -> None:
        _, _, pcb = self.boards[1]
        text = to_kicad_pcb(pcb)
        depth = 0
        in_string = escaped = False
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
        for item in pcb.footprints:
            self.assertIn(f'(property "Reference" "{item.component.ref}"', text)
        self.assertIn('(zone (net 1) (net_name "GND") (layer "B.Cu")', text)
        self.assertEqual(text.count("(segment "), len(pcb.tracks))
        # Pads carry the net names KiCad derives from the schematic (no parity warnings).
        names = kicad_net_names(build_schematic(pcb.board))
        pad_nets = set(re.findall(r'\(pad "[^"]*" [^\n]*?\(net \d+ "([^"]+)"\)', text))
        self.assertEqual(pad_nets, {names[net] for net in pcb.nets() if any(net in c.pins.values() for c in pcb.board.components)})
        self.assertIn('(gr_text "IN"', text)
        self.assertIn('(property "Description"', text)


class PcbFormTests(unittest.TestCase):
    def test_view_and_exports(self) -> None:
        form = dict(DEFAULT_FORM, kind="highpass", fp="2k", fs="1k", mounting="tht")
        view = pcb_view(form)
        self.assertTrue(view["ok"])
        self.assertEqual(view["unrouted"], 0)
        self.assertFalse(view["smd"])
        self.assertTrue(pcb_view(form, "bottom")["svg"].startswith("<svg"))
        gerber = export_file(form, "gerber")
        self.assertTrue(gerber["filename"].endswith("_gerber.zip"))
        zipfile.ZipFile(io.BytesIO(base64.b64decode(gerber["base64"])))
        exported = export_file(form, "kicad_pcb")
        project = zipfile.ZipFile(io.BytesIO(base64.b64decode(exported["base64"])))
        base = exported["filename"].removesuffix("_kicad.zip")
        self.assertTrue(project.read(f"{base}/{base}.kicad_pcb").startswith(b"(kicad_pcb"))
        settings = json.loads(project.read(f"{base}/{base}.kicad_pro"))
        self.assertEqual(settings["net_settings"]["classes"][0]["clearance"], 0.25)


if __name__ == "__main__":
    unittest.main()
