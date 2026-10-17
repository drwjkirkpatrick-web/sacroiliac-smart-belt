"""Sensor layer: IMU abstraction and a deterministic simulated IMU.

NOTE ON REALISM
The simulated sensor rides at the right iliac crest of a belt, x axis
pointing ventrally (forward), z axis pointing down. At rest an
accelerometer measures the reaction against gravity, so with the pelvis
retroverted (rotated backward) by ``theta``:

    ax = -g * sin(theta)
    az = +g * cos(theta)

The inverse mapping ``rotation_deg_from_gravity`` recovers theta from a
reading; the posture classifier (classify.py) reuses exactly this
function so the emission and the estimate can never drift apart.

WHY a fake IMU at all: the whole stack must be testable and demonstrable
without hardware, and tests need determinism - so every stochastic
element draws from a seeded RNG.
"""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .models import Activity

G_MPS2 = 9.81

# Default posterior pelvic rotation per activity (degrees). Mirrors the
# WearerProfile defaults; the engine overrides these with profile values.
DEFAULT_ROTATIONS: Dict[Activity, float] = {
    Activity.STANDING: 2.0,
    Activity.SITTING: 15.0,
    Activity.DRIVING: 25.0,
    Activity.UNKNOWN: 15.0,
}


@dataclass(frozen=True)
class SensorReading:
    """One 6-axis sample. Accels in m/s^2, gyros in rad/s."""

    t_s: float
    ax: float
    ay: float
    az: float
    gx: float
    gy: float
    gz: float


def rotation_deg_from_gravity(ax: float, az: float) -> float:
    """Recover posterior pelvic rotation (deg) from the gravity components.

    Inverse of the emission formula; works for theta in (-90, 90).
    """
    if az == 0.0 and ax == 0.0:
        return 0.0
    return math.degrees(math.atan2(-ax, az))


class IMU(ABC):
    """The sensor contract the rest of the system depends on."""

    @abstractmethod
    def read(self) -> Optional[SensorReading]:
        """Return the next sample, or None when no new data exists."""

    @property
    @abstractmethod
    def has_data(self) -> bool:
        """False once the stream is exhausted (or the sensor is dead)."""


class NoSignalIMU(IMU):
    """A dead sensor. Exists so safety tests can prove the watchdog fires."""

    def read(self) -> Optional[SensorReading]:
        return None

    @property
    def has_data(self) -> bool:
        return False


@dataclass(frozen=True)
class ScenarioSegment:
    """One posture held for ``duration_s``.

    transition_s: how long the (smoothed) change from the previous posture
    takes at the START of this segment - a real sit-down is not instant.
    """

    activity: Activity
    duration_s: float
    transition_s: float = 1.5


def total_duration_s(scenario: Sequence[ScenarioSegment]) -> float:
    """Total scenario length in seconds."""
    return sum(seg.duration_s for seg in scenario)


def _smoothstep(u: float) -> float:
    """Smooth 0->1 ramp with zero slope at both ends (a gentle sit-down)."""
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


class SimulatedIMU(IMU):
    """Deterministic waist-worn IMU playing back a posture scenario.

    - Rotation follows the scenario: each segment targets the rotation
      prior of its activity, eased in with a smoothstep over
      ``transition_s`` seconds.
    - Sensor noise is Gaussian (seeded) on all six axes; gyro channels also
      carry the true angular rate of the pelvis during transitions.
    - ``read()`` advances the clock by ``dt``; once the scenario is
      exhausted it returns None (``has_data`` False) forever after.
    """

    def __init__(
        self,
        scenario: Sequence[ScenarioSegment],
        seed: int = 7,
        dt: float = 0.02,
        noise_std: float = 0.04,
        rotations: Optional[Dict[Activity, float]] = None,
    ):
        self.scenario: List[ScenarioSegment] = list(scenario)
        if not self.scenario:
            raise ValueError("scenario must contain at least one segment")
        self.dt = dt
        self.noise_std = noise_std
        self.rotations = dict(rotations or DEFAULT_ROTATIONS)
        self._rng = random.Random(seed)
        self._t = 0.0
        self._theta = self.rotations.get(self.scenario[0].activity, 2.0)
        self._prev_theta = self._theta
        self._seg_index = 0
        self._seg_elapsed = 0.0
        self._seg_ticks = 0

    @property
    def has_data(self) -> bool:
        return self._seg_index < len(self.scenario)

    def read(self) -> Optional[SensorReading]:
        if not self.has_data:
            return None

        seg = self.scenario[self._seg_index]
        target = self.rotations.get(seg.activity, self.rotations[Activity.STANDING])

        # Ease from the previous posture into this segment's target.
        if seg.transition_s > 0.0 and self._seg_elapsed < seg.transition_s:
            u = self._seg_elapsed / seg.transition_s
            self._prev_theta = self._theta
            self._theta = self._theta + (target - self._theta) * _smoothstep_delta(
                self._theta, target, u
            )
        else:
            self._prev_theta = self._theta
            self._theta = target

        theta_rad = math.radians(self._theta)
        rate_rad_s = 0.0
        if self.dt > 0:
            rate_rad_s = math.radians(self._theta - self._prev_theta) / self.dt

        g = G_MPS2
        n = self.noise_std
        rng = self._rng
        reading = SensorReading(
            t_s=self._t,
            ax=-g * math.sin(theta_rad) + rng.gauss(0.0, n),
            ay=rng.gauss(0.0, n),
            az=g * math.cos(theta_rad) + rng.gauss(0.0, n),
            gx=rng.gauss(0.0, n * 0.5),
            gy=-rate_rad_s + rng.gauss(0.0, n * 0.5),
            gz=rng.gauss(0.0, n * 0.5),
        )

        # Advance the clock and segment state.
        # NOTE: segment advancement counts integer ticks, never accumulated
        # floats - 0.02 added 500 times is not exactly 10.0, and drifting
        # comparisons would occasionally hold a segment one tick too long.
        self._t += self.dt
        self._seg_elapsed += self.dt
        self._seg_ticks += 1
        if self._seg_ticks >= max(1, round(seg.duration_s / self.dt)):
            self._seg_index += 1
            self._seg_ticks = 0
            self._seg_elapsed = 0.0
        return reading


def _smoothstep_delta(current: float, target: float, u: float) -> float:
    """Fraction of the remaining gap to close at progress ``u`` (0..1)."""
    return (target - current) * _smoothstep(u)
