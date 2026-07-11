# Automated Batch Deep Analysis Implementation Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the confirmed one-click SAS batch-analysis design through four independently testable implementation plans without losing any method/model output requirement.

**Architecture:** The work proceeds from stable schemas and orchestration, through complete numerical methods/models, then sequence analysis, and finally the atomic result package and GUI. Each plan must finish its focused and full regression checks before the next plan starts.

**Tech Stack:** Python 3.x, numpy, pandas, scipy, matplotlib, PySide6, pytest, openpyxl (introduced only in Plan 4), pathlib and JSON/CSV.

## Global Constraints

- Authoritative design: `docs/superpowers/specs/2026-07-11-automated-batch-deep-analysis-design.md`.
- Execute the four plans in the exact order below.
- Treat every plan boundary as a review checkpoint; do not continue while tests fail.
- Never modify raw experimental files or use unpublished experimental data as fixtures.
- Do not automatically commit, push or package.

---

## Execution Order

- [ ] **Plan 1: Batch foundation** — `docs/superpowers/plans/2026-07-11-auto-batch-foundation.md`
  - Exit criterion: typed config/result contract, complete metric registry, input manifest/CSV metadata, strict consensus q ranges and failure-isolating in-memory orchestration all pass.
- [ ] **Plan 2: Complete methods and models** — `docs/superpowers/plans/2026-07-11-complete-analysis-and-models.md`
  - Exit criterion: every registered method and all 10 allowed models emit complete parameters, uncertainty, bounds, diagnostics, residuals, statuses and rankings.
- [ ] **Plan 3: In-situ sequence analysis** — `docs/superpowers/plans/2026-07-11-in-situ-sequence-analysis.md`
  - Exit criterion: ordered comparisons, feature/status matrices, trends, change/outlier flags, optional kinetics, PCA/clustering and heatmap data/figures pass without filling invalid frames.
- [ ] **Plan 4: Result package and GUI** — `docs/superpowers/plans/2026-07-11-results-package-and-gui.md`
  - Exit criterion: XLSX metadata, atomic result folder, all detail files, exact 16-sheet workbook, responsive GUI, cancellation, end-to-end output and input-hash integrity pass.

## Spec-to-Plan Coverage

| Design requirement | Implemented by |
|---|---|
| Batch config, statuses and typed results | Plan 1 Tasks 1–2 |
| Natural-sort input, manifest, hash and metadata | Plan 1 Task 3; XLSX extension in Plan 4 Task 1 |
| Batch-consensus q regions | Plan 1 Task 4 |
| Failure-isolating orchestration | Plan 1 Task 5 |
| Common fit statistics and residual contract | Plan 2 Task 1 |
| Guinier, power-law and local slope complete outputs | Plan 2 Task 2 |
| Crossover, peaks, shoulders, oscillations, Porod, Kratky and integrals | Plan 2 Task 3 |
| P(r), invariant, correlation and lamellar conditional outputs | Plan 2 Task 4 |
| All 10 model parameters, covariance, retries and derived values | Plan 2 Task 5 |
| Bootstrap and q-range sensitivity | Plan 2 Task 6 |
| Per-frame ranking, fixed batch model and transition flags | Plan 2 Task 7 |
| Reference differences/ratios and normalized shape distances | Plan 3 Task 1 |
| Feature table, status table, trends, change points and outliers | Plan 3 Task 2 |
| Empirical/Avrami kinetics | Plan 3 Task 3 |
| PCA and clustering | Plan 3 Task 4 |
| q-sequence heatmaps and parameter figures | Plan 3 Task 5 |
| Atomic outputs, detail CSV/JSON and manifest | Plan 4 Tasks 1–2 |
| Exact 16-sheet workbook | Plan 4 Task 3 |
| One-click GUI, progress and cancellation | Plan 4 Task 4 |
| End-to-end and input-integrity proof | Plan 4 Task 5 |
| Beginner documentation and final regression | Every plan's final task; final handoff in Plan 4 Task 6 |

## Checkpoint Protocol

At each plan boundary:

1. Run that plan's focused suite.
2. Run `python -B -m compileall -q main.py app\core app\ui`.
3. Run the full test suite with offscreen Qt/Agg settings.
4. Run `git diff --check` and inspect `git status --short`.
5. Append the required `CHANGELOG.md` entry.
6. Report exact pass/fail counts and any remaining limitation.
7. Do not commit, push or package unless the user separately authorizes it.
