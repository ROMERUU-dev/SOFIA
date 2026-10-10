"""SOFIA Filter Studio."""

__version__ = "0.5.1"

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
