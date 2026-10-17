# 🦴 sacroiliac-smart-belt

![tests](https://img.shields.io/badge/tests-127%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.8%2B-3776ab)
![dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-success)
![license](https://img.shields.io/badge/license-MIT-informational)
![paper](https://img.shields.io/badge/paper-LaTeX%20PDF-blue)

**A belt that knows when you sit — and gets out of your sacroiliac joints' way.**

`sibelt` is a lightweight, posture-adaptive belt design: a sensor-driven control
stack that keeps your trousers up while you stand, and *relaxes* the moment you
sit — so a belt fitted for standing never turns into a vice across your
sacroiliac joints (SIJs) in the car or at the desk.

The problem in one sentence: lower-body circumferences increase when a person
sits[11] and the pelvis rotates backward[24], so a static belt sized for
standing pulls **several times harder** the moment its wearer sits — force
redirected across lax or previously injured SIJs, all day, every day.

## Why this matters

Sacroiliac joint pain is one of the most common causes of low back pain,
accounting for an estimated 15–30% of cases[1], with SIJ dysfunction a
primary pain source in 10–25% of affected patients[2]. Trauma — including
the posttraumatic arthritis that can follow motor vehicle collisions — is
a recognized pathway[3]. And the people who hurt most are the ones whose
*clothing* betrays them — garment fit genuinely changes between standing and
sitting.[11]

Belts are the right conservative tool: a small-force pelvic belt generates
a self-bracing effect at the SIJ[19], belt application significantly
reduces SIJ mobility[19], pelvic belts help affected postpartum
patients[3], and belting is a standard nonoperative option alongside
exercise and manual therapy[10]. In a five-day strenuous-labor trial,
spine pain rose only 0.2 on the NRS with a Serola belt versus 0.9 without
it[8].

The liberating fact: **belts saturate.** A tension of 100 N does not reduce
SIJ laxity more than 50 N[4] — extra tension buys nothing. So a belt that
relaxes when you sit loses nothing therapeutic, and escapes the seated
over-tension entirely.

## The headline result

Real output of `sibelt simulate --scenario day --json` (seed 7 — a 3.3-hour
simulated day of standing, commuting, and desk work; 588,000 control ticks):

- Seated adverse SIJ load: **80,579 N·s (static belt) → 8,642 N·s (smart) — an 89.3% reduction**
- The static belt's seated tension peaks at **28.0 N — 3.5× its standing 8 N** — that is ordinary clothing hurting you
- **99.98%** of seated time at or under the 3 N comfort floor
- **Zero** safety-rule violations; ~1.95 mAh used (≈150 days on a 300 mAh cell)[unverified]

Full analysis: **[docs/paper/paper.pdf](docs/paper/paper.pdf)** — a 7-page
LaTeX paper with the complete evidence base, methods, and results.

## How it works

```
 IMU (6-axis) → posture classifier → tension policy → SAFETY → actuator
                (debounce +       (stand: hold,    (fail-loose) (rate-limited
                 hysteresis)       sit: slack)
```

| Layer | Module | What it does |
|---|---|---|
| Biomechanics | `sibelt/models.py` | Spring law + first-order SIJ load projection |
| Sensing | `sibelt/sensors.py` | IMU abstraction + deterministic simulated IMU |
| Classification | `sibelt/classify.py` | Debounced, confidence-gated posture state machine |
| Control | `sibelt/control.py` | Per-activity targets; loosens instantly, re-tightens with a grace delay |
| Actuation | `sibelt/actuator.py` | Rate-limited circumference motor + battery accounting |
| Safety | `sibelt/safety.py` | Watchdog, ceiling, manual overrides — everything fails LOOSE |
| Customization | `sibelt/profiles.py` | JSON profiles + calibration wizard (no PII) |
| The loop | `sibelt/engine.py` | Closed-loop engine + smart-vs-static day simulation |
| You | `sibelt/cli.py` | `simulate`, `calibrate`, `profile`, `selftest` |

## Quickstart

```bash
cd sacroiliac-smart-belt
python3 -m venv .venv
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q            # 127 tests, ~50 s
.venv/bin/python -m sibelt simulate      # the full day, as text
.venv/bin/python -m sibelt simulate --scenario commute --json
```

No runtime dependencies — pure standard library Python (3.8+).

## Make it yours

Every number is a profile field. Measure twice, wear forever:

```bash
.venv/bin/python -m sibelt calibrate --standing 900 --sitting 928
```

(Or run `calibrate` with no flags for the interactive wizard.) The profile
is JSON at `~/.sibelt/profile.json` — geometry, stiffness, tension
targets, timing, all of it — and stores an opaque `wearer_id` only.

## Safety: fail loose, always

The safe state of a belt is the *loosest* state — and since extra tension
buys no extra laxity reduction, loose risks nothing therapeutically.[4] Every fault path — dead
sensor, stale estimate, low confidence, tension ceiling breach — ends at
full loose, and the belt boots loose. Precedence: manual loosen > manual
freeze > watchdog > ceiling > policy. A belt that fails loose cannot
over-compress an SIJ; sagging trousers are cosmetic, over-compression is
not — and since extra tension buys no extra laxity reduction[4], loose
costs nothing.

## Sensing, honestly

Waist-worn accelerometers are standard but imperfect: telling sitting from
light activity is their known weak spot compared with thigh-worn
inclinometry[23]. The design answers the caveat instead of ignoring it:
debounced state transitions, confidence gates, graceful degradation to
loose — and wearable sensing itself is a mature, promising approach for
posture analysis[13]. Confusing sitting with driving is *tolerated on
purpose*: both get slack, so the error costs nothing.

## Prior art

A motorized "smart belt" that self-adjusts its fit has existed since
2015[16]. What it lacked — the clinical rationale, the posture-aware
policy, per-wearer calibration, and a fail-loose safety architecture —
is exactly what this project contributes.

## Hardware pathway

The simulation carries an explicit mass and battery budget: ~95 g of
electronics and actuator.[unverified] The build plan (MCU, IMU, micro-servo ratchet,
single-cell LiPo, fail-loose spring-return wiring) is in
[docs/HARDWARE.md](docs/HARDWARE.md).

## The paper

**[docs/paper/paper.pdf](docs/paper/paper.pdf)** — *A Posture-Adaptive
Belt for Reducing Adverse Sacroiliac Joint Loading During Sitting* —
presents the rationale, the first-order model and its assumptions, the
safety architecture, and the simulation results, with a reference list
generated from the same citation ledger used throughout this project.

## Disclaimer

This is a design study and simulation, **not a medical device**. No claim
of clinical efficacy is made. Anyone with diagnosed sacroiliac joint
pain, ligamentous laxity, or pelvic trauma should work with their
clinician before changing how they load their SIJs — belts included.

## License

MIT — see [LICENSE](LICENSE).

## Sources

[1] https://pmc.ncbi.nlm.nih.gov/articles/PMC8517984 — Successful Diagnosis of Sacroiliac Joint Dysfunction (PMC)
[2] https://pmc.ncbi.nlm.nih.gov/articles/PMC8043903 — Association Between SIJ Dysfunction and LBP (PMC)
[3] https://www.aafp.org/afp/2022/0300/p239 — SI Joint Dysfunction: Diagnosis and Treatment (AAFP)
[4] https://repub.eur.nl/pub/72524 — Damen: Does a pelvic belt influence sacroiliac joint laxity?
[8] https://pmc.ncbi.nlm.nih.gov/articles/PMC9479175 — Serola SI Belt: pain and functional impairment (PMC)
[10] https://pmc.ncbi.nlm.nih.gov/articles/PMC7041669 — Nonoperative Treatment Options for SIJ Pain (PMC)
[11] https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8464815 — Kinematic 3D Human-Body Model: standing vs sitting garment fit (PMC)
[13] https://pmc.ncbi.nlm.nih.gov/articles/PMC6929158 — Commercial Postural Devices: A Review (PMC)
[16] https://gizmodo.com/the-only-gadget-the-world-really-needs-is-a-self-adjust-1677432880 — Belty self-adjusting smart belt (Gizmodo)
[19] https://thepogp.co.uk/_userfiles/pages/files/gps_msb_pgp_06.pdf — POGP: pelvic support belts for perinatal PGP
[23] https://d-nb.info/1254931295/34 — Measuring sedentary behavior: waist- vs thigh-worn monitors
[24] https://onlinelibrary.wiley.com/doi/10.1111/os.12543 — Influence of Pelvic Tilt on Femoral Anteversion (supine/standing/sitting)
