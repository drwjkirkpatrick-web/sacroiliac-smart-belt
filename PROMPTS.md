# Sacroiliac Smart Belt — Ten Build Prompts

**Project:** `sacroiliac-smart-belt` — a lightweight, posture-adaptive belt that
adjusts its own circumference to reduce adverse pressure on the sacroiliac
joints (SIJs), built as a Python simulation and control stack (CLI, stdlib-only,
hardware-swappable).

**The problem it models.** Ligamentous laxity and prior trauma (e.g., motor
vehicle collisions, which can leave posttraumatic arthritis of the SI
joints[3]) can produce lifelong SIJ pain. Sacroiliac joint pain is a common
cause of low back pain, accounting for roughly 15–30% of cases[1], with
estimates around 10–25% for SIJ dysfunction as a primary pain source[2].
For these wearers, *ordinary clothing is the hazard*: a belt sized to hold up
trousers while standing has a smaller circumference than the pelvis presents
when its owner sits down — lower-body circumferences measurably increase with
the switch from standing to sitting[11], and the pelvis tends to move backward
from standing to sitting[24]. The result is a belt that was comfortable at
9 a.m. applying a sharply different directional load across the SIJs an hour
later in the car — precisely the situation this project attacks.

**Why a belt at all is the right tool.** Belts are not a hack; they are the
recognized conservative therapy. A pelvic belt worn with a small force can
generate a self-bracing effect at the SIJ (Snijders et al., 1993)[19], belt
application significantly reduces SIJ mobility (Vleeming et al., 1992)[19],
pelvic belts may be beneficial in affected postpartum patients[3], belting is
a standard nonoperative option for SIJ pain[10], and in a manual-labor trial,
spine pain increased only 0.2 on the NRS during the week participants used a
Serola belt versus 0.9 without it[8]. Critically, Damen's work on healthy young
women showed a pelvic belt is most effective in a high position, while a
tension of 100 N does not reduce SIJ laxity more than 50 N[4] — more tension is
*not* more stabilization. That is the license for this project's central move:
a belt that *loosens* when the wearer sits loses nothing therapeutically, and
escapes the sitting-induced over-tension entirely.

**Prior art.** A motorized consumer "smart belt" (Belty) that self-adjusts
tightness was demonstrated as early as 2015[16]; what it did not have is a
clinical rationale, a posture-aware control policy, per-wearer customization,
or a fail-loose safety architecture — the contributions of this project.

**Sensing.** Waist-worn accelerometers are standard for activity assessment,
though thigh-worn inclinometry distinguishes sitting from light activity more
cleanly — waist-worn devices need careful filtering and hysteresis to classify
posture reliably[23]. Wearable technology is a promising alternative to
laboratory systems for movement and posture analysis[13]. The design answers
that caveat with debounced, hysteresis-bounded state estimation, and treats
SITTING/DRIVING confusion as low-stakes (both get slack targets).

---

## Design overview

```
 +---------+     +------------------+     +----------------+     +---------+
 |   IMU   | --> | Posture          | --> | Tension policy  |--> | Safety  |
 |(6-axis) |     | classifier       |     | (per-activity   |   | layer   |
 +---------+     | (debounce +      |     |  circumference  |   |(fail-   |
                  |  hysteresis)     |     |  targets)       |   | loose)  |
                  +------------------+     +----------------+     +---+-----+
                                                                     |
                                                                     v
                                                                +---------+
                                                                | Actuator|
                                                                |(rate-   |
                                                                | limited)|
                                                                +---------+
```

- **Lightweight**: no phone, no cloud. A 6-axis IMU + microcontroller + micro
  actuator; the simulation carries an explicit mass and battery budget.
- **Posture-adaptive**: standing keeps trouser-holding tension; sitting and
  driving relax the belt so the seated pelvis is not over-compressed.
- **Customizable**: every wearer-dependent number (circumferences, stiffness,
  tension targets, timing) lives in a JSON profile with a calibration wizard.
- **Fail-loose**: any fault (sensor loss, watchdog timeout, low confidence)
  relaxes the belt. A loose belt cannot over-compress an SIJ; sagging trousers
  are a cosmetic failure, not a clinical one.

## Non-goals

- Not a medical device; no diagnosis. Simulation + control design with a
  clinical disclaimer. No PII: profiles store an opaque `wearer_id` only.

---

## Prompt 1 — Biomechanical core: domain models

**Files:** `sibelt/__init__.py`, `sibelt/models.py`, `tests/test_models.py`

**Spec.**
- `Activity` enum: `STANDING`, `SITTING`, `DRIVING`, `UNKNOWN`.
- `WearerProfile` dataclass with defaults: standing pelvic circumference
  `c_standing_mm=880`, sitting increase `delta_sit_mm=25` (grounded
  qualitatively in [11]; wearer-specific → calibration), belt stiffness
  `stiffness_n_per_mm=0.8` (engineering assumption), trouser-hold tension
  `hold_tension_n=8.0`, seated floor tension `sitting_tension_n=3.0`, safety
  ceiling `max_tension_n=30.0`, posterior pelvic-rotation priors per activity
  (standing 2°, sitting 15°, driving 25° — direction grounded in [24],
  magnitudes are first-order engineering assumptions).
- `circumference_mm(profile, activity)` — pelvic circumference per activity.
- `spring_tension_n(belt_circ_mm, wearer_circ_mm, stiffness)`:
  `T = k · max(0, C_wearer − B)` — a belt can pull, never push.
- `SIJointLoad` dataclass + `estimate_si_load(tension_n, rotation_deg)`:
  beneficial force-closure component `T · cos(θ)` and adverse directional
  component `T · sin(θ)`. Documented as a first-order projection of belt force
  onto SIJ axes as the pelvis rotates; used for *relative* comparisons between
  belt strategies, not absolute diagnosis.
- All functions pure, no module-level state, math-annotated.

**Acceptance.** Tension is zero when the belt is slack, monotone in wearer
circumference; adverse load grows with both tension and rotation; standing
loads are dominated by closure; defaults round-trip through `asdict`.

**Tests (~14).** Spring model (slack, linear zone, monotonicity, zero when
B ≥ C), circumference per activity, SIJ load components at 0°/90°, ceiling
clamping helper, profile defaults sane (`min < max`, positive stiffness), all
enums importable, `to_dict`/`from_dict` round-trip.

**Commit:** `Prompt 1: biomechanical core domain models`

---

## Prompt 2 — Sensor layer and simulated IMU

**Files:** `sibelt/sensors.py`, `tests/test_sensors.py`

**Spec.**
- `SensorReading` frozen dataclass: `t_s, ax, ay, az, gx, gy, gz` (m/s², rad/s).
- `IMU` abstract base: `read() -> Optional[SensorReading]`, `has_data`.
- `ScenarioSegment` (`activity`, `duration_s`, optional `transition_s=1.5`).
- `SimulatedIMU(scenario, seed, dt=0.02, noise_std=0.04)`:
  - Builds pelvic-rotation trajectory θ(t) per segment, interpolating smoothly
    across transitions.
  - Emits gravity components `ax = −g·sin(θ)`, `az = g·cos(θ)` (sensor at the
    right iliac crest, z down, x ventral) plus seeded Gaussian noise and small
    gyro pulses during transitions.
  - Deterministic for a given seed; `read()` returns `None` only if the
    harness injects a dropout.
- `StaticBelt`... not here — sensor only. A `NoSignalIMU` that returns `None`
  (used by safety tests).

**Acceptance.** Deterministic replay; pitch recoverable from the gravity vector
via the inverse of the emission formula; scenario duration respected.

**Tests (~10).** Determinism (two IMUs, same seed → identical streams), pitch
recovery error < 2° at steady state, transition interpolation bounded, noise
seeded, `None` on `NoSignalIMU`, segment coverage, reading rate.

**Commit:** `Prompt 2: sensor abstraction and simulated IMU`

---

## Prompt 3 — Posture classifier

**Files:** `sibelt/classify.py`, `tests/test_classify.py`

**Spec.**
- `PositionEstimate` dataclass: `activity`, `rotation_deg`, `confidence`,
  `t_s`, `age_s`.
- `PostureClassifier(profile, debounce_s=1.0, ema_alpha=0.15, stale_s=3.0)`:
  - Recovers θ from each reading (EMA-filtered).
  - Candidate activity = nearest rotation prior (standing/sitting/driving).
  - Debounce: a candidate different from the current activity must persist
    `debounce_s` before the switch commits (no flapping at boundaries[23] is
    the design answer to the waist-worn caveat).
  - Confidence = `1 − normalized distance to the chosen prior`, and drops to
    0 / activity `UNKNOWN` when the estimate is stale (> `stale_s` since last
    reading) or confidence < 0.35.
  - SITTING↔DRIVING confusion is deliberately low-stakes (both get slack
    targets) — document this graceful-degradation choice.

**Acceptance.** Standing→sitting detected within `debounce_s + 1 s` of the
physical transition; zero spurious switches under seeded noise; stale input →
`UNKNOWN`.

**Tests (~10).** Detection latency, debounce suppresses single-frame spikes,
no flapping in a noisy standing hold, stale → UNKNOWN, confidence bounds,
driving recognized at 25°, priors configurable per profile.

**Commit:** `Prompt 3: posture classifier with debounce and hysteresis`

---

## Prompt 4 — Tension policy and controller

**Files:** `sibelt/control.py`, `tests/test_control.py`

**Spec.**
- `TensionPolicy(profile)`: per-activity target *tension*: STANDING →
  `hold_tension_n` (holds trousers), SITTING/DRIVING → `sitting_tension_n`
  (floor, near slack), UNKNOWN → 0 (loose). Rationale grounded in [4]: since
  extra tension buys no extra laxity reduction, seated slack costs nothing.
- `TensionController(profile, retighten_delay_s=2.0)`:
  - Converts (activity, target tension) → circumference command
    `B = C_wearer(activity) − T_target / k`.
  - Re-tighten delay: after a transition *into* STANDING, wait
    `retighten_delay_s` before commanding the tighter target (never cinch mid-
    movement); loosening is never delayed.
  - Clamps commands to the actuator envelope `[c_min_mm, c_max_mm]` from the
    profile.

**Acceptance.** Targets per activity exactly; loosening immediate on sit;
tightening delayed but eventually committed; commands always in envelope.

**Tests (~10).** Per-activity targets, command formula, clamp at envelope,
retighten delay window, loosening not delayed, target changes propagate.

**Commit:** `Prompt 4: per-activity tension policy and controller`

---

## Prompt 5 — Actuator abstraction

**Files:** `sibelt/actuator.py`, `tests/test_actuator.py`

**Spec.**
- `Actuator` abstract base: `command(target_mm, t_s)`, `step(dt)` →
  `ActuatorStatus` (`position_mm`, `moving`, `motor_on_s`, `adjustments`).
- `SimulatedActuator(profile, max_speed_mm_s=40.0)`:
  - Moves toward the commanded circumference at the rate limit; clamped to
    the profile envelope.
  - Accounts motor-on time and adjustment events; `battery_mah_used(motor_a=0.15,
    system_ma=0.5)` converts to mAh (lightweight budget evidence).
- `tension_n(wearer_circ_mm)` via the spring model (belt pulls, never pushes).

**Acceptance.** Position never leaves the envelope; rate respected; moving
stops exactly at the target; accounting consistent with motion time.

**Tests (~10).** Rate limit, envelope clamp, exact arrival, no motor time when
already at target, adjustment counting, tension at position, battery model
arithmetic.

**Commit:** `Prompt 5: rate-limited actuator with duty accounting`

---

## Prompt 6 — Safety and failsafe layer

**Files:** `sibelt/safety.py`, `tests/test_safety.py`

**Spec.**
- `SafetyEvent` dataclass (`t_s`, `kind`, `detail`); kinds: `WATCHDOG`,
  `CEILING`, `OVERRIDE`, `LOW_CONFIDENCE`.
- `OverrideMode` enum: `NONE`, `FREEZE` (hold position), `LOOSEN`.
- `SafetyMonitor(profile, watchdog_s=3.0)`:
  - `enforce(command_mm, estimate, current_tension_n, override, t_s)` →
    `SafetyDecision` (final command + events).
  - Watchdog: stale or UNKNOWN estimate → loose command (fail-loose).
  - Ceiling: current tension above `max_tension_n` → loosen regardless.
  - Override precedence: LOOSEN > FREEZE > watchdog > ceiling > policy.
- Fail-loose principle documented in the module docstring: the safe state is
  the loosest state[4] — excess tension buys nothing clinically and can only
  harm; sagging trousers are a cosmetic failure.

**Acceptance.** Every fault path produces the loose command; precedence order
verified; nominal day produces zero events.

**Tests (~12).** Watchdog on stale, ceiling forced loosen, FREEZE ignores
policy, LOOSEN beats everything, precedence matrix, no events when healthy,
event log ordering, tension ceiling arithmetic.

**Commit:** `Prompt 6: fail-loose safety monitor`

---

## Prompt 7 — Customization: profiles and calibration

**Files:** `sibelt/profiles.py`, `tests/test_profiles.py`

**Spec.**
- `default_profile()` factory; `ProfileStore(path)` with `load()/save()`
  (JSON, atomic write via temp file + rename), `validate()` raising
  `ValidationError` with field-level messages.
- Envelope: circumference 400–2000 mm; `delta_sit_mm` 5–80; stiffness
  0.1–5.0 N/mm; `sitting_tension_n < hold_tension_n ≤ max_tension_n`;
  priors strictly increasing standing < sitting < driving; all timings > 0.
- Per-activity tension overrides (dict keyed by activity name) merged over
  defaults.
- `calibrate(c_standing_mm, c_sitting_mm)`: sets `c_standing_mm` and
  `delta_sit_mm`, requiring `c_sitting ≥ c_standing` and delta in envelope.
- No PII: schema stores `wearer_id` (opaque string) and numbers only.

**Acceptance.** Round-trip byte-stable JSON; every invalid mutation rejected
with a specific message; calibration updates exactly two fields.

**Tests (~12).** Round-trip, defaults valid, each envelope violation rejected
(≥ 6 cases), override merge, calibration sanity failures, atomic save leaves
no temp file, unknown activity override rejected.

**Commit:** `Prompt 7: customizable JSON profiles with calibration`

---

## Prompt 8 — Closed-loop engine and day simulation

**Files:** `sibelt/engine.py`, `tests/test_engine.py`

**Spec.**
- `BeltEngine(profile, imu, seed)`: wires sensor → classifier → controller →
  safety → actuator at `dt=0.02`; records per-tick rows
  (`t_s`, activity, rotation, belt circumference, tension, SIJ load, events).
- `simulate_day(profile, scenario, seed)` → `SimulationReport`:
  - Smart-belt run vs **static-belt baseline** (a fixed belt sized for
    standing — the ordinary-clothing case this project replaces).
  - Metrics: adverse-load integral over seated periods (N·s), peak seated
    adverse load, peak seated tension, % seated time at/under the comfortable
    floor, adjustment count, battery estimate, safety events (must be 0).
  - `to_json()`, and `render_text()` human summary.
- Built-in scenarios: `day` (stand/commute-drive/desk-sit/stand breaks) and
  `commute`.

**Acceptance.** With default profile and seeded `day` scenario: adverse seated
load reduced ≥ 60% vs the static baseline; zero safety events; static baseline
reproduces the user's scenario — a belt sized standing becomes several times
tighter when its wearer sits[11][24].

**Tests (~10).** Reduction threshold, zero violations, baseline tension
inflation when seated (≥ 2× standing), metrics JSON-serializable, report text
contains all headline numbers, determinism (same seed → same report),
scenarios load, seated floor honored ≥ 95% of seated ticks.

**Commit:** `Prompt 8: closed-loop engine, day simulation, baseline comparison`

---

## Prompt 9 — CLI

**Files:** `sibelt/cli.py`, `sibelt/__main__.py`, `tests/test_cli.py`

**Spec.**
- `python -m sibelt` / `sibelt` console script, argparse subcommands:
  - `simulate [--scenario day|commute] [--profile PATH] [--json] [--seed N]`
  - `calibrate --standing MM --sitting MM [--wearer-id ID] [--profile PATH]`
    (wizard over stdin when flags omitted)
  - `profile show|validate [--profile PATH]`
  - `selftest` (wiring check: models/sensors/classify/engine import + quick
    deterministic loop)
- Exit codes: 0 ok; 1 usage; 2 validation. JSON output stable in every branch.
- All user-visible strings kid-friendly-readable; no PII echoed.

**Acceptance.** Every documented command executed against a fresh profile and
its output verified; `--json` output parses and round-trips the report.

**Tests (~10).** Subprocess exit codes for each command, JSON parses, wizard
stdin round-trip, calibrate writes profile + rejects bad input, `profile
validate` rejects a broken file, `--seed` determinism, `selftest` exit 0.

**Commit:** `Prompt 9: CLI (simulate, calibrate, profile, selftest)`

---

## Prompt 10 — README, academic paper (LaTeX → PDF), and release

**Files:** `README.md`, `docs/paper/paper.tex`, `docs/paper/paper.pdf`,
`docs/paper/references.tex` (generated from the citation ledger),
`docs/HARDWARE.md`, `LICENSE`, final `PROMPTS.md`/`Project_state.md` updates.

**Spec.**
- **README.md** — Phosphorus voice, feature-first, with inline citations
  `[n]` drawn from the citation ledger and a mechanically rendered `Sources:`
  block; medical disclaimer; quickstart; the headline simulation numbers from
  a real `sibelt simulate --json` run; link to the compiled paper.
- **Academic paper** (`docs/paper/paper.tex`, compiled with `pdflatex` twice;
  both `.tex` and `.pdf` committed):
  - Abstract; Introduction (SIJD prevalence[1][2], trauma[3], the clothing
    problem[11][24]); Background (belt mechanics: self-bracing[19], SIJ
    mobility reduction[19], tension non-linearity[4], clinical
    evidence[3][8][10], PGP guideline context[18][19], prior art[16], sensing
    feasibility and caveats[13][23]); Methods (device architecture, biomechanical
    first-order model with assumptions table, control policy, safety);
    Results (real numbers from `sibelt simulate --json`: seated adverse-load
    reduction, tension traces, battery); Discussion; Limitations (first-order
    model, waist-worn ambiguity[23], simulation-only, not a medical device);
    References (generated from the ledger — no hand-typed URLs).
- **`docs/HARDWARE.md`** — physical build pathway: IMU (e.g., MPU-6050 class),
  MCU, micro linear actuator/ratchet, mass and battery budget < 120 g,
  fail-loose wiring notes.
- **LICENSE** — MIT. Full pytest suite green; `python -m compileall` clean;
  `sources.py verify README.md` green; commit; push to GitHub `main`.

**Acceptance.** `pdflatex` compiles twice without error; the PDF contains the
real simulation numbers; README `verify` passes with evidence quotes; full
test suite green; repo pushed.

**Commit:** `Prompt 10: README, LaTeX paper (with compiled PDF), license, release`

---

## Dependency table

| Prompt | Module | Depends on |
|---|---|---|
| 1 | `sibelt/models.py` | — |
| 2 | `sibelt/sensors.py` | 1 |
| 3 | `sibelt/classify.py` | 1, 2 |
| 4 | `sibelt/control.py` | 1 |
| 5 | `sibelt/actuator.py` | 1 |
| 6 | `sibelt/safety.py` | 1 |
| 7 | `sibelt/profiles.py` | 1 |
| 8 | `sibelt/engine.py` | 1–7 |
| 9 | `sibelt/cli.py`, `__main__.py` | 1–8 |
| 10 | docs + paper | 1–9 |

## Testing strategy

- One pytest file per module, all under `tests/`, run with the project venv
  (`.venv/bin/python -m pytest -q`) — the session interpreter has no pytest.
- Determinism everywhere: every stochastic component takes a seed.
- Acceptance thresholds live *in tests* (e.g., ≥ 60% adverse-load reduction),
  so regressions fail loudly.
- `git add` with explicit paths, one commit per prompt; push at phase
  boundaries.

## Test-count table (updated as phases land)

| Prompt | Module | Tests |
|---|---|---|
| 1 | models | — |
| 2 | sensors | — |
| 3 | classify | — |
| 4 | control | — |
| 5 | actuator | — |
| 6 | safety | — |
| 7 | profiles | — |
| 8 | engine | — |
| 9 | cli | — |
| 10 | docs/paper | full suite |