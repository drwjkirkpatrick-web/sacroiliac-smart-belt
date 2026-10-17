"""Command-line interface: simulate, calibrate, profile, selftest.

Exit codes: 0 = success; 1 = invalid interactive input; 2 = validation or
argument errors (argparse uses 2 for usage errors as well).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .engine import SCENARIOS, simulate
from .models import WearerProfile, profile_to_dict
from .profiles import ProfileStore, ValidationError

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_VALIDATION = 2


def _default_profile_path() -> Path:
    """Where profiles live when --profile is not given."""
    return Path.home() / ".sibelt" / "profile.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sibelt",
        description="Posture-adaptive belt simulation and control for "
                    "reducing adverse sacroiliac joint loading.")
    parser.add_argument("--version", action="version",
                        version=f"sibelt {__version__}")
    sub = parser.add_subparsers(dest="command")

    sim = sub.add_parser("simulate",
                          help="run the smart-vs-static belt comparison")
    sim.add_argument("--scenario", choices=sorted(SCENARIOS), default="day")
    sim.add_argument("--profile", default=None,
                     help="wearer profile JSON path")
    sim.add_argument("--json", action="store_true",
                     help="machine-readable report")
    sim.add_argument("--seed", type=int, default=7)
    sim.add_argument("--time-scale", type=float, default=1.0,
                     help="compress the day (<1 runs faster, same structure)")

    cal = sub.add_parser("calibrate",
                          help="record standing/seated tape measurements")
    cal.add_argument("--standing", type=float, default=None,
                     help="standing pelvic circumference in mm")
    cal.add_argument("--sitting", type=float, default=None,
                     help="seated pelvic circumference in mm")
    cal.add_argument("--wearer-id", default=None,
                     help="opaque wearer label (no PII)")
    cal.add_argument("--profile", default=None)

    prof = sub.add_parser("profile", help="show or validate a profile")
    prof.add_argument("action", choices=["show", "validate"])
    prof.add_argument("--profile", default=None)

    sub.add_parser("selftest", help="import every layer and run a tiny loop")
    return parser


def run_selftest() -> bool:
    """Wiring check: imports every layer and runs a small end-to-end loop."""
    report = simulate(WearerProfile(), "commute", seed=1, time_scale=0.05)
    ok = report.ticks > 0 and report.reduction_pct > 0
    state = "OK" if ok else "FAILED"
    print(f"selftest: {report.ticks} ticks, adverse reduction "
          f"{report.reduction_pct:.1f}% -> {state}")
    return ok


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_INPUT

    profile_path = (Path(args.profile) if getattr(args, "profile", None)
                    else _default_profile_path())

    try:
        if args.command == "simulate":
            profile = ProfileStore(profile_path).load()
            report = simulate(profile, args.scenario, seed=args.seed,
                              time_scale=args.time_scale)
            if args.json:
                print(report.to_json())
            else:
                print(report.render_text())
            return EXIT_OK

        if args.command == "calibrate":
            standing, sitting = args.standing, args.sitting
            if standing is None or sitting is None:
                try:
                    standing = float(input(
                        "Standing pelvic circumference (mm): "))
                    sitting = float(input(
                        "Seated pelvic circumference (mm): "))
                except (EOFError, ValueError):
                    print("calibrate: two numeric measurements are required",
                          file=sys.stderr)
                    return EXIT_INPUT
            store = ProfileStore(profile_path)
            profile = store.calibrate(standing, sitting,
                                       wearer_id=args.wearer_id)
            store.save(profile)
            print(f"calibrated profile saved to {profile_path}")
            print(f"  standing {profile.c_standing_mm:.0f} mm, "
                  f"seated +{profile.delta_sit_mm:.0f} mm")
            return EXIT_OK

        if args.command == "profile":
            store = ProfileStore(profile_path)
            if args.action == "show":
                print(json.dumps(profile_to_dict(store.load()), indent=2))
                return EXIT_OK
            try:
                store.load()
                print("profile valid")
                return EXIT_OK
            except ValidationError as exc:
                print(f"profile invalid: {exc}", file=sys.stderr)
                return EXIT_VALIDATION

        if args.command == "selftest":
            return EXIT_OK if run_selftest() else EXIT_VALIDATION

    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_VALIDATION

    return EXIT_INPUT
