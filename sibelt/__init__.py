"""sibelt - a posture-adaptive belt that protects the sacroiliac joints.

The package models a lightweight belt that measures the wearer's posture and
adjusts its own circumference so a belt sized for standing never over-
compresses the sacroiliac joints (SIJs) when its wearer sits down.
"""

__version__ = "0.1.0"

from .models import (
    Activity,
    BeltState,
    SIJointLoad,
    WearerProfile,
    belt_circumference_for_tension,
    circumference_mm,
    estimate_si_load,
    rotation_deg_for,
    sanity_errors,
    spring_tension_n,
)

__all__ = [
    "Activity",
    "BeltState",
    "SIJointLoad",
    "WearerProfile",
    "belt_circumference_for_tension",
    "circumference_mm",
    "estimate_si_load",
    "rotation_deg_for",
    "sanity_errors",
    "spring_tension_n",
    "__version__",
]
