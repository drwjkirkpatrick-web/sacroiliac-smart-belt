"""Tension policy and controller: what the belt should be doing right now.

WHY SEATED SLACK COSTS NOTHING
The evidence base for this project includes the finding that a pelvic
belt tension of 100 N does not reduce sacroiliac joint laxity more than
50 N (see PROMPTS.md): extra tension buys no extra stabilization. So a
belt that relaxes when its wearer sits loses nothing therapeutically -
and escapes the seated over-tension entirely.

WHY RE-TIGHTENING IS DELAYED
Loosening is immediate (comfort/safety). Re-tightening waits
``retighten_delay_s`` after the wearer enters STANDING so the belt never
cinches while its owner is still mid-motion between postures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .classify import PositionEstimate
from .models import (
    Activity,
    WearerProfile,
    belt_circumference_for_tension,
    circumference_mm,
)

SEATED = (Activity.SITTING, Activity.DRIVING)


@dataclass(frozen=True)
class Command:
    """A circumference order for the actuator, with its justification."""

    target_circ_mm: float
    reason: str


class TensionPolicy:
    """Maps an activity to the tension the belt should aim for (newtons)."""

    def __init__(self, profile: WearerProfile):
        self.profile = profile

    def target_tension_n(self, activity: Activity) -> float:
        if activity is Activity.STANDING:
            return self.profile.hold_tension_n
        if activity in SEATED:
            return self.profile.sitting_tension_n
        return 0.0  # UNKNOWN -> loose (fail-loose)


class TensionController:
    """Turns a posture estimate into a circumference command."""

    def __init__(self, profile: WearerProfile):
        self.profile = profile
        self.policy = TensionPolicy(profile)
        self._last_activity = Activity.UNKNOWN
        self._standing_since: Optional[float] = None

    def update(self, estimate: PositionEstimate, t_s: float) -> Command:
        activity = estimate.activity

        if activity is Activity.STANDING and self._last_activity is not Activity.STANDING:
            self._standing_since = t_s
        self._last_activity = activity

        if activity is Activity.STANDING:
            settled = (
                self._standing_since is not None
                and (t_s - self._standing_since) >= self.profile.retighten_delay_s
            )
            if settled:
                # Hold trousers up: belt slightly smaller than the standing body.
                target = belt_circumference_for_tension(
                    self.profile.hold_tension_n,
                    circumference_mm(self.profile, Activity.STANDING),
                    self.profile.stiffness_n_per_mm,
                )
                cmd = Command(target, "hold: keep trousers up while standing")
            else:
                # Grace window after standing up: stay loose while settling.
                target = belt_circumference_for_tension(
                    self.profile.sitting_tension_n,
                    circumference_mm(self.profile, Activity.SITTING),
                    self.profile.stiffness_n_per_mm,
                )
                cmd = Command(target, "grace: settling after standing (loose)")
        elif activity in SEATED:
            target = belt_circumference_for_tension(
                self.profile.sitting_tension_n,
                circumference_mm(self.profile, activity),
                self.profile.stiffness_n_per_mm,
            )
            cmd = Command(target, "slack: seated floor tension")
        else:
            cmd = Command(self.profile.belt_max_mm, "fail-loose: posture unknown")

        clamped = max(self.profile.belt_min_mm,
                      min(self.profile.belt_max_mm, cmd.target_circ_mm))
        return Command(clamped, cmd.reason)
