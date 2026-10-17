"""Tests for the CLI (sibelt.cli via python -m sibelt)."""
import json
import subprocess
import sys

import pytest


def run_cli(args, stdin=None):
    return subprocess.run([sys.executable, "-m", "sibelt"] + args,
                          capture_output=True, text=True, input=stdin)


class TestSimulate:
    def test_json_output_parses(self):
        r = run_cli(["simulate", "--scenario", "commute",
                     "--time-scale", "0.02", "--json"])
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data["scenario"] == "commute"
        assert "adverse_reduction_pct" in data
        assert data["ticks"] > 0

    def test_text_output_carries_headlines(self):
        r = run_cli(["simulate", "--scenario", "commute",
                     "--time-scale", "0.02"])
        assert r.returncode == 0, r.stderr
        assert "reduction" in r.stdout
        assert "Safety events: 0" in r.stdout

    def test_seed_determinism(self):
        a = run_cli(["simulate", "--scenario", "commute",
                     "--time-scale", "0.02", "--json", "--seed", "11"])
        b = run_cli(["simulate", "--scenario", "commute",
                     "--time-scale", "0.02", "--json", "--seed", "11"])
        assert a.stdout == b.stdout


class TestCalibrate:
    def test_flags_write_profile(self, tmp_path):
        ppath = tmp_path / "p.json"
        r = run_cli(["calibrate", "--standing", "900", "--sitting", "930",
                     "--wearer-id", "w-test", "--profile", str(ppath)])
        assert r.returncode == 0, r.stderr
        data = json.loads(ppath.read_text())
        assert data["c_standing_mm"] == 900.0
        assert data["delta_sit_mm"] == 30.0
        assert data["wearer_id"] == "w-test"

    def test_wizard_over_stdin(self, tmp_path):
        ppath = tmp_path / "p.json"
        r = run_cli(["calibrate", "--profile", str(ppath)],
                    stdin="910\n938\n")
        assert r.returncode == 0, r.stderr
        data = json.loads(ppath.read_text())
        assert data["c_standing_mm"] == 910.0

    def test_rejects_sitting_smaller_than_standing(self, tmp_path):
        r = run_cli(["calibrate", "--standing", "910", "--sitting", "900",
                     "--profile", str(tmp_path / "p.json")])
        assert r.returncode == 2

    def test_rejects_non_numeric_stdin(self, tmp_path):
        r = run_cli(["calibrate", "--profile", str(tmp_path / "p.json")],
                    stdin="abc\ndef\n")
        assert r.returncode == 1


class TestProfile:
    def test_show_prints_json(self, tmp_path):
        ppath = tmp_path / "p.json"
        run_cli(["calibrate", "--standing", "900", "--sitting", "928",
                 "--profile", str(ppath)])
        r = run_cli(["profile", "show", "--profile", str(ppath)])
        assert r.returncode == 0
        assert json.loads(r.stdout)["c_standing_mm"] == 900.0

    def test_validate_detects_broken_file(self, tmp_path):
        ppath = tmp_path / "p.json"
        ppath.write_text("{not json")
        r = run_cli(["profile", "validate", "--profile", str(ppath)])
        assert r.returncode == 2
        assert "invalid" in r.stderr


class TestSelftestAndVersion:
    def test_selftest_exits_ok(self):
        r = run_cli(["selftest"])
        assert r.returncode == 0, r.stderr
        assert "OK" in r.stdout

    def test_version(self):
        r = run_cli(["--version"])
        assert r.returncode == 0
        assert "sibelt" in r.stdout
