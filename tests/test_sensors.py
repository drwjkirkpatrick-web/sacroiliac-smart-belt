"""Tests for the sensor layer (sibelt.sensors)."""
import math
import statistics

import pytest

from sibelt.models import Activity
from sibelt.sensors import (
    DEFAULT_ROTATIONS,
    G_MPS2,
    NoSignalIMU,
    ScenarioSegment,
    SensorReading,
    SimulatedIMU,
    rotation_deg_from_gravity,
    total_duration_s,
)


def basic_scenario():
    return [
        ScenarioSegment(Activity.STANDING, 10.0),
        ScenarioSegment(Activity.SITTING, 10.0),
        ScenarioSegment(Activity.DRIVING, 10.0),
    ]


def collect(imu, n):
    out = []
    for _ in range(n):
        r = imu.read()
        if r is None:
            break
        out.append(r)
    return out


class TestDeterminism:
    def test_same_seed_identical_streams(self):
        a = SimulatedIMU(basic_scenario(), seed=42)
        b = SimulatedIMU(basic_scenario(), seed=42)
        ra = collect(a, 200)
        rb = collect(b, 200)
        assert ra == rb

    def test_different_seed_differs(self):
        a = collect(SimulatedIMU(basic_scenario(), seed=1), 100)
        b = collect(SimulatedIMU(basic_scenario(), seed=2), 100)
        assert a != b


class TestGravityEmission:
    def test_standing_components(self):
        readings = collect(SimulatedIMU(basic_scenario(), seed=3, noise_std=0.001), 100)
        mean_ax = statistics.mean(r.ax for r in readings)
        mean_az = statistics.mean(r.az for r in readings)
        theta = math.radians(DEFAULT_ROTATIONS[Activity.STANDING])
        assert mean_ax == pytest.approx(-G_MPS2 * math.sin(theta), abs=0.05)
        assert mean_az == pytest.approx(G_MPS2 * math.cos(theta), abs=0.05)

    def test_rotation_recovery_standing(self):
        imu = SimulatedIMU(basic_scenario(), seed=5)
        vals = [rotation_deg_from_gravity(r.ax, r.az) for r in collect(imu, 200)]
        assert statistics.mean(vals) == pytest.approx(DEFAULT_ROTATIONS[Activity.STANDING], abs=1.0)

    def test_rotation_recovery_driving(self):
        imu = SimulatedIMU(basic_scenario(), seed=5)
        readings = collect(imu, 1450)  # run into the driving segment (t=20-30 s)
        tail = readings[-100:]
        vals = [rotation_deg_from_gravity(r.ax, r.az) for r in tail]
        assert statistics.mean(vals) == pytest.approx(DEFAULT_ROTATIONS[Activity.DRIVING], abs=2.0)


class TestTransitions:
    def test_rotation_bounded_between_targets(self):
        imu = SimulatedIMU(basic_scenario(), seed=9)
        thetas = [rotation_deg_from_gravity(r.ax, r.az) for r in collect(imu, 750)]
        assert min(thetas) >= 0.0
        assert max(thetas) <= DEFAULT_ROTATIONS[Activity.DRIVING] + 2.0

    def test_gyro_carries_transition_rate(self):
        imu = SimulatedIMU(basic_scenario(), seed=11, noise_std=0.001)
        readings = collect(imu, 750)
        peak_gy = max(abs(r.gy) for r in readings)
        assert peak_gy > 0.05  # a real sit-down shows up on the gyro
        steady_tail = readings[-100:]
        assert statistics.mean(abs(r.gy) for r in steady_tail) < 0.02


class TestStreamLifecycle:
    def test_exhausts_after_scenario(self):
        imu = SimulatedIMU(basic_scenario(), seed=13, noise_std=0.001)
        n = len(collect(imu, 100000))
        assert n == round(30.0 / 0.02)
        assert imu.read() is None
        assert imu.has_data is False

    def test_no_signal_imu(self):
        imu = NoSignalIMU()
        assert imu.read() is None
        assert imu.has_data is False

    def test_clock_advances_by_dt(self):
        imu = SimulatedIMU(basic_scenario(), seed=17, noise_std=0.001)
        readings = collect(imu, 10)
        assert [r.t_s for r in readings] == [pytest.approx(i * 0.02) for i in range(10)]

    def test_total_duration_helper(self):
        assert total_duration_s(basic_scenario()) == pytest.approx(30.0)

    def test_empty_scenario_rejected(self):
        with pytest.raises(ValueError):
            SimulatedIMU([])
