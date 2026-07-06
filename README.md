# sas_curve_analyzer

`sas_curve_analyzer` 是一个本地 Python 桌面软件，用于读取、检查和绘制已经完成绝对强度校准的一维 SAS 曲线数据。

当前实现到阶段四：项目骨架、数据导入、数据质量检查、q 单位转换、基础可视化、无模型初步分析、批量比较、历史/正式记录、报告导出、高级方法边界提示、分析模板、pipeline、插件基类和高级预留接口。

## 当前支持的功能

- 通过 `python main.py` 启动 PySide6 GUI。
- 导入 `csv`、`txt`、`dat` 格式的一维 SAS 曲线。
- 输入数据至少包含 `q` 和 `I(q)` 两列，可选包含 `error` 或 `sigma` 列。
- 自动跳过以 `#`、`;`、`//` 开头的注释行。
- 自动识别逗号、制表符和空格分隔。
- 检查 q 单调性、重复 q、NaN、负强度、零强度和异常 error。
- 显示 `q_min`、`q_max`、`I_min`、`I_max`、点数和动态范围。
- q 单位在 `A^-1` 和 `nm^-1` 之间转换，转换会生成新曲线，不覆盖原始曲线。
- 绘制线性图、半对数图和双对数图。
- 有 `error` 列时可显示误差棒。
- 绘制 Guinier、Kratky、Porod、q²I(q) 和局部斜率图。
- 进行 Guinier、power-law/Porod 斜率、局部斜率、峰识别、有限 q 范围不变量、Kratky 指标和 Porod 平台指标分析。
- 每个分析结果保存为 `AnalysisResult`，包含 q 区间、参数、结果、warning、时间和输入曲线版本。
- 导入多条曲线并建立曲线组。
- 对重复曲线求平均；q 网格不一致时可线性插值到共同 q 网格。
- 计算两条曲线的差值、比值和相对差值。
- 仅用于显示的归一化：`I/Imax`、`I/I(q_ref)`、`I/area`、`I/Q_measured`。
- 创建历史记录和正式记录。
- 导出曲线 CSV、分析 JSON/CSV、feature table、图像和 Markdown 报告。
- 保存和加载本地项目文件夹，第一版使用 JSON/CSV，不依赖数据库。
- 使用结构化方法 warning 提醒 Guinier、power-law、Porod、invariant 和峰分析的适用边界。
- 保存和应用分析模板，并通过 pipeline 串联验证、Guinier、power-law、局部斜率、峰识别和 invariant。
- 使用高级显示变换：`2π/q`、`q²`、`lnI`、`log10I`、`qI`、`q²I`、`q³I`、`q⁴I` 和 normalized I。
- 提供 P(r) experimental placeholder、相关函数预留接口、外推预留接口和插件基类。
- 通过设置对话框保存默认 q 单位、图像格式、误差棒、方法 warning、导出目录和日志等级。

## 明确不支持的功能

当前阶段不做以下操作：

- 强度校正；
- 背景扣除；
- 透过率校正；
- 厚度校正；
- 曝光时间归一化；
- 绝对强度标定；
- 二维探测器图像积分；
- 复杂结构模型拟合；
- 自动材料结构判断。
- 低 q 或高 q 外推；
- 由不变量自动反演体积分数或比表面积；
- 把 `d = 2π/q*` 自动解释为颗粒直径。
- 成熟 P(r) 间接傅里叶变换；
- 成熟相关函数参数自动提取。

## 安装方法

在 Windows PowerShell 中进入项目目录：

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -m pip install -r requirements.txt
```

这条命令会安装 GUI、数据处理、绘图和测试所需依赖。

## 启动方法

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

成功标准：出现标题为 `sas_curve_analyzer` 的桌面窗口，左侧为曲线列表，右侧有“数据导入”“数据检查”“曲线绘图”“无模型分析”“批量比较”“历史与正式记录”“导出报告”“分析模板”“高级功能”标签页，并有“设置”菜单。

## 示例数据格式

示例文件：

```text
examples/example_absolute_sas_curve.csv
```

格式如下：

```csv
q,I,error
0.010,980.1987,19.6039
0.012,971.6108,19.4322
```

- `q`：散射矢量，默认单位 `A^-1`。
- `I`：绝对强度或已校准强度。
- `error`：可选误差列。如果没有误差列，软件仍允许导入。

## 测试方法

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -m pytest
```

成功标准：所有测试显示 `passed`。

## 项目结构

```text
sas_curve_analyzer/
  README.md
  requirements.txt
  main.py
  app/
    ui/
      main_window.py
      import_tab.py
      check_tab.py
      plotting_tab.py
      analysis_tab.py
      batch_tab.py
      records_tab.py
      export_tab.py
    core/
      data_model.py
      io.py
      validation.py
      transforms.py
      plotting.py
      project.py
      fitting.py
      uncertainty.py
      model_free.py
      feature_extraction.py
      batch.py
      comparison.py
      records.py
      export.py
      report.py
  tests/
  examples/
  docs/
```

## 数据安全

导入、检查、绘图和单位转换都不会修改原始实验数据。单位转换会生成新的 `CurveData` 对象，并在 `processing_history` 中记录来源和转换参数。

## 阶段二方法边界

阶段二分析用于辅助判断 q 区间和提取曲线特征，不直接证明材料机理。

- Guinier 分析要求合理低 q 区间；当 `qRg_max > 1.3` 或 slope 非负时会给出 warning。
- power-law 斜率只提示可能的 Porod-like、分形或粗糙界面相关行为，不自动给出唯一结构结论。
- 有限 q 不变量只积分实测 q 范围，不做 `q -> 0` 或 `q -> infinity` 外推。
- 峰位对应的 `d = 2π/q*` 是特征尺度或相关距离，不等同于颗粒直径。

## 阶段三批量与导出说明

- 重复曲线平均会生成新的 `CurveData`，原始曲线不变。
- q 网格不一致时使用线性插值，并在历史记录中写入 warning。
- 比值和相对差值遇到分母为 0 或接近 0 的点会排除并给出 warning。
- 归一化默认只用于显示或形状比较，不会修改原始曲线。
- Markdown 报告会记录曲线、分析结果、历史记录、正式记录和图像路径。
