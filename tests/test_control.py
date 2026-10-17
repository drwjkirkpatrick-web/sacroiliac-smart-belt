"""Tests for the tension policy and controller (sibelt.control)."""
import pytest

from sibelt.classify import PositionEstimate
from sibelt.control import Command, TensionController, TensionPolicy
from sibelt.models import Activity, WearerProfile, spring_tension_n


def est(activity, t):
    return PositionEstimate(activity=activity, rotation_deg=2.0,
                             confidence=0.9, t_s=t, age_s=0.0)


class TestPolicy:
    def test_target_tensions_per_activity(self):
        p = TensionPolicy(WearerProfile())
        assert p.target_tension_n(Activity.STANDING) == 8.0
        assert p.target_tension_n(Activity.SITTING) == 3.0
        assert p.target_tension_n(Activity.DRIVING) == 3.0
        assert p.target_tension_n(Activity.UNKNOWN) == 0.0


class TestController:
    def test_standing_command_holds_trousers(self):
        c = TensionController(WearerProfile())
        # first stand at t=0: grace; stand settled after the delay
        c.update(est(Activity.STANDING, 0.0), 0.0)
        cmd = c.update(est(Activity.STANDING, 3.0), 3.0)
        assert cmd.target_circ_mm == pytest.approx(870.0)
        assert "hold" in cmd.reason
        # and that command really yields 8 N on the standing body
        assert spring_tension_n(870.0, 880.0, 0.8) == pytest.approx(8.0)

    def test_seated_commands_slack(self):
        c = TensionController(WearerProfile())
        cmd = c.update(est(Activity.SITTING, 5.0), 5.0)
        assert cmd.target_circ_mm == pytest.approx(901.25)
        assert "slack" in cmd.reason
        assert spring_tension_n(cmd.target_circ_mm, 905.0, 0.8) == pytest.approx(3.0)

    def test_driving_same_as_sitting(self):
        c = TensionController(WearerProfile())
        sit = c.update(est(Activity.SITTING, 5.0), 5.0)
        drv = c.update(est(Activity.DRIVING, 6.0), 6.0)
        assert drv.target_circ_mm == pytest.approx(sit.target_circ_mm)

    def test_unknown_is_fully_loose(self):
        c = TensionController(WearerProfile())
        cmd = c.update(est(Activity.UNKNOWN, 1.0), 1.0)
        assert cmd.target_circ_mm == pytest.approx(985.0)
        assert "fail-loose" in cmd.reason

    def test_commands_clamped_to_envelope(self):
        profile = WearerProfile(belt_min_mm=880.0)  # tighter than the 870 target
        c = TensionController(profile)
        c.update(est(Activity.STANDING, 0.0), 0.0)
        cmd = c.update(est(Activity.STANDING, 5.0), 5.0)
        assert cmd.target_circ_mm == profile.belt_min_mm

    def test_retighten_delay_holds_then_releases(self):
        c = TensionController(WearerProfile())
        c.update(est(Activity.UNKNOWN, 0.0), 0.0)
        first = c.update(est(Activity.STANDING, 10.0), 10.0)
        assert "grace" in first.reason
        mid = c.update(est(Activity.STANDING, 11.5), 11.5)
        assert "grace" in mid.reason
        late = c.update(est(Activity.STANDING, 12.5), 12.5)
        assert "hold" in late.reason

    def test_loosening_is_never_delayed(self):
        c = TensionController(WearerProfile())
        c.update(est(Activity.STANDING, 0.0), 0.0)
        c.update(est(Activity.STANDING, 5.0), 5.0)  # settled, holding
        cmd = c.update(est(Activity.SITTING, 6.0), 6.0)
        assert "slack" in cmd.reason  # immediate, no grace on loosening

    def test_delay_reapplies_after_re_sitting(self):
        c = TensionController(WearerProfile())
        c.update(est(Activity.STANDING, 0.0), 0.0)
        c.update(est(Activity.STANDING, 5.0), 5.0)
        c.update(est(Activity.SITTING, 10.0), 10.0)
        grace = c.update(est(Activity.STANDING, 20.0), 20.0)
        assert "grace" in grace.reason

    def test_command_type_immutable(self):
        cmd = Command(870.0, "x")
        with pytest.raises(Exception):
            cmd.target_circ_mm = 1.0
