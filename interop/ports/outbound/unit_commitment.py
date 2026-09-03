"""The vocabulary both solve ports share for a generator's on/off decision."""

from __future__ import annotations

from enum import StrEnum


class UnitCommitmentTreatment(StrEnum):
    """How a committable generator's on/off decision is solved.

    EXACT keeps status, start-up, and shut-down as true binary decisions, so the solve is a
    mixed-integer program. LINEARISED trades exact integrality for solve time an ensemble of
    many networks cannot always afford. What each framework does with it differs: PyPSA
    relaxes the same decisions to a continuous [0, 1] fraction, and PowerSimulations has no
    relaxed unit commitment formulation, so it falls back to economic dispatch.
    """

    EXACT = "exact"
    LINEARISED = "linearised"
