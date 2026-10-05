from scripts.select_tests import select_tests
import scripts.select_tests as selection


def test_documentation_only_requires_no_runtime_suite():
    plan = select_tests(["AGENTS.md", "docs/agents/domain.md", "CHANGELOG.md"])
    assert plan["scope"] == "none"
    assert plan["tests"] == []


def test_leaf_includes_consumer_tests_without_full_collection():
    plan = select_tests(["app\\core\\user_messages.py", "README.md"])
    assert plan["scope"] == "targeted"
    assert plan["tests"] == ["tests/test_ui_safety.py", "tests/test_user_messages.py"]


def test_known_test_only_change_runs_that_test():
    plan = select_tests(["tests/test_io.py", "tests/test_io.py"])
    assert plan["tests"] == ["tests/test_io.py"]


def test_shared_or_unmapped_change_retains_deep_checks():
    for path in ("app/core/io.py", "app/core/study.py", "app/cli.py", "requirements.txt",
                 "pytest.ini", "tests/conftest.py", ".github/workflows/tests.yml",
                 "app/core/new_method.py", "examples/example_absolute_sas_curve.csv",
                 "tests/test_removed_or_missing.py"):
        plan = select_tests(["app/ui/style.py", path])
        assert plan["scope"] == "full", path
        assert plan["tests"] == ["tests"]
        assert "tests/test_study.py" in plan["headless_tests"]


def test_empty_diff_has_no_checks():
    assert select_tests([])["scope"] == "none"


def test_ci_reuses_plan_without_git_and_propagates_test_failure(monkeypatch):
    import json
    from types import SimpleNamespace

    plan = select_tests(["tests/test_io.py"])
    calls = []
    monkeypatch.setenv("SAS_TEST_PLAN", json.dumps(plan))
    monkeypatch.setattr(selection.sys, "argv", ["select_tests.py", "--run"])

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(selection.subprocess, "run", run)
    assert selection.main() == 7
    assert calls == [[selection.sys.executable, "-m", "pytest", "-q", "tests/test_io.py"]]


def test_headless_ci_runs_only_the_saved_qt_free_scope(monkeypatch):
    import json
    from types import SimpleNamespace

    plan = select_tests(["app/core/io.py"])
    calls = []
    monkeypatch.setenv("SAS_TEST_PLAN", json.dumps(plan))
    monkeypatch.setattr(selection.sys, "argv", ["select_tests.py", "--run", "--headless"])
    monkeypatch.setattr(selection.subprocess, "run", lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0))
    assert selection.main() == 0
    assert calls[0][4:] == plan["headless_tests"]
    assert "tests/test_ui_safety.py" not in calls[0]
