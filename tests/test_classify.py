"""Tests for the posture classifier (sibelt.classify)."""
import math

import pytest

from sibelt.classify import PostureClassifier, PositionEstimate
from sibelt.models import Activity, WearerProfile
from sibelt.sensors import ScenarioSegment, SensorReading, SimulatedIMU

G = 9.81
DT = 0.02


def reading_at(t, deg):
    """Synthetic reading with a given true pelvic rotation."""
    rad = math.radians(deg)
    return SensorReading(t_s=t, ax=-G * math.sin(rad), ay=0.0,
                         az=G * math.cos(rad), gx=0.0, gy=0.0, gz=0.0)


def feed_standing(cls, t_start, seconds):
    t = t_start
    n = int(seconds / DT)
    last = None
    for _ in range(n):
        last = cls.update(reading_at(t, 2.0), t)
        t += DT
    return last, t


class TestAcquisition:
    def test_startup_is_unknown(self):
        cls = PostureClassifier(WearerProfile())
        est = cls.update(None, 0.0)
        assert est.activity is Activity.UNKNOWN
        assert est.confidence == 0.0

    def test_standing_acquired_after_debounce(self):
        cls = PostureClassifier(WearerProfile())
        est, _ = feed_standing(cls, 0.0, 3.0)
        assert est.activity is Activity.STANDING
        # and it needed the debounce window, not one frame
        assert cls.switch_count == 1


class TestScenarioClassification:
    def test_sitdown_detected_within_window(self):
        profile = WearerProfile()
        imu = SimulatedIMU([ScenarioSegment(Activity.STANDING, 10.0),
                            ScenarioSegment(Activity.SITTING, 10.0)], seed=5)
        cls = PostureClassifier(profile)
        t = 0.0
        seen = {}
        while imu.has_data:
            est = cls.update(imu.read(), t)
            seen.setdefault(est.activity, t)
            t += DT
        assert Activity.SITTING in seen
        assert seen[Activity.SITTING] <= 13.5  # change at 10 + transition + debounce

    def test_driving_recognized(self):
        imu = SimulatedIMU([ScenarioSegment(Activity.STANDING, 10.0),
                            ScenarioSegment(Activity.SITTING, 10.0),
                            ScenarioSegment(Activity.DRIVING, 10.0)], seed=5)
        cls = PostureClassifier(WearerProfile())
        t = 0.0
        seen = {}
        while imu.has_data:
            est = cls.update(imu.read(), t)
            seen.setdefault(est.activity, t)
            t += DT
        assert Activity.DRIVING in seen
        assert seen[Activity.DRIVING] <= 24.5

    def test_not_sitting_mid_transition(self):
        imu = SimulatedIMU([ScenarioSegment(Activity.STANDING, 10.0),
                            ScenarioSegment(Activity.SITTING, 10.0)], seed=5)
        cls = PostureClassifier(WearerProfile())
        t = 0.0
        est = None
        while t < 10.5:
            est = cls.update(imu.read(), t)
            t += DT
        assert est.activity is Activity.STANDING  # sit-down just began


class TestStability:
    def test_single_frame_spike_suppressed(self):
        cls = PostureClassifier(WearerProfile())
        feed_standing(cls, 0.0, 5.0)
        t = 5.0
        cls.update(reading_at(t, 15.0), t)  # one stray "sitting" frame
        est, _ = feed_standing(cls, t + DT, 2.0)
        assert est.activity is Activity.STANDING
        assert cls.switch_count == 1  # only the initial acquisition

    def test_no_flapping_under_noise(self):
        imu = SimulatedIMU([ScenarioSegment(Activity.STANDING, 60.0)], seed=99,
                           noise_std=0.04)
        cls = PostureClassifier(WearerProfile())
        t = 0.0
        est = None
        while imu.has_data:
            est = cls.update(imu.read(), t)
            t += DT
        assert est.activity is Activity.STANDING
        assert cls.switch_count <= 1

    def test_confidence_bounds_always(self):
        imu = SimulatedIMU([ScenarioSegment(Activity.STANDING, 10.0),
                            ScenarioSegment(Activity.SITTING, 10.0),
                            ScenarioSegment(Activity.DRIVING, 10.0)], seed=5)
        cls = PostureClassifier(WearerProfile())
        t = 0.0
        while imu.has_data:
            est = cls.update(imu.read(), t)
            assert 0.0 <= est.confidence <= 1.0
            assert -0.5 <= est.rotation_deg <= 45.0
            t += DT


class TestStaleness:
    def test_stale_input_goes_unknown(self):
        cls = PostureClassifier(WearerProfile())
        feed_standing(cls, 0.0, 3.0)
        t = 3.0
        est = None
        for _ in range(int(5.0 / DT)):  # 5 s of silence
            est = cls.update(None, t)
            t += DT
        assert est.activity is Activity.UNKNOWN
        assert est.confidence == 0.0
        assert est.age_s >= 5.0 - DT

    def test_recovers_after_stale(self):
        cls = PostureClassifier(WearerProfile())
        feed_standing(cls, 0.0, 3.0)
        t = 3.0
        for _ in range(int(5.0 / DT)):
            cls.update(None, t)
            t += DT
        est, _ = feed_standing(cls, t, 2.0)
        assert est.activity is Activity.STANDING


class TestCustomization:
    def test_priors_come_from_profile(self):
        profile = WearerProfile(rotation_standing_deg=5.0,
                                rotation_sitting_deg=20.0,
                                rotation_driving_deg=30.0)
        cls = PostureClassifier(profile)
        t = 0.0
        est = None
        for _ in range(int(4.0 / DT)):
            est = cls.update(reading_at(t, 20.5), t)  # closest to the 20 deg prior
            t += DT
        assert est.activity is Activity.SITTING
