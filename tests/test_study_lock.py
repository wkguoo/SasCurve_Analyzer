from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core.study_lock import study_lock


_HOLDER_SCRIPT = r"""
import sys
import time
from pathlib import Path
from app.core.study_lock import study_lock

output, ready, release = map(Path, sys.argv[1:])
with study_lock(output):
    ready.write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + 20
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not release.exists():
        raise SystemExit("parent did not release test holder")
"""

_CONTENDER_SCRIPT = r"""
import sys
from pathlib import Path
from app.core.study_lock import StudyLockError, study_lock

try:
    with study_lock(Path(sys.argv[1])):
        print("acquired")
except StudyLockError as exc:
    print(str(exc))
    raise SystemExit(17)
"""


def _start_holder(tmp_path: Path, output: Path) -> tuple[subprocess.Popen[str], Path, Path]:
    ready, release = tmp_path / "holder.ready", tmp_path / "holder.release"
    command = [sys.executable, "-c", _HOLDER_SCRIPT, str(output), str(ready), str(release)]
    process = subprocess.Popen(
        command, cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 10
    while not ready.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(f"lock holder exited before acquiring lock: {stdout}\n{stderr}")
        time.sleep(0.01)
    if not ready.exists():
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        pytest.fail(f"lock holder did not become ready: {stdout}\n{stderr}")
    return process, ready, release


def _release_holder(process: subprocess.Popen[str], release: Path) -> None:
    release.write_text("release", encoding="utf-8")
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr


def test_two_processes_contending_for_same_canonical_output(tmp_path):
    output = tmp_path / "nested" / "study"
    alias_component = output.parent / "alias"
    alias_component.mkdir(parents=True)
    alias = alias_component / ".." / output.name
    process, _, release = _start_holder(tmp_path, output)
    try:
        contender = subprocess.run(
            [sys.executable, "-c", _CONTENDER_SCRIPT, str(alias)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
        )
        assert contender.returncode == 17
        assert "Study output is busy" in contender.stdout
        assert "study" in contender.stdout
    finally:
        _release_holder(process, release)


def test_different_outputs_can_be_locked_while_another_is_busy(tmp_path):
    process, _, release = _start_holder(tmp_path, tmp_path / "study-a")
    try:
        contender = subprocess.run(
            [sys.executable, "-c", _CONTENDER_SCRIPT, str(tmp_path / "study-b")],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
        )
        assert contender.returncode == 0, contender.stderr
        assert contender.stdout.strip() == "acquired"
    finally:
        _release_holder(process, release)


def test_exception_releases_lock_and_lock_file_is_retained(tmp_path):
    output = tmp_path / "study"
    with pytest.raises(RuntimeError, match="abort"):
        with study_lock(output):
            raise RuntimeError("abort")

    with study_lock(output):
        pass
    assert (tmp_path / ".study.study.lock").is_file()
    assert (tmp_path / ".study.study.lock").stat().st_size == 1


def test_terminated_process_releases_lock_for_recovery(tmp_path):
    output = tmp_path / "study"
    process, _, _ = _start_holder(tmp_path, output)
    process.terminate()
    process.communicate(timeout=10)

    recovered = subprocess.run(
        [sys.executable, "-c", _CONTENDER_SCRIPT, str(output)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
    )
    assert recovered.returncode == 0, recovered.stderr
    assert recovered.stdout.strip() == "acquired"
    assert (tmp_path / ".study.study.lock").is_file()


def test_simultaneous_first_creation_has_only_one_writer(tmp_path):
    script = r"""
import sys, time
from pathlib import Path
from app.core.study_lock import StudyLockError, study_lock
output, start, result, release = map(Path, sys.argv[1:])
deadline = time.monotonic() + 10
while not start.exists() and time.monotonic() < deadline:
    time.sleep(0.01)
try:
    with study_lock(output):
        result.write_text("owner")
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
except StudyLockError:
    result.write_text("busy")
"""
    output, start, release = (tmp_path / name for name in ("new-study", "start", "release"))
    results = [tmp_path / f"result-{index}" for index in range(2)]
    processes = [subprocess.Popen([sys.executable, "-c", script, str(output), str(start), str(result), str(release)],
                                  cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for result in results]
    try:
        start.write_text("start")
        deadline = time.monotonic() + 10
        while not all(result.exists() for result in results) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert sorted(result.read_text() for result in results) == ["busy", "owner"]
    finally:
        release.write_text("release")
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            assert process.returncode == 0, stdout + stderr
