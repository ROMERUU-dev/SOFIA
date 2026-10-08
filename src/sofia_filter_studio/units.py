"""Engineering-notation helpers shared by the user interfaces."""

from __future__ import annotations

import math
import re

PREFIXES = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "m": 1e-3,
    "": 1.0,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "meg": 1e6,
    "G": 1e9,
}
_DISPLAY_PREFIXES = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p"))
_QUANTITY_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[pnuµμmkKMG]?)\s*([A-Za-zΩ]*)\s*$")


def parse_quantity(text: str, unit: str = "") -> float:
    """Parse '10n', '0,1 uF', '1.5k', '2 kHz' or '1e-8' into a float.

    Raises ValueError with a readable message when the text is not a number.
    """
    cleaned = text.strip().replace(",", ".")
    match = _QUANTITY_RE.match(cleaned)
    if not match:
        raise ValueError(f"'{text.strip()}' no es un número válido")
    number, prefix, suffix = match.groups()
    accepted = {unit.lower(), "ohm", "Ω".lower()} if unit in {"Ω", "ohm"} else {unit.lower()}
    if suffix and unit and suffix.lower() not in accepted:
        raise ValueError(f"unidad '{suffix}' no reconocida en '{text.strip()}' (se espera {unit})")
    return float(number) * PREFIXES[prefix]


def format_quantity(value: float, unit: str = "", digits: int = 4) -> str:
    """146266.05 -> '146.3 kΩ' (with unit='Ω'); 1e-9 -> '1 nF' (with unit='F')."""
    if value == 0 or not math.isfinite(value):
        return f"{value:g} {unit}".strip()
    magnitude = abs(value)
    for scale, prefix in _DISPLAY_PREFIXES:
        if magnitude >= scale * 0.9995:
            break
    scaled = value / scale
    text = f"{scaled:.{digits}g}"
    return f"{text} {prefix}{unit}".strip()


def format_resistor_value(value: float) -> str:
    """Compact resistor notation used on schematics: 150000 -> '150k', 4700 -> '4.7k', 39 -> '39'."""
    for scale, prefix in ((1e6, "M"), (1e3, "k")):
        if value >= scale:
            return f"{value / scale:.4g}{prefix}"
    return f"{value:.4g}"
