"""Tests for the actuator layer (sibelt.actuator)."""
import pytest

from sibelt.actuator import SimulatedActuator
from sibelt.models import WearerProfile


def act(profile=None):
    return SimulatedActuator(profile or WearerProfile())


class TestMovement:
    def test_starts_loose(self):
        a = act()
        assert a._position == WearerProfile().belt_max_mm

    def test_moves_at_rate_limit(self):
        a = act()  # starts at 985
        a.command(870.0, 0.0)  # 115 mm away
        st = a.step(0.02)
        assert st.position_mm == pytest.approx(985.0 - 40.0 * 0.02)  # 40 mm/s
        assert st.moving

    def test_arrives_exactly(self):
        a = act()
        a.command(980.0, 0.0)
        for _ in range(100):
            st = a.step(0.02)
            if not st.moving:
                break
        assert st.position_mm == pytest.approx(980.0)
        assert not st.moving

    def test_envelope_is_hard(self):
        a = act()
        a.command(400.0, 0.0)  # absurdly tight
        for _ in range(500):
            st = a.step(0.02)
        assert st.position_mm == a.profile.belt_min_mm
        a.command(5000.0, 1.0)  # absurdly loose
        for _ in range(500):
            st = a.step(0.02)
        assert st.position_mm == a.profile.belt_max_mm

    def test_zero_dt_is_safe(self):
        a = act()
        a.command(870.0, 0.0)
        st = a.step(0.0)
        assert st.position_mm == pytest.approx(985.0)


class TestAccounting:
    def test_motor_time_only_when_moving(self):
        a = act()
        a.command(985.0, 0.0)  # already there
        for _ in range(100):
            st = a.step(0.02)
        assert st.motor_on_s == 0.0

    def test_motor_time_matches_travel(self):
        a = act()
        a.command(865.0, 0.0)  # exactly 120 mm of travel
        for _ in range(400):
            st = a.step(0.02)
            if not st.moving:
                break
        assert st.motor_on_s == pytest.approx(120.0 / 40.0)

    def test_adjustments_count_target_changes_not_ticks(self):
        a = act()
        for _ in range(50):
            a.command(870.0, 0.0)
        assert a.step(0.02).adjustments == 1
        a.command(875.0, 1.0)
        for _ in range(50):
            a.command(875.0, 1.0)
        assert a.step(0.02).adjustments == 2


class TestTensionInterface:
    def test_tension_at_position(self):
        a = act(profile=WearerProfile(belt_max_mm=871.0))
        a.command(870.0, 0.0)
        for _ in range(500):
            st = a.step(0.02)
            if not st.moving:
                break
        assert a.tension_n(880.0) == pytest.approx(8.0)

    def test_tension_zero_when_loose(self):
        a = act()
        assert a.tension_n(880.0) == 0.0  # belt at 985, body 880

    def test_battery_arithmetic(self):
        a = act()
        a.command(870.0, 0.0)  # 115 mm -> 2.875 s motor time
        for _ in range(1000):
            st = a.step(0.02)
            if not st.moving:
                break
        used = a.battery_mah_used(duration_s=3600.0)
        motor = 2.875 / 3600.0 * 0.15 * 1000.0
        system = 3600.0 / 3600.0 * 0.5
        assert used == pytest.approx(motor + system, rel=0.01)
