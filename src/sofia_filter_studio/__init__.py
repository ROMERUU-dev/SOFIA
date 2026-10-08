"""SOFIA Filter Studio."""

__version__ = "0.2.0"

from .models import (
    Approximation,
    DesignInputs,
    DesignResult,
    FilterKind,
    FilterSpec,
    OpAmpModel,
    ResistorSeries,
    Topology,
)

__all__ = [
    "Approximation",
    "DesignInputs",
    "DesignResult",
    "FilterKind",
    "FilterSpec",
    "OpAmpModel",
    "ResistorSeries",
    "Topology",
]
