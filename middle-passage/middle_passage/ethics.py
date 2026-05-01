from __future__ import annotations

from enum import Enum


class Sensitivity(str, Enum):
    """Release sensitivity for project data products."""

    PUBLIC = "public"
    GENERALIZED = "generalized"
    RESTRICTED = "restricted"
    DO_NOT_PUBLISH = "do_not_publish"


def protection_notice() -> str:
    return (
        "These outputs are survey-priority and memorial planning artifacts, "
        "not proof of remains. Treat candidate locations as protected, "
        "non-disturbance zones pending descendant/community, legal, and "
        "archaeological review."
    )

