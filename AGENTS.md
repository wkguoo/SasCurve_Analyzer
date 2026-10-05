# SasCurve Analyzer

Python application for calibrated 1D SAS curves. `app/cli.py` is the headless
entry point, `main.py` the Qt entry point; numerical/import/export logic belongs
in `app/core/`, widgets in `app/ui/`, tests in `tests/`.

## Work from the current evidence

- When already in this repository, use the task, current context and Git diff
  to locate the affected code. Workspace maps, README, domain docs and skills
  are routes for unresolved questions, not a fixed startup reading list.
- Read relevant definitions, callers and tests once. Reuse unchanged content
  and passed checks within the task; edits, failures or unresolved boundary
  questions justify another read/check. Search named paths before broadening.
- Batch independent reads/checks in one tool call. Use a subagent only for an
  independent, bounded task that saves elapsed time; do not rebuild repo maps.

## Boundaries

- Preserve imported measurements, units, provenance, invalid frames and missing
  values. Derived data must not mutate sources. Experimental/model-dependent
  results retain their applicability and reporting gates.
- Reuse raw parsed tables only within their explicit cache lifetime and file
  signature. Keep content hashes at publication and cross-run reuse boundaries.
- Keep private data, generated studies, `.tmp/`, environments and credentials
  out of Git. Preserve unrelated changes and active worktrees.
- Follow existing Python style: four spaces, snake_case, PascalCase, useful type
  hints. Record each behavior change in `CHANGELOG.md` and
  `docs/developer_notes.md` before handoff (reason, modules, checks, actual limits).

## Load details when needed

| Task | Route |
| --- | --- |
| Select checks / development commands / Git handoff | [development.md](docs/agents/development.md) |
| Run or resume calibrated curve studies | [agent_workflow_zh.md](docs/agent_workflow_zh.md) |
| Domain/architecture decision | [domain.md](docs/agents/domain.md) |
| User asks for GitHub issue work | [issue-tracker.md](docs/agents/issue-tracker.md), then labels only if needed |

For code changes, `python scripts/select_tests.py` reports the tests justified by
the current diff; `--run` executes them. Known local changes use focused tests;
shared or unknown code/config changes use the full suite. Do not repeat a
successful run unless its covered content changed or a concrete risk remains.
