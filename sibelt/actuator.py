"""Actuator abstraction: moves the belt circumference and tracks its duty.

The real device will be a small ratchet/servo in the buckle; the
abstraction here keeps the rest of the system hardware-agnostic. The
SimulatedActuator models three physical realities the controller must
respect: a rate limit (mm/s), a hard envelope, and the fact that motion
costs battery. The lightweight budget is explicit: motor-on seconds and
system draw are tracked so the simulation can REPORT how much battery a
day of real use would consume.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .models import WearerProfile, spring_tension_n


@dataclass(frozen=True)
class ActuatorStatus:
    position_mm: float
    moving: bool
    motor_on_s: float
    adjustments: int


class Actuator(ABC):
    """The actuator contract: command a target, step time, read status."""

    @abstractmethod
    def command(self, target_mm: float, t_s: float) -> None:
        """Set the target circumference (clamped to the envelope)."""

    @abstractmethod
    def step(self, dt: float) -> ActuatorStatus:
        """Advance ``dt`` seconds; move toward the target at the rate limit."""

    @abstractmethod
    def tension_n(self, wearer_circ_mm: float) -> float:
        """Resulting belt tension against a body of the given circumference."""


class SimulatedActuator(Actuator):
    """Rate-limited virtual actuator with duty accounting."""

    def __init__(self, profile: WearerProfile):
        self.profile = profile
        # Start LOOSE - the fail-safe bootstrap state of the whole design.
        self._position = profile.belt_max_mm
        self._target = profile.belt_max_mm
        # Boot state counts as the initial target, so the FIRST real command
        # (away from the loose state) is counted as an adjustment.
        self._last_target = profile.belt_max_mm
        self._motor_on_s = 0.0
        self._adjustments = 0

    def command(self, target_mm: float, t_s: float) -> None:
        target = max(self.profile.belt_min_mm,
                     min(self.profile.belt_max_mm, target_mm))
        if self._last_target is not None and target != self._last_target:
            self._adjustments += 1
        self._last_target = target
        self._target = target

    def step(self, dt: float) -> ActuatorStatus:
        delta = self._target - self._position
        max_move = self.profile.max_speed_mm_s * dt
        move = max(-max_move, min(max_move, delta))
        if move != 0.0:
            self._position += move
            # Battery: the motor draws only while actually moving; bill the
            # fraction of dt proportional to the motion distance.
            self._motor_on_s += abs(move) / self.profile.max_speed_mm_s
        moving = abs(self._target - self._position) > 1e-9
        return ActuatorStatus(self._position, moving, self._motor_on_s,
                              self._adjustments)

    def tension_n(self, wearer_circ_mm: float) -> float:
        return spring_tension_n(self._position, wearer_circ_mm,
                                self.profile.stiffness_n_per_mm)

    def battery_mah_used(self, duration_s: float) -> float:
        """Estimated mAh consumed: motor duty + always-on system draw."""
        motor_mah = self._motor_on_s / 3600.0 * self.profile.motor_a * 1000.0
        system_mah = duration_s / 3600.0 * self.profile.system_ma
        return motor_mah + system_mah
