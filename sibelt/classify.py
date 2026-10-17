"""Posture classifier: IMU samples -> debounced, hysteresis-bounded activity.

DESIGN NOTE - why debounce and confidence gates
Waist-worn accelerometers are the standard for activity assessment, but
telling sitting from light activity apart from the waist alone is
genuinely hard (see PROMPTS.md sources); a naive nearest-centroid
classifier flaps at every posture boundary. This classifier commits a
posture change only after the candidate has PERSISTED for ``debounce_s``
and is confident enough, and it never guesses tighter - stale or
unreadable input degrades to UNKNOWN, which the tension policy maps to
"loose". SITTING vs DRIVING confusion is deliberately tolerated: both get
slack targets, so confusing them costs almost nothing (graceful
degradation by design).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models import Activity, WearerProfile
from .sensors import SensorReading, rotation_deg_from_gravity

# Below this confidence the classifier refuses to commit a posture change.
MIN_CONFIDENCE = 0.35


@dataclass(frozen=True)
class PositionEstimate:
    """What the classifier believes right now."""

    activity: Activity
    rotation_deg: float
    confidence: float
    t_s: float
    age_s: float


class PostureClassifier:
    """Debounced nearest-prior posture estimator.

    Feed it one reading per tick (or None when the sensor has nothing new);
    it returns its best current belief. ``switch_count`` counts committed
    activity changes - the tests use it to prove the classifier does not
    flap under noise.
    """

    def __init__(self, profile: WearerProfile):
        self.profile = profile
        self._rotation: Optional[float] = None
        self._activity = Activity.UNKNOWN
        self._candidate: Optional[Activity] = None
        self._candidate_since = 0.0
        self._last_data_t: Optional[float] = None
        self.switch_count = 0

    # -- internals -----------------------------------------------------

    def _priors(self) -> dict:
        return {
            Activity.STANDING: self.profile.rotation_standing_deg,
            Activity.SITTING: self.profile.rotation_sitting_deg,
            Activity.DRIVING: self.profile.rotation_driving_deg,
        }

    def _nearest(self, rotation: float):
        """Nearest posture prior: (activity, distance_deg, confidence)."""
        priors = self._priors()
        values = sorted(priors.values())
        separation = ((values[2] - values[1]) + (values[1] - values[0])) / 2.0
        if separation <= 0:
            separation = 1.0
        best = min(priors.items(), key=lambda kv: abs(rotation - kv[1]))
        distance = abs(rotation - best[1])
        confidence = max(0.0, 1.0 - distance / separation)
        return best[0], distance, confidence

    # -- API -----------------------------------------------------------

    def update(self, reading: Optional[SensorReading], t_s: float) -> PositionEstimate:
        """Feed one reading (None = no data this tick); get the estimate."""
        confidence = 0.0
        if reading is not None:
            raw = rotation_deg_from_gravity(reading.ax, reading.az)
            if self._rotation is None:
                self._rotation = raw
            else:
                a = self.profile.ema_alpha
                self._rotation = a * raw + (1.0 - a) * self._rotation
            self._last_data_t = t_s

            nearest, _distance, confidence = self._nearest(self._rotation)
            if confidence >= MIN_CONFIDENCE:
                if nearest == self._activity:
                    self._candidate = None
                else:
                    if self._candidate != nearest:
                        self._candidate = nearest
                        self._candidate_since = t_s
                    if t_s - self._candidate_since >= self.profile.debounce_s:
                        self._activity = nearest
                        self._candidate = None
                        self.switch_count += 1
            # Low-confidence readings change nothing - that is the hysteresis.

        # Staleness: no fresh data at all -> UNKNOWN (the policy loosens).
        if self._last_data_t is None:
            age = float("inf")
        else:
            age = max(0.0, t_s - self._last_data_t)
        activity = self._activity
        rot = self._rotation if self._rotation is not None else 0.0
        if age > self.profile.stale_s:
            if self._activity is not Activity.UNKNOWN:
                self._activity = Activity.UNKNOWN
                self._candidate = None
                self.switch_count += 1
            activity = Activity.UNKNOWN
            confidence = 0.0

        return PositionEstimate(
            activity=activity,
            rotation_deg=round(rot, 3),
            confidence=round(min(confidence, 1.0), 3),
            t_s=t_s,
            age_s=age,
        )
