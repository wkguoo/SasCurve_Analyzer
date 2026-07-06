# GUI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing PySide6 GUI with a more polished scientific desktop theme, clearer action importance, and concise hover help that does not obscure controls.

**Architecture:** Add one shared UI helper module for theme, action roles, button styling, and short help text. Apply those helpers across existing tabs without moving numerical or persistence logic out of `app/core`. Keep the change visually broad but mechanically narrow.

**Tech Stack:** Python, PySide6, Qt style sheets, pytest.

---

### Task 1: Shared UI Helper Tests

**Files:**
- Create: `tests/test_ui_style.py`
- Create: `app/ui/style.py`

- [ ] **Step 1: Write failing tests**

```python
from PySide6.QtWidgets import QApplication, QPushButton

from app.ui.style import action_button, apply_help, build_app_stylesheet


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_action_button_sets_importance_role_and_tooltip():
    _app()
    button = action_button(
        "导入曲线",
        role="primary",
        tooltip="读取当前选择的数据文件。",
        status_tip="主操作：导入当前文件并记录历史。",
    )

    assert button.property("uiRole") == "primary"
    assert button.toolTip() == "读取当前选择的数据文件。"
    assert button.statusTip() == "主操作：导入当前文件并记录历史。"
    assert button.whatsThis() == "主操作：导入当前文件并记录历史。"
    assert button.toolTipDuration() == 7000


def test_apply_help_keeps_tooltip_short_and_moves_detail_to_status_tip():
    _app()
    button = QPushButton("保存项目")

    apply_help(
        button,
        tooltip="保存项目状态。",
        status_tip="重要：写出 project.json 和曲线数据，便于后续复现。",
    )

    assert button.toolTip() == "保存项目状态。"
    assert button.statusTip().startswith("重要：")
    assert button.whatsThis() == button.statusTip()


def test_build_app_stylesheet_defines_tooltips_and_button_roles():
    stylesheet = build_app_stylesheet()

    assert "QToolTip" in stylesheet
    assert 'QPushButton[uiRole="primary"]' in stylesheet
    assert 'QPushButton[uiRole="danger"]' in stylesheet
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_ui_style.py -v
```

Expected: FAIL because `app.ui.style` does not exist.

- [ ] **Step 3: Implement minimal helper module**

Add `app/ui/style.py` with:

- `build_app_stylesheet() -> str`
- `apply_help(widget, tooltip, status_tip=None, duration_ms=7000) -> None`
- `action_button(text, role="secondary", tooltip="", status_tip=None) -> QPushButton`
- `apply_button_role(button, role) -> QPushButton`
- `apply_app_theme(app) -> None`

- [ ] **Step 4: Re-run the focused tests**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_ui_style.py -v
```

Expected: PASS.

### Task 2: Apply Theme And Help To Existing Screens

**Files:**
- Modify: `main.py`
- Modify: `app/ui/main_window.py`
- Modify: `app/ui/import_tab.py`
- Modify: `app/ui/check_tab.py`
- Modify: `app/ui/plotting_tab.py`
- Modify: `app/ui/analysis_tab.py`
- Modify: `app/ui/batch_tab.py`
- Modify: `app/ui/records_tab.py`
- Modify: `app/ui/export_tab.py`
- Modify: `app/ui/templates_tab.py`
- Modify: `app/ui/advanced_tab.py`
- Modify: `app/ui/settings_dialog.py`

- [ ] **Step 1: Apply global app theme**

In `main.py`, after `app = QApplication(sys.argv)`, call:

```python
from app.ui.style import apply_app_theme

apply_app_theme(app)
```

- [ ] **Step 2: Add main window hierarchy**

In `app/ui/main_window.py`, give the curve list and tab widget object names, larger initial size, clear window title, status tips for tabs, and splitter proportions.

- [ ] **Step 3: Replace important buttons with `action_button`**

Use roles consistently:

- `primary`: main workflow actions such as import, plot, run analysis, save project.
- `secondary`: helper actions such as choose file, refresh, load template.
- `success`: create/add/apply actions such as batch group, average, apply template, mark formal.
- `warning`: experimental or method-boundary actions.
- `danger`: destructive or removing actions such as unmarking formal records.

- [ ] **Step 4: Add concise hover help**

Each key button, combo box, and risky option should get short `tooltip` text plus a more detailed `status_tip`. Keep tooltip text brief to reduce obstruction; detailed guidance appears in the status bar and What's This text.

### Task 3: Records And Verification

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/developer_notes.md`

- [ ] **Step 1: Add user-facing changelog entry**

Record date, symptom/reason, touched UI modules, fix summary, tests run, and remaining manual GUI risk.

- [ ] **Step 2: Add developer note**

Document `app/ui/style.py`, action role meanings, and the short-tooltip/status-tip convention.

- [ ] **Step 3: Run syntax and focused tests**

Run:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest tests/test_ui_style.py -v
python -m py_compile main.py app\core\*.py app\ui\*.py
```

Expected: focused tests pass and syntax compilation succeeds.
