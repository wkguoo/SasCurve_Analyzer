from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QSizePolicy, QSplitter, QTabWidget, QVBoxLayout, QWidget

from app.core.data_model import CurveData
from app.core.project import ProjectState, load_project, save_project
from app.core.records import create_history_record
from app.core.settings import load_settings_with_info
from app.core.user_messages import UserMessage, exception_detail, format_user_message
from app.ui.advanced_tab import AdvancedTab
from app.ui.advanced_workspace_tab import AdvancedWorkspaceTab
from app.ui.analysis_tab import AnalysisTab
from app.ui.auto_batch_tab import AutoBatchTab
from app.ui.batch_tab import BatchTab
from app.ui.check_tab import CheckTab
from app.ui.curve_workspace_tab import CurveWorkspaceTab
from app.ui.data_import_workspace_tab import DataImportWorkspaceTab
from app.ui.deep_analysis_tab import DeepAnalysisTab
from app.ui.export_tab import ExportTab
from app.ui.import_tab import ImportTab
from app.ui.plotting_tab import PlottingTab
from app.ui.records_tab import RecordsTab
from app.ui.settings_dialog import SettingsDialog
from app.ui.style import action_button, apply_help
from app.ui.templates_tab import TemplatesTab
from app.ui.widgets import configure_combo, configure_table, scroll_page


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SAS Curve Analyzer")
        self.resize(1440, 900)
        self.setMinimumSize(900, 640)
        self.project = ProjectState()
        self.current_project_folder: Path | None = None
        self._saved_revision = self.project.revision
        self.settings, self.settings_info = load_settings_with_info()

        self.curve_list = QListWidget()
        self.curve_list.setObjectName("curveList")
        self.curve_list.setAlternatingRowColors(True)
        apply_help(
            self.curve_list,
            tooltip="已导入曲线列表。",
            status_tip="选择一条曲线后，数据检查、绘图、分析和导出页面会使用当前曲线。",
        )
        self.curve_list.currentRowChanged.connect(self._on_curve_selection_changed)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")

        self.import_tab = ImportTab(self)
        self.check_tab = CheckTab(self)
        self.plotting_tab = PlottingTab(self)
        self.analysis_tab = AnalysisTab(self)
        self.batch_tab = BatchTab(self)
        self.auto_batch_tab = AutoBatchTab(self)
        self.deep_analysis_tab = DeepAnalysisTab(self)
        self.records_tab = RecordsTab(self)
        self.export_tab = ExportTab(self)
        self.templates_tab = TemplatesTab(self)
        self.advanced_tab = AdvancedTab(self)

        self.output_tabs = QTabWidget()
        self.output_tabs.setObjectName("outputTabs")
        self.output_tabs.addTab(scroll_page(self.records_tab), "历史与正式记录")
        self.output_tabs.addTab(scroll_page(self.export_tab), "导出报告")
        self.output_tabs.addTab(scroll_page(self.templates_tab), "分析模板")

        self.data_import_workspace_tab = DataImportWorkspaceTab(self.import_tab, self.check_tab)
        self.curve_workspace_tab = CurveWorkspaceTab(self.plotting_tab, self.analysis_tab)
        self.advanced_workspace_tab = AdvancedWorkspaceTab(self.advanced_tab, self.deep_analysis_tab, self.batch_tab, self.auto_batch_tab)
        self.tabs.addTab(self.data_import_workspace_tab, "数据导入")
        self.tabs.addTab(self.curve_workspace_tab, "曲线工作台")
        self.tabs.addTab(self.advanced_workspace_tab, "高级功能")
        self.tabs.addTab(self.output_tabs, "项目与输出")
        self.plotting_tab.plot_type.currentIndexChanged.connect(
            lambda _index: self.analysis_tab.set_plot_type_from_plot(self.plotting_tab.plot_type.currentData())
        )
        self._configure_tab_help()

        self._create_project_menu()
        settings_action = self.menuBar().addAction("设置")
        settings_action.setStatusTip("配置默认 q 单位、图像格式、误差检查和导出目录。")
        settings_action.triggered.connect(self.open_settings)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self._build_sidebar())
        self.main_splitter.addWidget(self.tabs)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([240, 1200])

        header = QWidget()
        header.setObjectName("workspaceHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        brand = QLabel("SAS Curve Analyzer")
        brand.setObjectName("brandTitle")
        subtitle = QLabel("一维小角散射曲线分析")
        subtitle.setProperty("uiRole", "muted")
        header_layout.addWidget(brand)
        header_layout.addWidget(subtitle)
        header_layout.addStretch(1)
        self.project_state = QLabel()
        self.project_state.setObjectName("projectState")
        self.project_state.setTextFormat(Qt.PlainText)
        self.project_state.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header_layout.addWidget(self.project_state, 1)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(10)
        layout.addWidget(header)
        layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(central)

        from PySide6.QtWidgets import QComboBox, QTableWidget
        for combo in self.findChildren(QComboBox):
            configure_combo(combo)
        for table in self.findChildren(QTableWidget):
            configure_table(table)

        self.statusBar().showMessage("请导入已经完成绝对强度校准的一维 SAS 曲线。")
        self._update_curve_context()
        self._update_window_title()
        from app.ui.help_texts import install_ui_help
        install_ui_help(self)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("projectSidebar")
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(300)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)
        title = QLabel("项目曲线")
        title.setProperty("uiRole", "heading")
        self.curve_count = QLabel("0 条曲线")
        self.curve_count.setObjectName("curveCount")
        self.curve_search = QLineEdit()
        self.curve_search.setObjectName("curveSearch")
        self.curve_search.setPlaceholderText("搜索曲线名称或单位")
        self.curve_search.setClearButtonEnabled(True)
        self.curve_search.textChanged.connect(self._filter_curve_list)
        self.sidebar_hint = QLabel("尚未导入曲线。\n从数据导入开始，再检查数据并分析。")
        self.sidebar_hint.setWordWrap(True)
        self.sidebar_hint.setProperty("uiRole", "muted")
        self.curve_summary = QLabel()
        self.curve_summary.setObjectName("curveSummary")
        self.curve_summary.setTextFormat(Qt.PlainText)
        self.curve_summary.setWordWrap(True)
        self.curve_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        import_button = action_button("导入数据", role="primary")
        import_button.setObjectName("sidebarImportButton")
        import_button.clicked.connect(self.show_import_tab)
        plot_button = action_button("查看曲线与分析", role="secondary")
        plot_button.setObjectName("sidebarPlotButton")
        plot_button.clicked.connect(self.show_plotting_tab)
        layout.addWidget(title)
        layout.addWidget(self.curve_count)
        layout.addWidget(self.curve_search)
        layout.addWidget(self.sidebar_hint)
        layout.addWidget(self.curve_list, 1)
        layout.addWidget(self.curve_summary)
        layout.addWidget(import_button)
        layout.addWidget(plot_button)
        search_action = QAction(self)
        search_action.setShortcut(QKeySequence("Ctrl+F"))
        search_action.triggered.connect(self.curve_search.setFocus)
        self.addAction(search_action)
        return sidebar

    def show_import_tab(self) -> None:
        self.tabs.setCurrentWidget(self.data_import_workspace_tab)
        self.data_import_workspace_tab.tabs.setCurrentIndex(0)

    def _filter_curve_list(self, text: str = "") -> None:
        query = text.strip().casefold()
        visible = 0
        for index in range(self.curve_list.count()):
            item = self.curve_list.item(index)
            hidden = query not in item.text().casefold()
            item.setHidden(hidden)
            visible += not hidden
        total = self.curve_list.count()
        self.curve_count.setText(f"{visible} / {total} 条曲线" if query else f"{total} 条曲线")
        self.sidebar_hint.setVisible(total == 0 or visible == 0)
        self.sidebar_hint.setText("没有匹配的曲线，请修改或清除搜索。" if total else "尚未导入曲线。\n从数据导入开始，再检查数据并分析。")

    def _update_curve_context(self) -> None:
        if not hasattr(self, "curve_summary"):
            return
        self._filter_curve_list(self.curve_search.text())
        curve = self.current_curve()
        if curve is None:
            self.curve_summary.setText("选择曲线后，这里显示点数、单位与测量范围。")
            return
        q = curve.q[np.isfinite(curve.q)]
        q_range = f"{q.min():.5g} – {q.max():.5g}" if q.size else "无有限值"
        self.curve_summary.setText(
            f"当前曲线\n{curve.name}\n\n{curve.q.size} 个数据点\n"
            f"q：{q_range} {curve.q_unit}\nI(q)：{curve.intensity_unit}"
        )

    def _create_project_menu(self) -> None:
        project_menu = self.menuBar().addMenu("项目")

        new_action = QAction("新建项目", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.setStatusTip("清空当前项目状态并开始一个新项目。")
        new_action.triggered.connect(self.new_project)
        project_menu.addAction(new_action)

        open_action = QAction("打开项目...", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.setStatusTip("从包含 project.json 的文件夹恢复项目。")
        open_action.triggered.connect(self.open_project_dialog)
        project_menu.addAction(open_action)

        save_action = QAction("保存项目", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.setStatusTip("保存到当前项目文件夹；若尚未选择文件夹则执行另存为。")
        save_action.triggered.connect(self.save_project)
        project_menu.addAction(save_action)

        save_as_action = QAction("另存为项目...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.setStatusTip("选择文件夹并保存当前项目。")
        save_as_action.triggered.connect(self.save_project_as_dialog)
        project_menu.addAction(save_as_action)

        self.project_actions = {
            "new": new_action,
            "open": open_action,
            "save": save_action,
            "save_as": save_as_action,
        }

    def _configure_tab_help(self) -> None:
        tab_help = [
            "导入 SAS 曲线，并在内部数据检查页查看质量提示。",
            "同屏查看曲线绘图和八种曲线分析输出。",
            "使用高级方法、深度分析和批量比较等低频功能。",
            "管理历史记录、导出报告和分析模板。",
        ]
        for index, text in enumerate(tab_help):
            self.tabs.setTabToolTip(index, text)
        self.output_tabs.setTabToolTip(0, "管理历史记录和正式报告记录。")
        self.output_tabs.setTabToolTip(1, "导出曲线、特征表、报告或项目文件夹。")
        self.output_tabs.setTabToolTip(2, "保存、加载并批量应用分析模板。")

    def show_plotting_tab(self) -> None:
        self.tabs.setCurrentWidget(self.curve_workspace_tab)

    def show_analysis_tab(self) -> None:
        self.tabs.setCurrentWidget(self.curve_workspace_tab)

    def show_project_output_tab(self, child_index: int = 0) -> None:
        self.tabs.setCurrentWidget(self.output_tabs)
        self.output_tabs.setCurrentIndex(child_index)

    def set_plot_type(self, plot_type: str) -> bool:
        index = self.plotting_tab.plot_type.findData(plot_type)
        if index < 0:
            return False
        self.plotting_tab.plot_type.setCurrentIndex(index)
        self.plotting_tab.refresh()
        return True

    def set_analysis_type(self, analysis_type: str) -> bool:
        aliases = {
            "power_law": "loglog",
            "kratky_metrics": "kratky",
            "porod_metrics": "porod",
            "invariant_measured": "invariant",
        }
        analysis_type = aliases.get(analysis_type, analysis_type)
        index = self.analysis_tab.analysis_type.findData(analysis_type)
        if index < 0:
            return False
        self.analysis_tab.analysis_type.setCurrentIndex(index)
        return True

    def add_curve(self, curve: CurveData) -> None:
        self.project.add_curve(curve)
        self.curve_search.clear()
        self._append_curve_list_item(curve)
        self.curve_list.setCurrentRow(len(self.project.curves) - 1)
        self.statusBar().showMessage(f"已导入曲线: {curve.name}")
        self._update_window_title()

    def _append_curve_list_item(self, curve: CurveData) -> None:
        item = QListWidgetItem(f"{curve.name}  [{curve.q_unit}]")
        item.setData(Qt.UserRole, curve.curve_id)
        item.setToolTip(f"{curve.name}\nq：{curve.q_unit} · I(q)：{curve.intensity_unit}\nID：{curve.curve_id}")
        self.curve_list.addItem(item)

    def refresh_curve_list(self, selected_row: int | None = None) -> None:
        previous_row = self.curve_list.currentRow()
        self.curve_list.blockSignals(True)
        self.curve_list.clear()
        for curve in self.project.curves:
            self._append_curve_list_item(curve)
        self.curve_list.blockSignals(False)
        if self.project.curves:
            row = selected_row if selected_row is not None else previous_row
            row = max(0, min(row, len(self.project.curves) - 1))
            self.curve_list.setCurrentRow(row)
        self.refresh_curve_dependent_controls()
        self._update_curve_context()

    def refresh_curve_dependent_controls(self) -> None:
        if hasattr(self, "batch_tab"):
            self.batch_tab.refresh_curves()
        if hasattr(self, "records_tab"):
            self.records_tab.refresh()

    def current_curve(self) -> CurveData | None:
        row = self.curve_list.currentRow()
        if row < 0 or row >= len(self.project.curves):
            return None
        return self.project.curves[row]

    def replace_current_curve_selection(self, curve: CurveData) -> None:
        self.add_curve(curve)

    def _on_curve_selection_changed(self) -> None:
        self._update_curve_context()
        self.check_tab.refresh()
        self.plotting_tab.refresh()
        self.analysis_tab.refresh_results()
        self.records_tab.refresh()
        self.refresh_curve_dependent_controls()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def is_project_dirty(self) -> bool:
        return self.project.revision != self._saved_revision

    def mark_project_dirty(self) -> None:
        self._update_window_title()

    def _mark_project_clean(self) -> None:
        self._saved_revision = self.project.revision
        self._update_window_title()

    def _update_window_title(self) -> None:
        project_name = "未命名项目" if self.current_project_folder is None else self.current_project_folder.name
        dirty_marker = " *" if self.is_project_dirty() else ""
        self.setWindowTitle(f"SAS Curve Analyzer - {project_name}{dirty_marker}")
        if hasattr(self, "project_state"):
            state = "未保存更改" if self.is_project_dirty() else ("尚未保存" if self.current_project_folder is None else "已保存")
            self.project_state.setText(f"{project_name} · {state}")
            self.project_state.setToolTip(f"{project_name} · {state}")

    def _handle_unsaved_changes_before_destructive_action(self) -> bool:
        if not self.is_project_dirty():
            return True
        message_box = QMessageBox(self)
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("未保存的项目更改")
        message_box.setText("当前项目有未保存更改。")
        message_box.setInformativeText("请选择先保存当前项目、不保存并继续，或取消本次操作。")
        save_button = message_box.addButton("保存", QMessageBox.AcceptRole)
        discard_button = message_box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_button = message_box.addButton("取消", QMessageBox.RejectRole)
        message_box.setDefaultButton(save_button)
        message_box.exec()
        clicked_button = message_box.clickedButton()
        if clicked_button == save_button:
            return self.save_project()
        if clicked_button == discard_button:
            return True
        if clicked_button == cancel_button:
            return False
        return False

    def _confirm_discard_unsaved_changes(self) -> bool:
        return self._handle_unsaved_changes_before_destructive_action()

    def _refresh_all_project_views(self) -> None:
        self._update_curve_context()
        self.refresh_curve_dependent_controls()
        self.check_tab.refresh()
        self.plotting_tab.refresh()
        self.analysis_tab.refresh_results()

    def new_project(self) -> None:
        if not self._handle_unsaved_changes_before_destructive_action():
            return
        self.project = ProjectState()
        self.current_project_folder = None
        self._saved_revision = self.project.revision
        self.curve_list.clear()
        self._refresh_all_project_views()
        self.statusBar().showMessage("已新建空项目。")
        self._update_window_title()

    def open_project_dialog(self) -> None:
        if not self._handle_unsaved_changes_before_destructive_action():
            return
        folder = QFileDialog.getExistingDirectory(self, "选择包含 project.json 的项目文件夹", self.settings.default_export_dir)
        if folder:
            try:
                self.open_project_folder(Path(folder))
            except Exception as exc:
                self._show_project_operation_message(
                    UserMessage(
                        title="项目打开失败",
                        what_happened="所选文件夹没有成功恢复为当前项目。",
                        facts=(
                            f"selected_folder: {folder}。",
                            "项目打开要求文件夹中存在可读取的 project.json。",
                        ),
                        technical_detail=exception_detail(exc),
                        severity="error",
                    )
                )

    def open_project_folder(self, folder: str | Path) -> None:
        project_folder = Path(folder)
        self.project = load_project(project_folder)
        self.current_project_folder = project_folder
        self._saved_revision = self.project.revision
        self.refresh_curve_list(selected_row=0)
        self.check_tab.refresh()
        self.plotting_tab.refresh()
        self.analysis_tab.refresh_results()
        self.records_tab.refresh()
        self.statusBar().showMessage(f"已打开项目: {project_folder}")
        self._update_window_title()

    def save_project(self) -> bool:
        if self.current_project_folder is None:
            return self.save_project_as_dialog()
        try:
            path = self.save_project_to_folder(self.current_project_folder)
        except Exception as exc:
            self._show_project_operation_message(
                UserMessage(
                    title="项目保存失败",
                    what_happened="当前项目没有写入当前项目文件夹。",
                    facts=(
                        f"current_project_folder: {self.current_project_folder}。",
                        f"curve_count: {len(self.project.curves)}。",
                    ),
                    technical_detail=exception_detail(exc),
                    severity="error",
                )
            )
            return False
        return path is not None

    def save_project_as_dialog(self) -> bool:
        folder = QFileDialog.getExistingDirectory(self, "选择项目保存文件夹", self.settings.default_export_dir)
        if not folder:
            return False
        try:
            path = self.save_project_to_folder(Path(folder))
        except Exception as exc:
            self._show_project_operation_message(
                UserMessage(
                    title="项目另存为失败",
                    what_happened="当前项目没有写入所选项目文件夹。",
                    facts=(
                        f"selected_folder: {folder}。",
                        f"curve_count: {len(self.project.curves)}。",
                    ),
                    technical_detail=exception_detail(exc),
                    severity="error",
                )
            )
            return False
        return path is not None

    def _project_folder_write_risks(self, folder: Path) -> list[str]:
        risks: list[str] = []
        if self.current_project_folder is not None and folder.resolve() == self.current_project_folder.resolve():
            return risks
        if (folder / "project.json").exists():
            risks.append("目标文件夹中已存在 project.json，继续保存会覆盖项目入口文件。")
        if (folder / "curves").exists():
            risks.append("目标文件夹中已存在 curves 子文件夹，继续保存可能混入旧项目曲线文件。")
        raw_suffixes = {".csv", ".txt", ".dat"}
        raw_like_files = [path.name for path in folder.iterdir() if path.is_file() and path.suffix.lower() in raw_suffixes] if folder.exists() else []
        if raw_like_files:
            preview = ", ".join(raw_like_files[:5])
            risks.append(f"目标文件夹包含疑似原始数据文件: {preview}。建议另选新的项目文件夹。")
        return risks

    def _confirm_project_folder_write(self, folder: Path, reasons: list[str]) -> bool:
        if not reasons:
            return True
        detail = "\n".join(f"- {reason}" for reason in reasons)
        response = QMessageBox.question(
            self,
            "确认项目保存文件夹",
            f"所选文件夹可能不是空项目文件夹:\n{folder}\n\n{detail}\n\n是否仍然写入项目文件？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return response == QMessageBox.Yes

    def save_project_to_folder(self, folder: str | Path) -> Path | None:
        project_folder = Path(folder)
        risks = self._project_folder_write_risks(project_folder)
        if not self._confirm_project_folder_write(project_folder, risks):
            self.statusBar().showMessage("已取消项目保存，未写入所选文件夹。")
            return None
        expected_path = project_folder / "project.json"
        self.project.add_history_record(
            create_history_record("project_save", parameters={"path": str(expected_path), "format": "project_folder"})
        )
        path = save_project(self.project, project_folder)
        self.current_project_folder = project_folder
        self.records_tab.refresh()
        self._mark_project_clean()
        self.statusBar().showMessage(f"项目已保存: {path}")
        return path

    def _show_project_operation_message(self, message: UserMessage) -> None:
        self.show_project_output_tab(child_index=1)
        self.export_tab.output.setPlainText(format_user_message(message))
        self.statusBar().showMessage(message.title)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.auto_batch_tab.is_running():
            self.tabs.setCurrentWidget(self.advanced_workspace_tab)
            self.advanced_workspace_tab.tabs.setCurrentIndex(3)
            self.statusBar().showMessage("批量分析仍在运行。请等待完成，或点击取消并等待结果保存后关闭。")
            event.ignore()
            return
        if not self.isVisible():
            event.accept()
            return
        if self._handle_unsaved_changes_before_destructive_action():
            event.accept()
        else:
            event.ignore()
