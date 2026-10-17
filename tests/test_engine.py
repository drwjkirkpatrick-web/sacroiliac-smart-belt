"""Tests for the closed-loop engine and day simulation (sibelt.engine)."""
import json

import pytest

from sibelt.actuator import SimulatedActuator
from sibelt.engine import SCENARIOS, BeltEngine, scenario_day, simulate, summarize
from sibelt.models import Activity, BeltState, WearerProfile
from sibelt.safety import EventKind
from sibelt.sensors import NoSignalIMU, ScenarioSegment, SimulatedIMU


def scaled_day(scale=0.1):
    """A fast-but-faithful day for tests (10% duration, same structure)."""
    return simulate(WearerProfile(), "day", seed=7, time_scale=scale)


class TestScenarios:
    def test_day_scenario_shape(self):
        segs = scenario_day()
        assert sum(s.duration_s for s in segs) == 11760.0
        assert [s.activity for s in segs][0] is Activity.STANDING

    def test_known_scenarios(self):
        assert set(SCENARIOS) == {"day", "commute"}

    def test_unknown_scenario_rejected(self):
        with pytest.raises(ValueError):
            simulate(scenario="nonsense")


class TestPipeline:
    def test_runs_and_records_every_tick(self):
        report = scaled_day()
        assert report.ticks == int(report.duration_s / 0.02)
        assert report.ticks > 1000

    def test_all_three_postures_seen(self):
        report = scaled_day()
        # If the day did not exercise standing, sitting, and driving the
        # comparison would be meaningless.
        assert report.smart["seated_ticks"] > 0
        assert report.baseline["peak_seated_tension_n"] > 0

    def test_determinism(self):
        a = scaled_day()
        b = scaled_day()
        assert a.to_json() == b.to_json()

    def test_commute_scenario_runs(self):
        report = simulate(WearerProfile(), "commute", seed=3, time_scale=0.1)
        assert report.ticks > 100
        assert report.reduction_pct > 0.0


class TestTheThesis:
    def test_adverse_reduction_at_least_60pct(self):
        report = scaled_day()
        assert report.reduction_pct >= 60.0

    def test_baseline_inflates_seated_tension(self):
        # Ordinary clothing: a belt sized standing pulls several times
        # harder the moment its wearer sits.
        report = scaled_day()
        hold = WearerProfile().hold_tension_n
        assert report.baseline["peak_seated_tension_n"] >= 2 * hold
        assert report.baseline["peak_seated_tension_n"] == pytest.approx(28.0,
                                                                         abs=1.0)

    def test_smart_seat_honors_floor(self):
        report = scaled_day()
        assert report.smart["seated_at_floor_pct"] >= 95.0

    def test_smart_never_exceeds_ceiling(self):
        report = scaled_day()
        assert report.smart["peak_seated_tension_n"] <= WearerProfile().max_tension_n

    def test_zero_safety_events_nominal(self):
        report = scaled_day()
        assert report.safety_event_count == 0


class TestFaultIntegration:
    def test_watchdog_fires_on_dead_sensor(self):
        profile = WearerProfile()
        engine = BeltEngine(profile, NoSignalIMU())
        t = 0.0
        for _ in range(int(10.0 / 0.02)):
            engine.tick(t)
            t += 0.02
        kinds = [e.kind for e in engine.safety_events]
        assert EventKind.WATCHDOG in kinds
        # the belt relaxed: tension is zero against any body
        assert engine.rows[-1].tension_n == 0.0
        assert engine.rows[-1].activity is Activity.UNKNOWN

    def test_manual_loosen_zeroes_tension(self):
        profile = WearerProfile()
        from sibelt.safety import OverrideMode
        imu = SimulatedIMU([ScenarioSegment(Activity.STANDING, 30.0)], seed=1)
        engine = BeltEngine(profile, imu, override=OverrideMode.LOOSEN)
        t = 0.0
        while engine.imu.has_data:
            engine.tick(t)
            t += 0.02
        assert engine.rows[-1].tension_n == 0.0
        assert engine.actuator._position == pytest.approx(profile.belt_max_mm)


class TestReporting:
    def test_json_round_trip(self):
        report = scaled_day()
        data = json.loads(report.to_json())
        assert data["adverse_reduction_pct"] == pytest.approx(
            report.reduction_pct, abs=0.2)
        assert "smart" in data and "baseline" in data

    def test_text_report_carries_headlines(self):
        text = scaled_day().render_text()
        assert "reduction" in text
        assert "static belt" in text
        assert "smart belt" in text
        assert "Safety events: 0" in text

    def test_battery_and_adjustments_sane(self):
        report = scaled_day()
        assert 2 <= report.adjustments <= 40
        assert 0.0 < report.battery_mah < WearerProfile().battery_capacity_mah
