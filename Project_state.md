# Project State: Sacroiliac Smart Belt

> **Last updated:** 2026-10-17
> **Current phase:** build
> **Overall health:** green

---

## 1. Goal (1–2 sentences)
A lightweight, posture-adaptive belt that adjusts its circumference to reduce
adverse sacroiliac joint pressure for wearers with ligamentous laxity or prior
trauma — built as a stdlib-only Python simulation/control stack with a CLI, an
academic paper (LaTeX→PDF), and a grounded-citations evidence base.

## 2. Current Status
### Done
- [x] Grounding research (24 sources registered, evidence quotes attached)
- [x] PROMPTS.md with the ten build prompts
- [x] Scaffold (pyproject, .gitignore, venv with pytest, git init)

### In Progress
- [ ] Prompts 1–10: build, test, commit one prompt at a time (no subagents)

### Not Started
- [ ] README.md, docs/paper/paper.tex → paper.pdf, docs/HARDWARE.md, LICENSE
- [ ] GitHub repo creation + final push

## 3. Architecture & Key Decisions
| Decision | Rationale | Date |
|---|---|---|
| Spring model `T = k·max(0, C_wearer−B)` | A belt can pull, never push; makes the standing/sitting circumference mismatch computable | 2026-10-17 |
| Fail-loose safety (faults → loosest state) | Excess tension buys no extra laxity reduction (Damen); sag is cosmetic, over-compression is not | 2026-10-17 |
| Circumference-commanded actuator | Encodes the user's core scenario: same belt, different seated circumference | 2026-10-17 |
| First-order SIJ load `T·cos θ` / `T·sin θ` | Used only for relative comparisons between belt strategies, never diagnosis | 2026-10-17 |
| Stdlib-only package, sim + hardware abstractions | Runs anywhere (incl. on-device), testable without hardware | 2026-10-17 |

## 4. Blockers & Risks
- **Risk:** waist-worn IMU posture ambiguity → mitigated with debounce + hysteresis; SITTING/DRIVING confusion is low-stakes (both slack). | **Risk:** model is first-order → paper states limitations explicitly.

## 5. Next Step (only ONE)
> **Next:** Build Prompt 1 (`sibelt/models.py` + tests), commit.

## 6. Environment & Tooling Notes
- Runtime: project venv `.venv/` (Python 3.14; session python3 has no pytest — always `.venv/bin/python -m pytest`)
- LaTeX: pdflatex/xelatex available (TeX Live 2022)
- Citations ledger: `~/.hermes/cache/citations/ledger.json` (grounded-citations skill; render Sources blocks mechanically, never hand-type URLs)
- Tests: `.venv/bin/python -m pytest -q`; compile check: `python -m compileall sibelt tests`

## 7. Recent Session Log
- 2026-10-17: Research grounding (24 sources, evidence quotes); scaffold + PROMPTS.md; build begins.

## 8. References
- Plan: PROMPTS.md (ten build prompts, dependency table, testing strategy)
- Citation ledger: `~/.hermes/cache/citations/ledger.json`