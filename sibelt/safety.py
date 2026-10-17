"""Fail-loose safety monitor: the layer that outranks everybody.

FAIL-LOOSE PRINCIPLE
The safe state of a belt is the LOOSEST state. Rationale (see PROMPTS.md
sources): a pelvic belt's stabilizing benefit saturates - a tension of
100 N does not reduce sacroiliac laxity more than 50 N - so excess
tension buys nothing clinically while a lax, previously injured SIJ is
exactly the structure that should not receive misdirected pressure.
Sagging trousers are a cosmetic failure; over-compression is not.
Therefore every fault path in this module ends at ``belt_max_mm``.

PRECEDENCE (checked in order)
1. Override LOOSEN   - the wearer opened the belt by hand
2. Override FREEZE   - the wearer froze the fit; even a stale sensor
                        does not unfreeze a deliberate human act
3. Watchdog          - estimate stale beyond ``watchdog_s``
4. Tension ceiling   - measured tension above ``max_tension_n``
5. Policy            - the controller's request passes through
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

from .classify import PositionEstimate
from .control import Command
from .models import Activity, WearerProfile


class OverrideMode(Enum):
    """Manual override states (a physical button on the buckle)."""

    NONE = "none"
    FREEZE = "freeze"
    LOOSEN = "loosen"


class EventKind(Enum):
    WATCHDOG = "watchdog"
    TENSION_CEILING = "tension_ceiling"
    OVERRIDE = "override"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class SafetyEvent:
    t_s: float
    kind: EventKind
    detail: str


@dataclass(frozen=True)
class SafetyDecision:
    command_mm: float
    reason: str
    events: Tuple[SafetyEvent, ...]


class SafetyMonitor:
    """Interposes between the controller and the actuator."""

    def __init__(self, profile: WearerProfile):
        self.profile = profile
        self.events: List[SafetyEvent] = []  # lifetime log
        self._watchdog_episode = False
        self._low_conf_episode = False

    def _log(self, t_s: float, kind: EventKind, detail: str) -> SafetyEvent:
        event = SafetyEvent(t_s, kind, detail)
        self.events.append(event)
        return event

    def enforce(
        self,
        command: Command,
        estimate: PositionEstimate,
        current_tension_n: float,
        override: OverrideMode,
        t_s: float,
        current_position_mm: float,
    ) -> SafetyDecision:
        """Return the FINAL circumference order for this tick."""
        events: List[SafetyEvent] = []
        loosest = self.profile.belt_max_mm

        if override is OverrideMode.LOOSEN:
            events.append(self._log(t_s, EventKind.OVERRIDE, "manual LOOSEN engaged"))
            self._reset_episodes()
            return SafetyDecision(loosest, "override: manual loosen", tuple(events))

        if override is OverrideMode.FREEZE:
            events.append(self._log(t_s, EventKind.OVERRIDE, "manual FREEZE engaged"))
            self._reset_episodes()
            return SafetyDecision(current_position_mm, "override: freeze",
                                  tuple(events))

        if estimate.age_s > self.profile.watchdog_s:
            if not self._watchdog_episode:
                events.append(self._log(
                    t_s, EventKind.WATCHDOG,
                    f"estimate stale for {estimate.age_s:.1f}s"))
                self._watchdog_episode = True
            self._low_conf_episode = False
            return SafetyDecision(loosest, "fail-loose: watchdog", tuple(events))

        if estimate.activity is Activity.UNKNOWN:
            # Boot-time UNKNOWN (posture never yet acquired) is not a
            # fault; losing a posture we HAD is.
            if not self._low_conf_episode and estimate.acquired:
                events.append(self._log(
                    t_s, EventKind.LOW_CONFIDENCE,
                    "classifier could not name the posture"))
                self._low_conf_episode = True
            # Policy already commands loose for UNKNOWN; pass it through.
            self._watchdog_episode = False
            return SafetyDecision(command.target_circ_mm, command.reason,
                                  tuple(events))

        if current_tension_n > self.profile.max_tension_n:
            events.append(self._log(
                t_s, EventKind.TENSION_CEILING,
                f"tension {current_tension_n:.1f} N above ceiling "
                f"{self.profile.max_tension_n:.1f} N"))
            self._reset_episodes()
            return SafetyDecision(loosest, "fail-loose: tension ceiling breach",
                                  tuple(events))

        self._reset_episodes()
        return SafetyDecision(command.target_circ_mm, command.reason, tuple(events))

    def _reset_episodes(self) -> None:
        self._watchdog_episode = False
        self._low_conf_episode = False
