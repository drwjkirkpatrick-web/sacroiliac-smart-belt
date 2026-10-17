"""Closed-loop engine: one belt, wired end to end, and a day of real use.

THE TWO RUNS THAT MATTER
``simulate()`` plays the SAME sensor stream (same seed) through two belts:

1. the SMART belt - sensor -> classifier -> controller -> safety ->
   actuator, exactly as the hardware would run; and
2. the STATIC belt - the ordinary-clothing control case: a belt fixed at
   the circumference that fits its wearer while STANDING, left alone all
   day (a frozen actuator). Standing it holds trousers at ~8 N; the
   moment its wearer sits, the seated body is larger than the standing
   body, so the same belt pulls several times harder - the everyday
   failure this project exists to fix.

The comparison metric is the ADVERSE (misdirected) load integral over
seated periods - what a lax sacroiliac joint should not be receiving
while its owner sits at a desk or in a car.
"""

from __future__ import annotations

import dataclasses
import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from .actuator import SimulatedActuator
from .classify import PostureClassifier
from .control import TensionController
from .models import (
    Activity,
    BeltState,
    WearerProfile,
    belt_circumference_for_tension,
    circumference_mm,
    estimate_si_load,
    rotation_deg_for,
)
from .safety import OverrideMode, SafetyMonitor
from .sensors import ScenarioSegment, SimulatedIMU

DT = 0.02
SEATED = (Activity.SITTING, Activity.DRIVING)


def scenario_day():
    """A rough clinical-day schedule (segment durations in seconds)."""
    return [
        ScenarioSegment(Activity.STANDING, 900.0),    # morning on feet
        ScenarioSegment(Activity.DRIVING, 1200.0),    # commute to work
        ScenarioSegment(Activity.STANDING, 60.0),     # walk in
        ScenarioSegment(Activity.SITTING, 3600.0),    # an hour at the desk
        ScenarioSegment(Activity.STANDING, 300.0),    # a stretch break
        ScenarioSegment(Activity.SITTING, 3600.0),    # another desk hour
        ScenarioSegment(Activity.DRIVING, 1200.0),    # drive home
        ScenarioSegment(Activity.STANDING, 900.0),    # evening on feet
    ]


def scenario_commute():
    """The minimal version of the user's own scenario: stand, drive, stand."""
    return [
        ScenarioSegment(Activity.STANDING, 600.0),
        ScenarioSegment(Activity.DRIVING, 1800.0),
        ScenarioSegment(Activity.STANDING, 600.0),
    ]


SCENARIOS = {"day": scenario_day, "commute": scenario_commute}


class BeltEngine:
    """Wires every layer into one belt.

    One ``tick`` = read -> classify -> control -> enforce safety ->
    actuate -> record. Ticks are driven by the caller (``run`` plays back
    a scenario; fault tests tick by hand).
    """

    def __init__(self, profile: WearerProfile, imu,
                 actuator: Optional[SimulatedActuator] = None,
                 classifier: Optional[PostureClassifier] = None,
                 controller: Optional[TensionController] = None,
                 safety: Optional[SafetyMonitor] = None,
                 override: Optional[OverrideMode] = None,
                 dt: float = DT):
        self.profile = profile
        self.dt = dt
        self.imu = imu
        self.actuator = actuator or SimulatedActuator(profile)
        self.classifier = classifier or PostureClassifier(profile)
        self.controller = controller or TensionController(profile)
        self.safety = safety or SafetyMonitor(profile)
        self.override = override or OverrideMode.NONE
        self.rows: List[BeltState] = []
        self.safety_events = []
        # Both the actuator and the engine boot LOOSE (fail-safe by default).
        self._position = profile.belt_max_mm
        self.status = None

    def tick(self, t_s: float) -> BeltState:
        reading = self.imu.read()
        estimate = self.classifier.update(reading, t_s)
        command = self.controller.update(estimate, t_s)

        wearer_c = circumference_mm(self.profile, estimate.activity)
        tension = self.actuator.tension_n(wearer_c)

        decision = self.safety.enforce(command, estimate, tension,
                                       self.override, t_s, self._position)
        self.safety_events.extend(decision.events)

        self.actuator.command(decision.command_mm, t_s)
        self.status = self.actuator.step(self.dt)
        self._position = self.status.position_mm

        tension = self.actuator.tension_n(wearer_c)
        rotation = rotation_deg_for(self.profile, estimate.activity)
        row = BeltState(t_s=t_s, activity=estimate.activity,
                        belt_circ_mm=self._position, tension_n=tension,
                        si_load=estimate_si_load(tension, rotation))
        self.rows.append(row)
        return row

    def run(self) -> List[BeltState]:
        """Play the sensor stream to exhaustion."""
        t_s = 0.0
        while self.imu.has_data:
            self.tick(t_s)
            t_s += self.dt
        return self.rows


def summarize(rows: List[BeltState], profile: WearerProfile, dt: float) -> Dict:
    """Adverse-load metrics over the seated periods (and overall peaks)."""
    adverse_integral = 0.0
    peak_adverse_n = 0.0
    peak_seated_tension_n = 0.0
    seated_ticks = 0
    seated_at_floor = 0
    floor = profile.sitting_tension_n + 1.5  # small travel allowance

    for row in rows:
        seated = row.activity in SEATED
        if seated:
            adverse_integral += row.si_load.adverse_n * dt
            peak_adverse_n = max(peak_adverse_n, row.si_load.adverse_n)
            peak_seated_tension_n = max(peak_seated_tension_n, row.tension_n)
            seated_ticks += 1
            if row.tension_n <= floor:
                seated_at_floor += 1

    return {
        "adverse_integral_n_s": round(adverse_integral, 2),
        "peak_adverse_n": round(peak_adverse_n, 3),
        "peak_seated_tension_n": round(peak_seated_tension_n, 2),
        "seated_ticks": seated_ticks,
        "seated_at_floor_pct": round(100.0 * seated_at_floor / seated_ticks, 2)
                               if seated_ticks else 0.0,
    }


@dataclass
class SimulationReport:
    """Everything the CLI, README, and paper report about one comparison."""

    scenario: str
    seed: int
    time_scale: float
    duration_s: float
    ticks: int
    smart: Dict
    baseline: Dict
    reduction_pct: float
    adjustments: int
    battery_mah: float
    safety_event_count: int
    hardware_mass_g: float

    def to_json(self) -> str:
        return json.dumps({
            "scenario": self.scenario,
            "seed": self.seed,
            "time_scale": self.time_scale,
            "duration_s": self.duration_s,
            "ticks": self.ticks,
            "smart": self.smart,
            "baseline": self.baseline,
            "adverse_reduction_pct": round(self.reduction_pct, 1),
            "adjustments": self.adjustments,
            "battery_mah": round(self.battery_mah, 2),
            "safety_event_count": self.safety_event_count,
            "hardware_mass_g": self.hardware_mass_g,
        }, indent=2)

    def render_text(self) -> str:
        lines = [
            f"Scenario: {self.scenario} (seed {self.seed}, scale {self.time_scale})",
            f"Duration: {self.duration_s:.0f} s of simulated wear, "
            f"{self.ticks} control ticks",
            "",
            "Seated adverse SIJ load (what a lax joint should not receive):",
            f"  static belt : {self.baseline['adverse_integral_n_s']:.0f} N.s"
            f"  (peak tension {self.baseline['peak_seated_tension_n']:.1f} N)",
            f"  smart belt  : {self.smart['adverse_integral_n_s']:.0f} N.s"
            f"  (peak tension {self.smart['peak_seated_tension_n']:.1f} N)",
            f"  reduction   : {self.reduction_pct:.1f}%",
            "",
            f"Seated time at/under the comfort floor: "
            f"{self.smart['seated_at_floor_pct']:.1f}%",
            f"Actuator adjustments: {self.adjustments}",
            f"Battery used: {self.battery_mah:.2f} mAh of "
            f"{self.hardware_mass_g:.0f} g-class hardware",
            f"Safety events: {self.safety_event_count}",
        ]
        return "\n".join(lines)


def simulate(profile: Optional[WearerProfile] = None, scenario: str = "day",
             seed: int = 7, time_scale: float = 1.0) -> SimulationReport:
    """Run the smart belt against a static belt on the same sensor stream."""
    profile = profile or WearerProfile()
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    segments = SCENARIOS[scenario]()
    if time_scale != 1.0:
        segments = [ScenarioSegment(s.activity,
                                     max(s.transition_s * 2.0,
                                         s.duration_s * time_scale),
                                     s.transition_s)
                    for s in segments]
    rotations = {
        Activity.STANDING: profile.rotation_standing_deg,
        Activity.SITTING: profile.rotation_sitting_deg,
        Activity.DRIVING: profile.rotation_driving_deg,
        Activity.UNKNOWN: profile.rotation_sitting_deg,
    }

    # Run 1: the smart belt.
    imu = SimulatedIMU(segments, seed=seed, rotations=rotations)
    engine = BeltEngine(profile, imu)
    engine.run()
    smart_rows = engine.rows

    # Run 2: the static belt - same stream, actuator frozen at the
    # standing fit. That is ordinary clothing: sized standing, unchanging.
    static_fit = belt_circumference_for_tension(
        profile.hold_tension_n, profile.c_standing_mm, profile.stiffness_n_per_mm)
    frozen_profile = dataclasses.replace(profile, belt_min_mm=static_fit,
                                         belt_max_mm=static_fit)
    imu2 = SimulatedIMU(segments, seed=seed, rotations=rotations)
    baseline_engine = BeltEngine(frozen_profile, imu2)
    baseline_engine.run()
    baseline_rows = baseline_engine.rows

    duration_s = len(smart_rows) * DT
    smart = summarize(smart_rows, profile, DT)
    baseline = summarize(baseline_rows, profile, DT)
    reduction = 0.0
    if baseline["adverse_integral_n_s"] > 0:
        reduction = 100.0 * (1.0 - smart["adverse_integral_n_s"]
                             / baseline["adverse_integral_n_s"])

    adjustments = engine.status.adjustments if engine.status else 0
    battery = engine.actuator.battery_mah_used(duration_s)

    return SimulationReport(
        scenario=scenario,
        seed=seed,
        time_scale=time_scale,
        duration_s=duration_s,
        ticks=len(smart_rows),
        smart=smart,
        baseline=baseline,
        reduction_pct=reduction,
        adjustments=adjustments,
        battery_mah=battery,
        safety_event_count=len(engine.safety_events),
        hardware_mass_g=profile.hardware_mass_g,
    )
