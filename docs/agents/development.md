# Development and proportionate verification

Use this page when changing code or selecting checks. A known project/task does
not require a workspace map or a fixed set of preliminary document reads.

## Select the work

Use the current diff and already-known paths first. Read the affected definition,
its immediate callers and relevant tests; expand only when these leave a concrete
question unresolved. Keep snippets and check outcomes in the current task context,
tied to the covered content. Do not reread unchanged files or rerun an equivalent
successful check at each plan/review/commit step. Read recent, relevant record
sections rather than the whole historical changelog or developer notes.

Batch independent tool calls, but return bounded snippets/results so a combined
output is not truncated. Reuse outputs already held in the task before fetching
the same file again. Successful equivalent checks are shared evidence across
applicable skills; a skill should not restart the validation chain.

`python scripts/select_tests.py [known_changed_paths ...]` prints a JSON test plan.
Without paths it uses the current tracked diff and non-ignored new files; it does
not scan or parse application files. `--base <revision>` compares a committed
change. `--run` runs the selected tests once. Use the available Python environment;
on Windows `py -3.13`/`py -3.12` may replace `python`.

| Evidence / change | Sufficient starting check | Expand when |
| --- | --- | --- |
| Documentation/instructions only | Review text, local links and diff | An executable example or runtime contract changed |
| Mapped leaf (`settings`, `user_messages`, import preview, UI style) | Selector's paired core/consumer tests | Failure, new dependency or changed public behavior not covered there |
| Individual test file only | Changed test files | Shared fixture, collection/config or helper changes |
| Numerical methods, shared import/state/cache, CLI, export, dependencies, CI or unmapped code | Full pytest suite | Failure or uncovered external/platform contract |
| Current bug investigation | One reproducing test, then affected scope | The failure reaches other consumers |

The selector is a small allowlist, not a generated dependency graph. Unmapped
changes remain full checks. Add a leaf only after inspecting its consumers and
identifying meaningful integration tests. A successful local subset does not
replace CI's platform/Qt-free contract checks for a shared change.

Pytest's native cache is enabled and ignored by Git. `--lf` is useful while fixing
a failure; run the required affected scope after that fix. Full collection and
tests are not the default for a documentation or mapped leaf edit.

To investigate a processing performance regression, run
`python scripts/benchmark_agent_workflow.py` explicitly. It counts real reads,
parses and package verifications on generated inputs and cleans its own study.
It is not a startup check or another required suite for ordinary edits.

## Commands when needed

- Runtime dependencies: `python -m pip install -r requirements.txt`; headless
  studies: `requirements-headless.txt`. Reuse a working environment.
- GUI: `python main.py`; headless study entry: `python -m app.cli`.
- Full tests (shared boundary or explicit deep check): `python -m pytest -q`.
- Syntax-only check: `python -m py_compile <changed_python_files>` when imports
  cannot be tested. Successful pytest imports already check their syntax; do not
  add an unconditional compile-all pass.
- GUI tests: `QT_QPA_PLATFORM=offscreen`; headless plotting: `MPLBACKEND=Agg`.
  In a Windows sandbox that actually restricts temporary files, set `TEMP`, `TMP`
  and `PYTEST_DEBUG_TEMPROOT` to an existing repo-local `.tmp/` directory.

## Records and handoff

Keep the existing mandatory change records concise: date, symptom/reason, root
cause when known, touched modules, fix, tests and remaining concrete limits in
`CHANGELOG.md` and `docs/developer_notes.md`. User-manual/UI changes also update
the relevant user instructions; numerical/import/export changes describe the
fixture and retain missing/error/unit coverage.

Before an authorized commit/merge/push, review the final diff and status, ensure
the recorded checks cover its current code, remove only this task's disposable
files, and verify the relevant remote refs. Fresh code or a changed merge result
needs an affected check; a fast-forward of the already-tested commit does not
need the same suite again. Use imperative commit messages. PR descriptions state
the final behavior and checks; visible UI changes include screenshots.
