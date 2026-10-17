"""Biomechanical core: domain models for the sacroiliac smart belt.

WHY THIS MODULE EXISTS
Everything else in ``sibelt`` is plumbing around the physics in this file.
The whole project stands on three honest simplifications:

1. A belt sized to hold up trousers while STANDING is too tight once the
   wearer SITS: lower-body circumferences increase from standing to sitting
   and the pelvis rotates backward (see PROMPTS.md sources).
2. A belt can only pull, never push, so tension obeys a spring law:

       T = k * max(0, C_wearer - B)

   where ``C_wearer`` is the wearer's circumference at the current posture,
   ``B`` is the belt circumference, and ``k`` is belt stiffness (N/mm).
3. Belt force projected onto sacroiliac joint (SIJ) axes, as a first-order
   model, splits into:

       closure = T * cos(theta)   beneficial "self-bracing" compression
       adverse = T * sin(theta)   pressure in a direction a lax SIJ dislikes

   ``theta`` is posterior pelvic rotation (near zero standing, larger
   sitting/driving). The model is for RELATIVE comparison of belt
   strategies (smart vs static), never for absolute clinical claims.

NOTE: every function here is pure - no module-level state - so the tests
verify properties (slack, monotonicity, projection conservation) rather
than golden snapshots.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum


class Activity(Enum):
    """What the wearer is doing.

    UNKNOWN means "the sensor cannot say" - and the system responds by
    relaxing the belt (fail-loose), never by guessing tighter.
    """

    STANDING = "standing"
    SITTING = "sitting"
    DRIVING = "driving"
    UNKNOWN = "unknown"


# Postures that behave like "seated" for body geometry (circumference grows).
SEATED_ACTIVITIES = (Activity.SITTING, Activity.DRIVING)


@dataclass
class WearerProfile:
    """Every wearer-dependent number lives here - the customization surface.

    NOTE: a new wearer starts from these defaults and overrides only what a
    calibration procedure actually measures (see sibelt.profiles).
    """

    wearer_id: str = "default"

    # -- body geometry (mm) ---------------------------------------------
    c_standing_mm: float = 880.0   # pelvic circumference, standing
    delta_sit_mm: float = 25.0     # how much larger it is when seated

    # -- belt mechanics ---------------------------------------------------
    stiffness_n_per_mm: float = 0.8  # elastic band stiffness (N per mm)
    belt_min_mm: float = 820.0       # actuator envelope floor
    belt_max_mm: float = 985.0       # actuator envelope ceiling
    max_speed_mm_s: float = 40.0     # actuator slew limit (mm/s)

    # -- tension policy (N) ------------------------------------------------
    hold_tension_n: float = 8.0      # standing: just enough to hold trousers
    sitting_tension_n: float = 3.0    # seated floor: near slack, never zero grip
    max_tension_n: float = 30.0      # hard safety ceiling

    # -- posture priors (degrees of posterior pelvic rotation) --------------
    rotation_standing_deg: float = 2.0
    rotation_sitting_deg: float = 15.0
    rotation_driving_deg: float = 25.0

    # -- control timing (s) -------------------------------------------------
    debounce_s: float = 1.0          # posture must persist this long to commit
    retighten_delay_s: float = 2.0   # grace after standing before cinching
    stale_s: float = 3.0             # readings older than this are stale
    watchdog_s: float = 3.0          # safety watchdog window
    ema_alpha: float = 0.15          # low-pass filter strength (0..1)

    # -- energy + mass budget (the "lightweight" requirement) ---------------
    motor_a: float = 0.15             # actuator current draw while moving
    system_ma: float = 0.5           # MCU + IMU average draw (sleep-heavy duty)
    battery_capacity_mah: float = 300.0
    hardware_mass_g: float = 95.0    # electronics + actuator budget (grams)


@dataclass
class SIJointLoad:
    """First-order projection of belt tension onto SIJ axes.

    closure_n: beneficial self-bracing compression across the SIJs.
    adverse_n:  directional pressure the joint should not receive when lax.
    """

    closure_n: float
    adverse_n: float

    @property
    def total_n(self) -> float:
        """Magnitude of the projected force - equals belt tension exactly.

        WHY a property: cos^2 + sin^2 = 1, so the projection never invents
        or loses force. The tests assert this conservation.
        """
        return math.hypot(self.closure_n, self.adverse_n)


@dataclass
class BeltState:
    """One sample of the whole system at time ``t_s`` (a timeline row)."""

    t_s: float
    activity: Activity
    belt_circ_mm: float
    tension_n: float
    si_load: SIJointLoad

    def to_dict(self) -> dict:
        return {
            "t_s": self.t_s,
            "activity": self.activity.value,
            "belt_circ_mm": round(self.belt_circ_mm, 2),
            "tension_n": round(self.tension_n, 3),
            "closure_n": round(self.si_load.closure_n, 3),
            "adverse_n": round(self.si_load.adverse_n, 3),
        }


def rotation_deg_for(profile: WearerProfile, activity: Activity) -> float:
    """Posterior pelvic rotation prior for an activity (degrees)."""
    if activity is Activity.STANDING:
        return profile.rotation_standing_deg
    if activity is Activity.SITTING:
        return profile.rotation_sitting_deg
    if activity is Activity.DRIVING:
        return profile.rotation_driving_deg
    # UNKNOWN: assume the seated geometry - the cautious choice, since the
    # controller relaxes the belt anyway; any residual tension estimate
    # then errs on the careful side.
    return profile.rotation_sitting_deg


def circumference_mm(profile: WearerProfile, activity: Activity) -> float:
    """Wearer's pelvic circumference at the given activity (mm).

    Seated postures present a larger circumference than standing - the
    measured effect this whole project exists to accommodate.
    UNKNOWN is treated as seated (cautious, see rotation_deg_for).
    """
    if activity in SEATED_ACTIVITIES or activity is Activity.UNKNOWN:
        return profile.c_standing_mm + profile.delta_sit_mm
    return profile.c_standing_mm


def spring_tension_n(
    belt_circ_mm: float, wearer_circ_mm: float, stiffness_n_per_mm: float
) -> float:
    """Belt tension in newtons. The belt can pull, never push.

    T = k * max(0, C_wearer - B): at or beyond exact fit the belt is slack
    and contributes exactly zero - it cannot press outward on the body.
    """
    return max(0.0, stiffness_n_per_mm * (wearer_circ_mm - belt_circ_mm))


def belt_circumference_for_tension(
    target_tension_n: float, wearer_circ_mm: float, stiffness_n_per_mm: float
) -> float:
    """Inverse of the spring law: belt circumference that yields a target tension.

    B = C_wearer - T/k. Zero tension means "exact fit"; a truly loose belt
    must go beyond this (callers use the actuator envelope for that).
    """
    return wearer_circ_mm - target_tension_n / stiffness_n_per_mm


def clamp_tension_n(tension_n: float, ceiling_n: float) -> float:
    """Clamp a tension to a ceiling (the safety layer enforces this)."""
    return max(0.0, min(tension_n, ceiling_n))


def estimate_si_load(tension_n: float, rotation_deg: float) -> SIJointLoad:
    """Project belt tension onto SIJ axes at a given pelvic rotation.

    First-order model, used only for relative comparisons between belt
    strategies. Rotation is clamped to [0, 90] degrees.
    """
    theta = max(0.0, min(rotation_deg, 90.0))
    rad = math.radians(theta)
    return SIJointLoad(
        closure_n=tension_n * math.cos(rad),
        adverse_n=tension_n * math.sin(rad),
    )


def sanity_errors(profile: WearerProfile) -> list:
    """Envelope checks; empty list means the profile is usable.

    Every check encodes a physical or safety requirement, e.g. the actuator
    envelope must be able to reach BOTH the standing hold fit and a fully
    loose seated fit - otherwise the belt cannot do its job at all.
    """
    errors = []
    if not (400.0 <= profile.c_standing_mm <= 2000.0):
        errors.append("c_standing_mm must be within 400-2000 mm")
    if not (5.0 <= profile.delta_sit_mm <= 80.0):
        errors.append("delta_sit_mm must be within 5-80 mm")
    if not (0.1 <= profile.stiffness_n_per_mm <= 5.0):
        errors.append("stiffness_n_per_mm must be within 0.1-5.0 N/mm")
    if not (0.0 < profile.sitting_tension_n < profile.hold_tension_n):
        errors.append("tension floors must satisfy 0 < sitting < hold")
    if not (profile.hold_tension_n <= profile.max_tension_n <= 50.0):
        errors.append("must satisfy hold <= max_tension <= 50 N")
    tightest_needed = profile.c_standing_mm - profile.hold_tension_n / profile.stiffness_n_per_mm
    if profile.belt_min_mm > tightest_needed:
        errors.append("belt_min_mm too high to reach standing hold tension")
    loosest_needed = profile.c_standing_mm + profile.delta_sit_mm
    if profile.belt_max_mm <= loosest_needed:
        errors.append("belt_max_mm too low to go slack when seated")
    if not (0.0 <= profile.rotation_standing_deg < profile.rotation_sitting_deg
            < profile.rotation_driving_deg <= 45.0):
        errors.append("rotation priors must be strictly increasing within 0-45 deg")
    if min(profile.debounce_s, profile.retighten_delay_s, profile.stale_s,
           profile.watchdog_s, profile.max_speed_mm_s) <= 0:
        errors.append("timings and speed must be positive")
    if not (0.0 < profile.ema_alpha < 1.0):
        errors.append("ema_alpha must be within (0, 1)")
    if profile.hardware_mass_g > 120.0:
        errors.append("hardware_mass_g exceeds the 120 g lightweight budget")
    return errors


def profile_to_dict(profile: WearerProfile) -> dict:
    """Serialize a profile (stable field order, JSON-friendly)."""
    return asdict(profile)


def profile_from_dict(data: dict) -> WearerProfile:
    """Rebuild a profile, ignoring unknown keys.

    WHY filter: forward compatibility - old profiles load after new fields
    are added, and hand-edited extras never crash the loader.
    """
    known = {f for f in WearerProfile.__dataclass_fields__}
    return WearerProfile(**{k: v for k, v in data.items() if k in known})
