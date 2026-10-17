# Project State: Sacroiliac Smart Belt

> **Last updated:** 2026-10-17
> **Current phase:** polish (v0.1 shipped)
> **Overall health:** green

---

## 1. Goal (1–2 sentences)
A lightweight, posture-adaptive belt that adjusts its circumference to reduce
adverse sacroiliac joint pressure for wearers with ligamentous laxity or prior
trauma — built as a stdlib-only Python simulation/control stack with a CLI, an
academic paper (LaTeX→PDF), and a grounded-citations evidence base.

## 2. Current Status
### Done
- [x] Prompts 1–10 built sequentially (one commit per prompt, no subagents)
- [x] Full suite: 127 tests green (`.venv/bin/python -m pytest -q`)
- [x] Full-day simulation: 89.3% seated adverse-load reduction vs static belt
- [x] README (grounded citations, Phosphorus voice), docs/HARDWARE.md, LICENSE
- [x] Academic paper: docs/paper/paper.tex → paper.pdf (7 pages, pdflatex clean)
- [x] GitHub repo drwjkirkpatrick-web/sacroiliac-smart-belt pushed to main

### In Progress
- [ ] (nothing — v0.1 complete)

### Not Started
- [ ] Physical prototype (see docs/HARDWARE.md)
- [ ] Real-IMU validation of the posture classifier
- [ ] Clinician-supervised evaluation pathway

## 3. Architecture & Key Decisions
| Decision | Rationale | Date |
|---|---|---|
| Spring model `T = k·max(0, C_wearer−B)` | A belt can pull, never push; makes the standing/sitting mismatch computable | 2026-10-17 |
| Fail-loose safety (faults → loosest state) | Excess tension buys no laxity reduction (Damen); sag is cosmetic | 2026-10-17 |
| Circumference-commanded actuator | Encodes the core scenario: same belt, different seated circumference | 2026-10-17 |
| First-order SIJ load `T·cos θ` / `T·sin θ` | Relative comparisons between strategies only, never diagnosis | 2026-10-17 |
| `acquired` flag on estimates | Boot-time UNKNOWN is not a lost-confidence fault | 2026-10-17 |
| Smoothstep trajectories from segment start | Squared-gap easing diverged on downward transitions | 2026-10-17 |

## 4. Blockers & Risks
- **Risk:** waist-worn IMU ambiguity → answered in software with debounce + hysteresis; still needs real-hardware validation.
- **Risk:** model is first-order → stated plainly in the paper and README.

## 5. Next Step (only ONE)
> **Next:** Hardware prototype per docs/HARDWARE.md (port the same stdlib modules to MicroPython).

## 6. Environment & Tooling Notes
- Tests: `.venv/bin/python -m pytest -q` (session python3 has no pytest)
- Compile check: `python -m compileall sibelt tests`
- Paper: `cd docs/paper && pdflatex -interaction=nonstopmode paper.tex` (twice)
- Citations ledger: `~/.hermes/cache/citations/ledger.json` (24 sources; 12 cited, all with verbatim evidence quotes)

## 7. Recent Session Log
- 2026-10-17: Grounding research (24 sources); ten prompts written; prompts 1–10 built sequentially (127 tests); paper compiled; repo pushed to GitHub main.

## 8. References
- Plan: PROMPTS.md (ten build prompts + build result)
- Paper: docs/paper/paper.pdf
- Citation ledger: ~/.hermes/cache/citations/ledger.json
