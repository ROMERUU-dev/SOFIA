from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class FilterKind(StrEnum):
    LOWPASS = "lowpass"
    HIGHPASS = "highpass"
    BANDPASS = "bandpass"
    BANDSTOP = "bandstop"


class Approximation(StrEnum):
    BUTTERWORTH = "butterworth"
    CHEBYSHEV_I = "chebyshev"


class Topology(StrEnum):
    AUTO = "auto"
    SALLEN_KEY = "sallen_key"
    ANTONIOU = "antoniou"
    TOW_THOMAS = "tow_thomas"
    MFB = "mfb"
    OTA = "ota"


class OpAmpModel(StrEnum):
    LM324 = "LM324"
    LM318 = "LM318"
    UA741 = "uA741"
    TL082 = "TL082"
    LM7171 = "LM7171"
    LM6164 = "LM6164"
    LM6165 = "LM6165"
    LM6171 = "LM6171"


class ResistorSeries(StrEnum):
    E12 = "E12"
    E24 = "E24"
    E48 = "E48"


@dataclass(slots=True)
class FilterSpec:
    passband_hz: float | tuple[float, float]
    stopband_hz: float | tuple[float, float]


@dataclass(slots=True)
class DesignInputs:
    kind: FilterKind
    approximation: Approximation
    spec: FilterSpec
    passband_ripple_db: float
    stopband_attenuation_db: float
    topology: Topology = Topology.SALLEN_KEY
    opamp: OpAmpModel = OpAmpModel.TL082
    stage_capacitor_f: float = 10e-9
    resistor_series: ResistorSeries = ResistorSeries.E24
    allow_resistor_arrays: bool = True
    max_resistors_per_network: int = 2
    auto_stage_capacitor: bool = True

    def validate(self) -> None:
        if self.passband_ripple_db <= 0:
            raise ValueError("passband_ripple_db must be positive in dB")
        if self.stopband_attenuation_db <= self.passband_ripple_db:
            raise ValueError("stopband_attenuation_db must exceed passband_ripple_db")
        if self.stage_capacitor_f <= 0:
            raise ValueError("stage_capacitor_f must be positive")
        if self.max_resistors_per_network < 1:
            raise ValueError("max_resistors_per_network must be at least 1")


@dataclass(slots=True)
class ResistorNetwork:
    label: str
    target_ohms: float
    realized_ohms: float
    connection: str
    parts_ohms: list[float]
    relative_error: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StageRealization:
    topology: Topology
    stage_index: int
    kind: FilterKind
    gain: float | None
    resistor_targets_ohms: dict[str, float]
    capacitor_values_f: dict[str, float]
    resistor_networks: dict[str, ResistorNetwork]
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "topology": self.topology,
            "stage_index": self.stage_index,
            "kind": self.kind,
            "gain": self.gain,
            "resistor_targets_ohms": self.resistor_targets_ohms,
            "capacitor_values_f": self.capacitor_values_f,
            "resistor_networks": {
                name: network.as_dict()
                for name, network in self.resistor_networks.items()
            },
            "notes": self.notes,
        }


@dataclass(slots=True)
class Stage:
    index: int
    natural_frequency_hz: float
    q: float | None
    order: int
    poles: tuple[complex, ...]
    damping_hz: float | None = None
    zero_frequency_hz: float | None = None
    gain_reference_hz: float | None = None
    realization: StageRealization | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["poles"] = [
            {"real": pole.real, "imag": pole.imag}
            for pole in self.poles
        ]
        if self.realization is not None:
            data["realization"] = self.realization.as_dict()
        return data


@dataclass(slots=True)
class DesignResult:
    order: int
    epsilon: float
    poles: list[complex]
    stages: list[Stage]
    summary: dict[str, Any]
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "epsilon": self.epsilon,
            "poles": [{"real": pole.real, "imag": pole.imag} for pole in self.poles],
            "stages": [stage.as_dict() for stage in self.stages],
            "summary": self.summary,
            "warnings": self.warnings,
        }
