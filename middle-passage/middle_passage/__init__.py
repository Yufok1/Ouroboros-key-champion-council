"""Middle Passage forensic GIS scaffold.

The package creates inspectable survey-priority zones for humanitarian,
memorial, and protection-first research. It does not identify remains or
replace expert review.
"""

from .ethics import Sensitivity, protection_notice
from .voyages.models import Coordinate, SurveyPriorityZone, Voyage

__all__ = [
    "Coordinate",
    "Sensitivity",
    "SurveyPriorityZone",
    "Voyage",
    "protection_notice",
]

__version__ = "0.1.0"

