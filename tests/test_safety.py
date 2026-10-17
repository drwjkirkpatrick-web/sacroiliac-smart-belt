"""Tests for the fail-loose safety layer (sibelt.safety)."""
import pytest

from sibelt.classify import PositionEstimate
from sibelt.control import Command
from sibelt.models import Activity, WearerProfile
from sibelt.safety import (
    EventKind,
    OverrideMode,
    SafetyDecision,
    SafetyEvent,
    SafetyMonitor,
)


def standing_est(t, age=0.0):
    return PositionEstimate(Activity.STANDING, 2.0, 0.9, t, age)


def policy_cmd():
    return Command(870.0, "hold: keep trousers up while standing")


def monitor():
    return SafetyMonitor(WearerProfile())


class TestHealthyPath:
    def test_passthrough_when_healthy(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(1.0), 8.0, OverrideMode.NONE,
                      1.0, 870.0)
        assert d.command_mm == 870.0
        assert d.events == ()
        assert m.events == []

    def test_ceiling_boundary_is_strict(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(1.0), 30.0, OverrideMode.NONE,
                      1.0, 870.0)
        assert d.command_mm == 870.0  # exactly at ceiling: fine
        assert d.events == ()


class TestOverrides:
    def test_freeze_holds_position(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(1.0), 8.0, OverrideMode.FREEZE,
                      1.0, 930.0)
        assert d.command_mm == 930.0
        assert "freeze" in d.reason

    def test_loosen_opens_fully(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(1.0), 8.0, OverrideMode.LOOSEN,
                      1.0, 870.0)
        assert d.command_mm == WearerProfile().belt_max_mm
        assert "manual loosen" in d.reason

    def test_loosen_outranks_stale_watchdog(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(10.0, age=10.0), 8.0,
                      OverrideMode.LOOSEN, 10.0, 870.0)
        assert "override" in d.reason  # not the watchdog reason

    def test_freeze_outranks_watchdog(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(10.0, age=10.0), 8.0,
                      OverrideMode.FREEZE, 10.0, 905.0)
        assert "freeze" in d.reason


class TestFaults:
    def test_watchdog_fires_on_stale_estimate(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(10.0, age=10.0), 8.0,
                      OverrideMode.NONE, 10.0, 870.0)
        assert d.command_mm == WearerProfile().belt_max_mm
        assert d.events[0].kind is EventKind.WATCHDOG

    def test_watchdog_logs_once_per_episode(self):
        m = monitor()
        for _ in range(5):
            d = m.enforce(policy_cmd(), standing_est(10.0, age=10.0), 8.0,
                          OverrideMode.NONE, 10.0, 870.0)
        assert len(m.events) == 1

    def test_ceiling_breach_relaxes(self):
        m = monitor()
        d = m.enforce(policy_cmd(), standing_est(1.0), 33.0, OverrideMode.NONE,
                      1.0, 870.0)
        assert d.command_mm == WearerProfile().belt_max_mm
        assert d.events[0].kind is EventKind.TENSION_CEILING

    def test_unknown_fresh_goes_loose_via_policy(self):
        m = monitor()
        est = PositionEstimate(Activity.UNKNOWN, 0.0, 0.0, 1.0, 0.0)
        d = m.enforce(Command(985.0, "fail-loose: posture unknown"), est, 0.0,
                      OverrideMode.NONE, 1.0, 985.0)
        assert d.command_mm == 985.0
        assert d.events[0].kind is EventKind.LOW_CONFIDENCE

    def test_low_confidence_logs_once_per_episode(self):
        m = monitor()
        est = PositionEstimate(Activity.UNKNOWN, 0.0, 0.0, 1.0, 0.0)
        cmd = Command(985.0, "fail-loose: posture unknown")
        for _ in range(4):
            d = m.enforce(cmd, est, 0.0, OverrideMode.NONE, 1.0, 985.0)
        assert len([e for e in m.events
                    if e.kind is EventKind.LOW_CONFIDENCE]) == 1

    def test_recovers_after_stale_episode(self):
        m = monitor()
        m.enforce(policy_cmd(), standing_est(10.0, age=10.0), 8.0,
                  OverrideMode.NONE, 10.0, 870.0)
        d = m.enforce(policy_cmd(), standing_est(11.0, age=0.1), 8.0,
                      OverrideMode.NONE, 11.0, 870.0)
        assert d.command_mm == 870.0
        # a SECOND stale episode logs again
        m.enforce(policy_cmd(), standing_est(20.0, age=10.0), 8.0,
                  OverrideMode.NONE, 20.0, 870.0)
        assert len([e for e in m.events
                    if e.kind is EventKind.WATCHDOG]) == 2


class TestTypes:
    def test_decision_is_immutable(self):
        d = SafetyDecision(1.0, "x", ())
        with pytest.raises(Exception):
            d.command_mm = 2.0

    def test_event_is_immutable(self):
        e = SafetyEvent(1.0, EventKind.WATCHDOG, "x")
        with pytest.raises(Exception):
            e.kind = EventKind.OVERRIDE
