"""Select checks from changed paths, without parsing or mapping the repository.

Known leaves have explicit consumer tests. Shared/unknown code changes fall back
to the full suite. Pass known paths directly, or let Git supply the current diff.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FOCUSED_TESTS = {
    "app/core/user_messages.py": ("tests/test_user_messages.py", "tests/test_ui_safety.py"),
    "app/core/settings.py": ("tests/test_settings.py", "tests/test_ui_safety.py"),
    "app/core/import_preview.py": ("tests/test_import_preview.py", "tests/test_ui_safety.py"),
    "app/ui/style.py": ("tests/test_ui_style.py", "tests/test_ui_safety.py"),
}
HEADLESS_TESTS = (
    "tests/test_study.py", "tests/test_publication_bundle.py", "tests/test_metric_units.py",
    "tests/test_pr_batch_config.py", "tests/test_cache_atomic.py", "tests/test_batch_inputs.py",
    "tests/test_batch_import.py", "tests/test_sequence_analysis.py", "tests/test_auto_batch.py",
    "tests/test_analysis_runner.py", "tests/test_io.py", "tests/test_import_preview.py",
    "tests/test_table_cache.py", "tests/test_test_selection.py",
    "tests/test_saxs_input_contract.py", "tests/test_result_package.py",
)
DOC_FILES = {"AGENTS.md", "README.md", "CHANGELOG.md", "LICENSE"}


def select_tests(paths: list[str]) -> dict:
    changed = sorted({PurePosixPath(path.replace("\\", "/")).as_posix() for path in paths})
    tests = set()
    for path in changed:
        if path in DOC_FILES or (path.startswith("docs/") and Path(path).suffix.lower() in {".md", ".rst", ".txt", ".png", ".svg", ".jpg", ".pdf"}):
            continue
        if path in FOCUSED_TESTS:
            tests.update(FOCUSED_TESTS[path])
        elif (path.startswith("tests/test_") and "/" not in path[6:]
              and path.endswith(".py") and (ROOT / path).is_file()):
            tests.add(path)
        else:
            return {"scope": "full", "tests": ["tests"], "headless_tests": list(HEADLESS_TESTS),
                    "changed": changed, "reason": f"Shared or unmapped boundary: {path}"}
    return {"scope": "targeted" if tests else "none", "tests": sorted(tests),
            "headless_tests": [], "changed": changed,
            "reason": "Explicit leaf/consumer tests" if tests else "No runtime changes"}


def changed_paths(base: str | None) -> list[str]:
    reference = "HEAD" if base is None else base
    result = subprocess.run(["git", "diff", "--name-only", "-z", reference, "--"], cwd=ROOT,
                            check=True, capture_output=True)
    paths = result.stdout.decode("utf-8").split("\0")
    if base is None:
        untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "-z"],
                                   cwd=ROOT, check=True, capture_output=True)
        paths += untracked.stdout.decode("utf-8").split("\0")
    return [path for path in paths if path]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Known changed paths (avoids Git calls)")
    parser.add_argument("--base", help="Git base revision; empty/all-zero base selects full checks")
    parser.add_argument("--full", action="store_true", help="Explicit deep verification")
    parser.add_argument("--run", action="store_true", help="Run the selected pytest scope once")
    parser.add_argument("--headless", action="store_true", help="Run the Qt-free subset of a full plan")
    parser.add_argument("--github-output", type=Path, help="Write the plan for downstream CI jobs")
    args = parser.parse_args()
    if args.full or (args.base is not None and not args.base.strip("0")):
        plan = select_tests(["requirements.txt"])
        plan["reason"] = "Explicit full check or no comparable Git base"
    elif args.run and not args.paths and args.base is None and os.environ.get("SAS_TEST_PLAN"):
        plan = json.loads(os.environ["SAS_TEST_PLAN"])
    else:
        plan = select_tests(args.paths if args.paths else changed_paths(args.base))
    encoded = json.dumps(plan, separators=(",", ":"))
    print(encoded, flush=True)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(f"scope={plan['scope']}\nplan={encoded}\n")
    if args.run:
        tests = plan["headless_tests"] if args.headless else plan["tests"]
        if tests:
            return subprocess.run([sys.executable, "-m", "pytest", "-q", *tests], cwd=ROOT).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
