# Developer Notes

## Project Structure

```text
sas_curve_analyzer/
  main.py
  app/
    core/
    ui/
  tests/
  examples/
  docs/
```

`app/core` 保存数据模型、导入、检查、转换、无模型分析、批量比较、导出、模板、pipeline、插件和高级预留接口。

`app/ui` 保存 PySide6 界面。GUI 应调用 `app/core`，不要把数值算法写进界面类。

## Core Data Models

- `CurveData`: 曲线数据对象。
- `AnalysisResult`: 分析结果。
- `ComparisonResult`: 曲线比较结果。
- `HistoryRecord`: 操作历史。
- `FormalRecord`: 正式记录。

## Adding A New Analysis Plugin

继承 `AnalysisPlugin`：

```python
class MyPlugin(AnalysisPlugin):
    name = "my_plugin"
    version = "0.1.0"
    description = "Short description"

    def run(self, curve, parameters):
        ...
```

插件应返回 `AnalysisResult`。调用方优先使用 `safe_run`，避免单个插件失败导致整个软件崩溃。

现有 Guinier、power-law、peak detection 和 finite invariant 已通过 `get_builtin_plugins()` 提供兼容层。新增插件可以复用 `FunctionAnalysisPlugin` 包装一个已有函数，也可以直接继承 `AnalysisPlugin`。

## Adding A New Plot Type

在 `app/core/plotting.py` 中扩展 `create_curve_figure` 的 `plot_type` 分支，然后在 `app/ui/plotting_tab.py` 的下拉框中加入名称，并添加测试。

## Running Tests

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -m pytest
```

## Packaging

本项目尚未自动打包。后续如果需要发布 Windows 桌面版本，可考虑 `PyInstaller`，但应先确认依赖、图标、示例数据和输出目录策略。
