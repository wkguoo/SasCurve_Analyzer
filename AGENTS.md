# Repository Guidelines

## Project Structure & Module Organization

This is a Python desktop application for inspecting and reporting calibrated 1D SAS curves. `main.py` is the GUI entry point. Core numerical and persistence logic lives in `app/core/`: import, validation, transforms, plotting, analysis, project state, records, export, and reports. PySide6 UI code lives in `app/ui/` and should delegate analysis work to `app/core/`. Tests are in `tests/`, docs in `docs/`, and sample data in `examples/`.

## Build, Test, and Development Commands

- `python -m pip install -r requirements.txt`: install runtime and test dependencies.
- `python main.py`: launch the desktop application locally.
- `python -m pytest`: run the full test suite.
- `python -m py_compile main.py app\core\*.py app\ui\*.py`: syntax check.

In restricted Windows sandboxes, keep pytest temp files inside the repo:

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
python -m pytest
```

## Coding Style & Naming Conventions

Use 4-space indentation, `snake_case` functions/modules, and `PascalCase` classes. Prefer type hints where they clarify data flow, especially in `app/core`. Keep numerical algorithms, parsing, validation, and serialization out of UI classes. Preserve non-destructive data handling: derived curves and exports should not mutate imported curve data.

## Testing Guidelines

Use `pytest`. Add focused tests next to the relevant behavior, following names such as `tests/test_validation.py` or `tests/test_batch_import.py`. For new analysis behavior, cover normal data, invalid q or intensity values, warnings, and missing error columns. For UI-facing changes, prefer testing the core function behind the workflow.

## Upgrade & Bugfix Records

Every upgrade, bug fix, behavior change, or troubleshooting discovery must be recorded before handoff. Use `CHANGELOG.md` for user-facing changes and `docs/developer_notes.md` for implementation notes. Include date, symptom or reason, root cause if known, touched files/modules, fix summary, tests run, and follow-up risk. This is mandatory to avoid repeated mistakes and speed future bug investigations.

## Commit & Pull Request Guidelines

Use imperative commit messages such as `Add batch import validation` or `Fix Guinier warning text`. Pull requests should include a summary, tests run, linked issues when applicable, and screenshots for visible UI changes. If import/export behavior changes, describe the fixture used.

## Security & Configuration Tips

Do not commit private scattering datasets, generated project folders, or local `.tmp/` contents unless they are intentional fixtures. Keep settings paths explicit and local; avoid reading arbitrary sensitive paths from user configuration. Experimental interfaces should remain clearly labeled and should not be used as sources of formal quantitative conclusions without validation.

## Agent skills

### Issue tracker

Issues for this repository are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The default engineering-skill triage labels are configured in `docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See `docs/agents/domain.md`.
