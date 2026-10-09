"""KiCad project in a ZIP: the schematic, the board (when there is one) and the SOFIA symbol library.

Opening the .kicad_pro keeps the schematic and the board linked (Update PCB from Schematic) and gives
ERC and DRC with the routing rules of the board and without missing-library warnings.
"""

from __future__ import annotations

import io
import json
import zipfile

from .router import Rules
from .schematic import Schematic, kicad_symbol_library, to_kicad

SYM_LIB_TABLE = (
    "(sym_lib_table\n"
    "\t(version 7)\n"
    '\t(lib (name "SOFIA") (type "KiCad") (uri "${KIPRJMOD}/SOFIA.kicad_sym") (options "") (descr "SOFIA Filter Studio"))\n'
    ")\n"
)


def project_file(base: str, rules: Rules) -> str:
    """Minimal .kicad_pro: KiCad fills in its defaults; the Default net class takes the board rules."""
    default_class = {
        "name": "Default",
        "clearance": rules.clearance,
        "track_width": rules.track,
        "via_diameter": rules.via_diameter,
        "via_drill": rules.via_drill,
        "wire_width": 6,
        "bus_width": 12,
        "line_style": 0,
        "priority": 2147483647,
    }
    project = {
        # The footprints carry the library pads but simpler drawings; KiCad would flag every one as
        # different from its library copy (Tools > Update Footprints from Library brings the full ones).
        "board": {"design_settings": {"rule_severities": {"lib_footprint_mismatch": "ignore"}}},
        "meta": {"filename": f"{base}.kicad_pro", "version": 1},
        "net_settings": {"classes": [default_class], "meta": {"version": 3}},
    }
    return json.dumps(project, indent=2) + "\n"


def project_zip(schematic: Schematic, base: str, pcb=None) -> bytes:
    """``base/`` with base.kicad_pro, base.kicad_sch, base.kicad_pcb (if ``pcb``), sym-lib-table and SOFIA.kicad_sym."""
    files = {
        f"{base}.kicad_pro": project_file(base, pcb.rules if pcb is not None else Rules()),
        f"{base}.kicad_sch": to_kicad(schematic, project=base),
        "sym-lib-table": SYM_LIB_TABLE,
        "SOFIA.kicad_sym": kicad_symbol_library(schematic),
    }
    if pcb is not None:
        from .pcbfiles import to_kicad_pcb

        files[f"{base}.kicad_pcb"] = to_kicad_pcb(pcb, schematic)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            info = zipfile.ZipInfo(f"{base}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text)
    return buffer.getvalue()
