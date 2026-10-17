"""Tests for profile persistence and calibration (sibelt.profiles)."""
import json

import pytest

from sibelt.models import WearerProfile
from sibelt.profiles import ProfileStore, ValidationError, default_profile


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "profile.json")


class TestRoundTrip:
    def test_missing_file_loads_defaults(self, store):
        assert store.load() == default_profile()

    def test_save_then_load(self, store):
        p = WearerProfile(wearer_id="w-42", c_standing_mm=940.0, delta_sit_mm=30.0)
        store.save(p)
        assert store.load() == p

    def test_unknown_keys_tolerated_on_load(self, store):
        p = default_profile()
        store.save(p)
        raw = json.loads(store.path.read_text())
        raw["bogus_field"] = 1
        store.path.write_text(json.dumps(raw))
        assert store.load() == p

    def test_invalid_json_rejected(self, store):
        store.path.write_text("{not json")
        with pytest.raises(ValidationError):
            store.load()

    def test_non_object_rejected(self, store):
        store.path.write_text("[1, 2, 3]")
        with pytest.raises(ValidationError):
            store.load()

    def test_no_temp_files_left_behind(self, store, tmp_path):
        store.save(default_profile())
        assert list(tmp_path.glob("*.tmp")) == []

    def test_broken_save_leaves_file_untouched(self, store):
        store.save(default_profile())
        before = store.path.read_text()
        with pytest.raises(ValidationError):
            store.save(WearerProfile(c_standing_mm=9999.0))
        assert store.path.read_text() == before


class TestValidation:
    @pytest.mark.parametrize("field,value,fragment", [
        ("c_standing_mm", 2500.0, "c_standing_mm"),
        ("delta_sit_mm", 100.0, "delta_sit_mm"),
        ("stiffness_n_per_mm", 9.0, "stiffness_n_per_mm"),
        ("sitting_tension_n", 20.0, "tension floors"),
        ("max_tension_n", 4.0, "hold <= max_tension"),
        ("belt_max_mm", 880.0, "belt_max_mm"),
        ("hardware_mass_g", 300.0, "lightweight budget"),
        ("ema_alpha", 1.5, "ema_alpha"),
    ])
    def test_envelope_violations(self, store, field, value, fragment):
        with pytest.raises(ValidationError) as excinfo:
            store.save(WearerProfile(**{field: value}))
        assert fragment in str(excinfo.value)

    def test_defaults_are_valid(self, store):
        store.validate(default_profile())  # must not raise


class TestCalibration:
    def test_calibrate_sets_exactly_the_two_fields(self, store):
        store.save(default_profile())
        updated = store.calibrate(910.0, 938.0, wearer_id="wearer-nd")
        assert updated.c_standing_mm == 910.0
        assert updated.delta_sit_mm == 28.0
        assert updated.wearer_id == "wearer-nd"
        # everything else untouched
        base = default_profile()
        assert updated.hold_tension_n == base.hold_tension_n
        assert updated.stiffness_n_per_mm == base.stiffness_n_per_mm

    def test_calibrate_rejects_sitting_smaller_than_standing(self, store):
        with pytest.raises(ValidationError):
            store.calibrate(910.0, 900.0)

    def test_calibrate_rejects_absurd_delta(self, store):
        with pytest.raises(ValidationError):
            store.calibrate(880.0, 1010.0)  # delta 130 > 80 envelope

    def test_calibrate_requires_measured_expansion(self, store):
        # delta below the 5 mm envelope floor is suspicious, not calibratable
        with pytest.raises(ValidationError):
            store.calibrate(900.0, 902.0)
