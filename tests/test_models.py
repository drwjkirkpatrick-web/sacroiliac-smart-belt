"""Tests for the biomechanical core (sibelt.models).

Strategy: verify PROPERTIES of the physics (slack, monotonicity,
projection conservation) instead of golden values, plus a few pinned
numbers where the default profile locks the headline scenario (a
standing-fit belt becomes several times tighter when seated).
"""
import pytest

from sibelt.models import (
    Activity,
    BeltState,
    WearerProfile,
    belt_circumference_for_tension,
    circumference_mm,
    estimate_si_load,
    profile_from_dict,
    profile_to_dict,
    rotation_deg_for,
    sanity_errors,
    spring_tension_n,
)


def default():
    return WearerProfile()


class TestActivity:
    def test_members(self):
        assert {a.name for a in Activity} == {"STANDING", "SITTING", "DRIVING", "UNKNOWN"}

    def test_values_are_json_friendly(self):
        assert Activity.SITTING.value == "sitting"


class TestSpringModel:
    def test_zero_when_slack(self):
        # Belt bigger than body -> it cannot push -> zero tension.
        assert spring_tension_n(belt_circ_mm=900, wearer_circ_mm=880,
                                stiffness_n_per_mm=0.8) == 0.0

    def test_linear_in_zone(self):
        assert spring_tension_n(870, 880, 0.8) == pytest.approx(8.0)

    def test_monotonic_in_wearer_circumference(self):
        tensions = [spring_tension_n(860, c, 0.8) for c in range(850, 1000, 10)]
        assert tensions == sorted(tensions)

    def test_monotonic_in_belt_circumference(self):
        tensions = [spring_tension_n(b, 900, 0.8) for b in range(900, 850, -10)]
        assert tensions == sorted(tensions)

    def test_inverse_round_trip(self):
        for t in (0.0, 3.0, 8.0, 15.0):
            b = belt_circumference_for_tension(t, 905.0, 0.8)
            assert spring_tension_n(b, 905.0, 0.8) == pytest.approx(t)


class TestBodyGeometry:
    def test_circumference_per_activity(self):
        p = default()
        assert circumference_mm(p, Activity.STANDING) == 880.0
        assert circumference_mm(p, Activity.SITTING) == 905.0
        assert circumference_mm(p, Activity.DRIVING) == 905.0

    def test_unknown_is_treated_as_seated(self):
        # Cautious default: unknown posture assumes the larger body.
        assert circumference_mm(default(), Activity.UNKNOWN) == 905.0

    def test_rotation_priors(self):
        p = default()
        assert rotation_deg_for(p, Activity.STANDING) == 2.0
        assert rotation_deg_for(p, Activity.SITTING) == 15.0
        assert rotation_deg_for(p, Activity.DRIVING) == 25.0
        assert rotation_deg_for(p, Activity.UNKNOWN) == 15.0


class TestSIJointLoad:
    def test_standing_dominated_by_closure(self):
        load = estimate_si_load(tension_n=8.0, rotation_deg=2.0)
        assert load.closure_n > load.adverse_n * 10

    def test_adverse_grows_with_rotation(self):
        vals = [estimate_si_load(10.0, deg).adverse_n for deg in (0, 15, 25, 45)]
        assert vals == sorted(vals) and vals[0] == 0.0

    def test_zero_tension_gives_zero_load(self):
        load = estimate_si_load(0.0, 15.0)
        assert load.closure_n == 0.0 and load.adverse_n == 0.0

    def test_projection_conserves_magnitude(self):
        # cos^2 + sin^2 = 1 -> the projection must return exactly the tension.
        for deg in (0, 2, 15, 25, 45, 90):
            load = estimate_si_load(12.0, deg)
            assert load.total_n == pytest.approx(12.0)

    def test_rotation_clamped(self):
        assert estimate_si_load(10.0, -5).adverse_n == 0.0
        ninety = estimate_si_load(10.0, 120.0)
        assert ninety.closure_n == pytest.approx(0.0, abs=1e-9)
        assert ninety.adverse_n == pytest.approx(10.0)

    def test_headline_scenario_static_belt_inflates_seated(self):
        # The user's scenario, pinned: a belt fitted at 8 N standing pulls
        # 3.5x harder the moment the wearer sits down.
        p = default()
        b_standing_fit = belt_circumference_for_tension(p.hold_tension_n,
                                                        p.c_standing_mm,
                                                        p.stiffness_n_per_mm)
        seated_tension = spring_tension_n(b_standing_fit,
                                          circumference_mm(p, Activity.SITTING),
                                          p.stiffness_n_per_mm)
        assert seated_tension == pytest.approx(28.0)
        assert seated_tension >= 3 * p.hold_tension_n


class TestProfile:
    def test_defaults_pass_sanity(self):
        assert sanity_errors(default()) == []

    def test_round_trip(self):
        p = WearerProfile(wearer_id="wearer-b", c_standing_mm=940.0,
                          delta_sit_mm=30.0, hold_tension_n=7.5)
        assert profile_from_dict(profile_to_dict(p)) == p

    def test_from_dict_ignores_unknown_keys(self):
        d = profile_to_dict(default())
        d["bogus_future_field"] = 42
        assert profile_from_dict(d) == default()

    def test_sanity_catches_envelope_violations(self):
        bad = WearerProfile(c_standing_mm=2500.0)
        assert any("c_standing_mm" in e for e in sanity_errors(bad))
        bad = WearerProfile(delta_sit_mm=100.0)
        assert any("delta_sit_mm" in e for e in sanity_errors(bad))
        bad = WearerProfile(sitting_tension_n=10.0, hold_tension_n=8.0)
        assert any("tension floors" in e for e in sanity_errors(bad))
        bad = WearerProfile(belt_max_mm=900.0)
        assert any("belt_max_mm" in e for e in sanity_errors(bad))

    def test_beltstate_to_dict(self):
        st = BeltState(t_s=1.5, activity=Activity.SITTING, belt_circ_mm=901.0,
                       tension_n=3.0, si_load=estimate_si_load(3.0, 15.0))
        d = st.to_dict()
        assert d["activity"] == "sitting"
        assert set(d) == {"t_s", "activity", "belt_circ_mm", "tension_n",
                          "closure_n", "adverse_n"}
