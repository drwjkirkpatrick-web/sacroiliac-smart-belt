"""Customization: JSON wearer profiles, validation, and calibration.

PRIVACY: a profile stores an opaque ``wearer_id`` string and numbers
only - no names, no contact details, no health data beyond the
anthropometric measurements the belt needs to fit.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
from pathlib import Path

from .models import (
    WearerProfile,
    profile_from_dict,
    profile_to_dict,
    sanity_errors,
)


class ValidationError(ValueError):
    """Raised when a profile cannot be used as-is."""


def default_profile() -> WearerProfile:
    """A fresh profile with the project defaults."""
    return WearerProfile()


class ProfileStore:
    """Load/save/validate a wearer profile as JSON.

    - Missing file -> defaults (first run just works).
    - Saves are atomic (temp file + os.replace) so a crash can never
      truncate an existing profile.
    - ``save`` validates FIRST: a broken profile is never written.
    """

    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> WearerProfile:
        if not self.path.exists():
            return default_profile()
        try:
            data = json.loads(self.path.read_text())
        except json.JSONDecodeError as exc:
            raise ValidationError(f"profile file is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValidationError("profile file must contain a JSON object")
        profile = profile_from_dict(data)
        self.validate(profile)
        return profile

    def save(self, profile: WearerProfile) -> None:
        self.validate(profile)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = tempfile.NamedTemporaryFile(
            "w", dir=str(self.path.parent), delete=False, suffix=".tmp"
        )
        try:
            with fd:
                json.dump(profile_to_dict(profile), fd, indent=2)
                fd.write("\n")
            os.replace(fd.name, str(self.path))
        finally:
            if os.path.exists(fd.name):
                os.remove(fd.name)

    def validate(self, profile: WearerProfile) -> None:
        errors = sanity_errors(profile)
        if errors:
            raise ValidationError("; ".join(errors))

    def calibrate(
        self,
        c_standing_mm: float,
        c_sitting_mm: float,
        wearer_id=None,
    ) -> WearerProfile:
        """Build a calibrated profile from two tape measurements.

        The standing and SEATED circumferences are exactly what the belt
        needs to know: the difference is the seated expansion the actuator
        must absorb (see PROMPTS.md - the measured effect the project
        exists to accommodate).
        """
        if c_sitting_mm < c_standing_mm:
            raise ValidationError(
                "seated circumference must be >= standing circumference")
        base = self.load()
        updated = dataclasses.replace(
            base,
            wearer_id=wearer_id or base.wearer_id,
            c_standing_mm=float(c_standing_mm),
            delta_sit_mm=float(c_sitting_mm - c_standing_mm),
        )
        self.validate(updated)
        return updated
