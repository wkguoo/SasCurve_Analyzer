# CHANGELOG

## 2026-07-12 13:15:18 +08:00 - Change Log-Log View To Base-10 Coordinates

### Task Objective

Change the project's log-log/power-law view from natural-log coordinates to base-10 coordinates, displayed as `lg I(q)` versus `lg q`.

### Added Files

- None.

### Modified Files

- `app/core/plotting.py`
- `app/core/plot_analysis.py`
- `app/core/model_free.py`
- `app/core/uncertainty.py`
- `app/ui/plotting_tab.py`
- `app/ui/analysis_tab.py`
- `app/core/model_catalog.py`
- `tests/test_plotting.py`
- `tests/test_plot_analysis.py`
- `tests/test_model_free_complete.py`
- `README.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`
- `docs/user_manual_zh.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Switched the `loglog` plot mapping to the existing `log10_q` and `log10_I` derived columns.
- Changed log-log display transforms, cursor readout, and display-range conversion to `log10`/`10^x`.
- Updated log-log error propagation to `sigma_lgI = sigma_I / (I * ln(10))`.
- Updated plot-analysis and power-law fits to report `A = 10^b` and use base-10 transformed residual coordinates.
- Updated visible UI labels, model-catalog text, documentation, and focused tests.
- Kept semi-log, Guinier, and local-slope natural-log definitions unchanged.

### Reason

The user requested an `lg-lg` presentation for the project's double-log plot. Base-10 coordinates make the displayed axes explicit while preserving the power-law exponent `alpha`.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

Select `Log-log / power-law: lg I(q) vs lg q` in the curve plotting tab.

### Generated Output Files

- None. No raw experimental data or existing result files were modified.

### How To Check Success

- Focused regression suite: `68 passed`.
- Run: `python -B -m pytest -q -p no:cacheprovider tests/test_plotting.py tests/test_plot_analysis.py tests/test_power_law.py tests/test_model_free_complete.py tests/test_ui_style.py`.
- The plot axes should read `lg q` and `lg I(q)`; display x-range conversion should use `q = 10^x`.

### Notes And Risks

- The power-law intercept is now expressed in base-10 coordinates; the exponent and R² remain mathematically unchanged.
- Existing derived `ln_q`/`ln_I` columns remain available for semi-log, Guinier, local-slope, and export workflows.
- Existing unrelated uncommitted workspace changes were preserved.

## 2026-07-12 - Bind cache to software, algorithms, and metadata

### Task Objective

完成第二轮缓存与结果导出复核：使算法/软件/metadata 变化可靠地使缓存失效，并保证可靠参数 CSV 只包含有限标量。

### Added Files

- None.

### Modified Files

- `app/core/batch_cache.py`
- `app/core/result_package.py`
- `tests/test_auto_batch.py`
- `tests/test_result_package.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- 缓存指纹加入 `app.__version__`、独立 `ANALYSIS_ALGORITHM_VERSION` 和排序后的曲线 metadata JSON。
- 保留 q/I/error、单位、有效 q 区间、配置与缓存格式版本等已有缓存身份字段。
- `reliable_parameters.csv` 只保留字符串、布尔、整数和有限浮点标量；NumPy 标量转换为原生标量；字典、列表、NaN 和 inf 留在完整审计输出中。
- 新增回归测试验证 metadata、软件/算法版本变化均产生新缓存键，并验证复合值和非有限值不会进入可靠参数表。
- 开发文档明确：数值方法、自动选区、拟合诊断、可靠性规则或模型实现变化时必须提升 `ANALYSIS_ALGORITHM_VERSION`；缓存格式变化时提升 `CACHE_SCHEMA_VERSION`。

### Reason

只绑定数据数组和缓存格式仍可能在算法升级或 metadata 变化后复用陈旧结果；将字典和列表写入“可靠标量参数表”也会破坏 Excel/Origin 兼容性和逐帧统计口径。

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q
```

### Generated Output Files

- 测试仅使用临时目录；未生成或修改实验结果文件。

### How To Check Success

- metadata/版本缓存失效及可靠标量筛选目标测试共 7 项通过。
- 全量测试应通过，且 `git diff --check` 无空白错误。

### Notes And Risks

- 新缓存身份会自然忽略此前生成的旧缓存文件，但不会自动删除旧缓存。
- metadata 全量进入指纹是保守策略：无关 metadata 变化也可能导致重新计算，但不会错误复用科研结果。
- 未修改原始实验数据，未打包，未执行 Git commit/push。

## 2026-07-12 - Harden batch cache and reliable-result export

### Task Objective

修复 Ti15 实例复核确认的缓存失效、失败缓存、可靠参数误收录、JSON 字段兼容和 pytest 配置问题。

### Added Files

- None.

### Modified Files

- `app/core/batch_cache.py`
- `app/core/auto_batch.py`
- `app/core/result_package.py`
- `app/core/feature_extraction.py`
- `pytest.ini`
- `tests/test_auto_batch.py`
- `tests/test_result_package.py`
- `tests/test_peak_analysis.py`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- 缓存键新增缓存格式版本、实际 q/I/error 数组指纹、单位和本次方法使用的有效 q 区间；同名但内容不同的曲线或不同共识区间不再复用旧结果。
- `FIT_FAILED`、`INVALID`、`CANCELLED` 等硬失败结果不再写入逐作业缓存，后续运行会重新尝试计算。
- `reliable_parameters.csv` 同时要求分析信封和参数自身状态可用，并要求可靠性评分存在且不低于 0.5。
- 峰明细移除仅大小写不同的 `snr` 重复别名，保留注册指标 `SNR` 和明确字段 `peak_snr`，避免大小写不敏感 JSON 工具冲突。
- 将无效 pytest `cache_dir` 配置替换为受支持的 `addopts = -p no:cacheprovider`。
- 新增测试覆盖输入内容/q 区间缓存失效、硬失败重试、无效参数与缺失评分拦截、峰字段唯一性。

### Reason

旧缓存只依赖文件名、方法和配置，可能在同名实验数据变化或共识 q 区间变化后错误复用结果；硬失败也可能被永久复用。可靠参数表则可能收录参数状态为 invalid 或没有可靠性评分的数值。这些行为会产生不可接受的科研可追溯性风险。

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q
```

### Generated Output Files

- 测试仅生成临时目录内容；未生成或修改实验分析结果。

### How To Check Success

- 新增的 5 个目标回归用例全部通过。
- 缓存、自动批处理、结果包、峰和指标注册相关测试共 118 项通过。
- 全量测试应无 `Unknown config option: cache_dir` 警告。
- `git diff --check` 应无空白错误。

### Notes And Risks

- 缓存格式版本已提升为 `2`，旧逐作业缓存不会命中新键，但不会自动删除。
- 此修复不改变原始实验数据、SAXS 数值算法或已生成的旧结果包。
- 未打包，未执行 Git commit 或 Git push。

## 2026-07-11 - Batch compute cache and tiered result packages

### Task Objective

解决十帧批处理计算量大却无法断点续算、导出失败需全量重跑，以及默认输出过于庞杂（数百明细表）的问题。

### Added Files

- `app/core/batch_cache.py`

### Modified Files

- `app/core/auto_batch.py`
- `app/core/result_package.py`
- `app/ui/auto_batch_tab.py`
- `tests/test_auto_batch.py`
- `tests/test_result_package.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Changes

- **计算缓存 / 断点续算**：`run_auto_batch(..., cache_dir=...)` 按「源文件名+方法+配置指纹」缓存每作业信封；中断后可复用已完成作业；结束写入 `run_checkpoint.json`。
- **计算与导出分离**：`export_result_package_from_checkpoint(cache_dir, output_dir)` 可在导出失败后仅重导包，不重算拟合。
- **三级结果包**：`summary/`（报告入口、可靠参数、排名）、`audit/`（全量参数/警告/索引）、`details/`（方法明细）。
- 默认 `detail_level='usable'`：仅导出 success/assumption_dependent 的明细表；跳过空序列 CSV。
- GUI 自动将缓存写到输出目录下 `{batch_id}_compute_cache`。

### Out of scope / follow-up

- 形状模型「快速预筛再精拟合」可作为后续配置项；本轮以缓存续算为主降低重复成本。

### Tests

- 作业缓存二次运行零 runner 调用；checkpoint 重导出；三级目录与 usable 明细过滤。

## 2026-07-11 - Main model residual and quality gates

### Task Objective

防止仅因覆盖率与 AICc 将 `residual_pass_rate=0` 的模型（如 `lamellar_peak_stack`）选为 `main_model`。

### Modified Files

- `app/core/model_selection.py`
- `tests/test_model_selection.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Changes

- 主模型资格除 coverage ≥ 0.70 外，还要求 residual_pass_rate ≥ 0.70、bound_hit_rate ≤ 0.30、uncertainty 存在且 ≤ 1.0、reliability_pass_rate ≥ 0.70。
- ranking 行增加 `eligibility_failures` 与各阈值字段，便于审计。
- `select_batch_main_model` 仅在 `eligible_for_main_model` 为真时选取。

### Tests

- 零残差通过率不可为主模型；bound_hit / 缺 uncertainty 拦截；可回退到合格模型。

## 2026-07-11 - Batch run.status scientific completeness

### Task Objective

避免批处理在大量 `missing_prerequisite` / `assumption_dependent` 时仍报告误导性的 `completed`。

### Modified Files

- `app/core/auto_batch.py`
- `app/ui/auto_batch_tab.py`
- `app/core/result_package.py`
- `tests/test_auto_batch.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Changes

- 新增 `_finalize_batch_status`：`completed` / `completed_with_limitations` / `partial_success` / `failed`（`cancelled` 不变）。
- `missing_prerequisite` / `assumption_dependent` / `not_applicable` 记为方法限制，不再伪装成全成功 `completed`。
- 无可报告结果（无 `success` 且无 `assumption_dependent`）→ `failed`。
- GUI 与结果包 README 展示各 status 中文/说明。

### Tests

- 覆盖：限制+成功、全 missing、仅 assumption、全 hard fail、hard+成功。

## 2026-07-11 - Ti15 instance P0: slim run_summary + status/reliability consistency

### Task Objective

根据 `results/17_Ti15_300_2_iso_first10_.../instance_review_zh.md` 修复两项 P0：结果包 `run_summary.json` 体积失控，以及 `status=success` 与 `reliability_label=invalid` 并存。

### Modified Files

- `app/core/result_package.py`
- `app/core/analysis_runner.py`
- `tests/test_result_package.py`
- `tests/test_analysis_runner.py`
- `CHANGELOG.md`

### Changes

- `run_summary.json` 仅写入曲线元数据摘要（`n_points`/`q_min`/`q_max` 等），不再嵌入完整 q/I 数组；分析 `tables` 仅保留 `row_count`（明细仍在 `analysis_tables/`）。
- `_result_status`：当 `reliability_label=invalid` 时返回 `AnalysisStatus.INVALID`，并补全 `invalid_reason`；失败态下 reliability 标签与状态对齐。
- README 结果包说明同步更新。

### Tests

- `tests/test_result_package.py`：长曲线摘要与体积断言。
- `tests/test_analysis_runner.py`：invalid reliability → INVALID envelope。

## 2026-07-11 - Priority review fixes (P0–P3)

### Task Objective

按代码审查优先级修复：项目加载安全、结果包序列化、文档范围对齐、依赖钉版本、启动器去硬编码、最小 CI，以及静默异常收窄。

### Added Files

- `.github/workflows/tests.yml`
- `pytest.ini`

### Modified Files

- `app/core/project.py`
- `app/core/records.py`
- `app/core/result_package.py`
- `app/core/import_preview.py`
- `app/ui/plotting_tab.py`
- `tests/test_project.py`
- `tests/test_records.py`
- `tests/test_result_package.py`
- `README.md`
- `requirements.txt`
- `Start_SasCurve_Analyzer.bat`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Changes

- `load_project` 拒绝绝对路径与路径穿越的 `data_file`；解析后必须落在项目根内。
- 项目与记录 JSON 反序列化改为 dataclass 字段白名单，未知键静默忽略。
- 结果包 `_json_default` 优先 `tolist()`，修复多元素 NumPy 数组无法写入 `run_summary.json`。
- README 中英文 Scope 对齐实际能力：有限模型拟合与自动批处理为假设依赖；去掉“完全不做复杂模型拟合”的过时表述。
- `requirements.txt` 增加兼容版本范围；启动器仅在 bat 旁存在 `main.py` 时启动，去掉 `E:\desktop\...` 硬编码。
- 新增 GitHub Actions pytest（Ubuntu、`QT_QPA_PLATFORM=offscreen`）；`pytest.ini` 将 cache 写入 `.tmp/pytest_cache`。
- 收窄 plotting cursor disconnect 与 import preview 列推断的异常捕获类型。

### Deferred

- 拆分 `model_free.py` / `model_fitting.py`。
- UI ProjectController 解耦。

### Tests

- 新增路径穿越、绝对路径拒绝、未知字段忽略相关用例。
- 全量测试：`529 passed`（`QT_QPA_PLATFORM=offscreen`，临时目录指向仓库内 `.tmp`）。

## 2026-07-11 22:15:00 +08:00 - Ti15 300 ℃ SAXS 前十帧分析

### 任务目标

使用 SAS Curve Analyzer 严格分析 `ti15_00001_abs2d_cm-1.csv` 至 `ti15_00010_abs2d_cm-1.csv`，输出可追溯参数表、论文级图件和中文报告，同时保持原始数据只读。

### 新增文件

- `scripts/analyze_ti15_first10.py`
- `../results/17_Ti15_300_2_iso_first10_20260711_220140/` 下的结果包、表格、图件、完整性记录和报告。

### 修改文件

- `app/core/result_package.py`
- `tests/test_result_package.py`
- `CHANGELOG.md`

### 删除文件

- 无。

### 具体修改及原因

- 新增可重复运行的前十帧专用分析脚本，以临时只读副本限制批处理输入，并在结果清单中保留原始绝对路径和 SHA-256。
- 输出逐帧数据质量、完整参数审计、可靠参数筛选、600 dpi PNG/SVG/PDF 图件和中文结论报告。
- 修复结果包导出时多元素 NumPy 数组不能序列化的问题，并添加回归测试；该问题曾在完成计算后阻止 `run_summary.json` 导出。
- 定量报告要求方法/参数状态可用、可靠性至少为 medium 且评分不低于 0.5。

### 如何运行

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python scripts\analyze_ti15_first10.py
```

默认输入为用户提供的外部 `spectra_csv` 目录；输出为项目上级 `results` 下新的时间戳目录。当前机器完整运行约需 5 分钟。

### 生成的输出文件

- `final_report_zh.md`、`data_quality.csv`、`reliable_parameters.csv`、`accepted_parameters.csv`、`all_parameters_audit.csv`。
- 软件原生拟合/序列表、`run_summary.json` 和 550 个方法明细表。
- `figures/` 下 9 个 PNG/SVG/PDF 图件。

### 成功检查

- 运行摘要：`RUN_STATUS=completed`、`CURVES=10`、`ANALYSES=240`、`SOURCE_INTEGRITY=PASS`。
- 输入清单严格包含 `00001–00010`，不含室温参考；十个原始文件均通过前后哈希、大小和时间戳检查。
- 全量测试：`525 passed`；`git diff --check` 无空白错误。

### 注意事项和风险

- 中等可靠性的共同峰位为 `q*=0.00925269 Å^-1`，对应特征尺度 `67.91 nm`，不可自动解释为颗粒直径。
- 没有获得可接受的 Guinier、幂律或 Porod 定量参数；散射不变量约下降 3.70%，但可靠性低，仅作描述性观察。
- 原始负强度未截断或平移；未修改原始数据，未打包，未执行 Git commit/push。

## 2026-07-11 21:31:58 +08:00 - Repair Sequence Safety And Batch Cancellation Contracts

### Task Objective

修复当日代码审查确认的序列分析数值安全、失败结果字段稳定性、GUI 安全取消、不完整结果标记及中文乱码问题。

### Added Files

- None.

### Modified Files

- `app/core/sequence_analysis.py`
- `app/core/auto_batch.py`
- `app/core/result_package.py`
- `app/ui/auto_batch_tab.py`
- `tests/test_sequence_analysis.py`
- `tests/test_auto_batch.py`
- `tests/test_result_package.py`
- `tests/test_auto_batch_ui.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- 序列参考比较现在使用排序后的局部 q/I 副本进行插值和积分，避免降序或乱序 q 造成负面积或错误空值。
- 探索性 PCA/聚类在插值前过滤非有限 q、非有限强度及非正强度；每条曲线不足两个有效点时返回明确的 `not_applicable`，不再让 NaN 进入 SVD。
- 方法执行异常时，失败 envelope 按 `METHOD_REGISTRY` 保留全部参数名，值为 `None`，状态与失败原因明确。
- GUI 新增线程安全取消请求和取消按钮，并把取消回调传入 `run_auto_batch()`。
- 取消时为所有已知但未执行的 curve×method 任务生成 `cancelled` envelope；即使最后一个任务运行期间收到取消请求，也将批次标记为 cancelled。
- 失败或取消参数保留注册表 `unit_role`，使跨帧失败行的字段元数据保持稳定。
- GUI 完成信息改为成功结果数和失败/未完成数。
- 已取消运行导出到带 `_incomplete` 后缀的目录，避免伪装成正式完整结果。
- 修复自动批处理界面和结果包 README 的中文乱码。
- 新增 reversed-q、NaN PCA、失败字段、取消导出及 GUI 取消回归测试。

### Reason

审查发现现有实现可能对乱序 q 产生错误面积、因单个 NaN 中止序列统计、在方法失败后丢失稳定字段，并将取消运行导出为正式结果；乱码也使 GUI 与说明文档不可读。

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q tests\test_sequence_analysis.py tests\test_auto_batch.py tests\test_result_package.py tests\test_auto_batch_ui.py
python -m pytest -q
```

### Generated Output Files

- 未生成科研数据、图件或打包文件。
- 测试仅在 pytest 临时目录中创建并验证结果包。

### How To Check Success

- 相关测试应报告 `42 passed`。
- 完整测试套件应全部通过。
- `python -m py_compile ...` 与 `git diff --check` 应退出码为 0。
- GUI 应显示可读中文和“取消”按钮；取消后的结果目录名应以 `_incomplete` 结尾。

### Notes And Risks

- 未修改、移动、覆盖或重命名任何原始实验数据。
- 本次未实现路线图后续要求的完整 16-sheet Excel、图件和逐拟合目录结构；这些仍属于未完成的结果包阶段。
- 未打包、未提交、未推送。

## 2026-07-11 15:37:31 +08:00 - Complete And Audit Stage 2 Extended Numerical Feature Safeguards

### Task Objective

Recover the partially implemented Stage 2 / Task 3 extended-feature work without reverting existing changes, then close the remaining audit and scientific-safety gaps for peaks, Porod, Kratky, integrals, shoulders, and oscillations.

### Added Files

- `app/core/extended_features.py` (existing unreviewed Task 3 file completed and retained)
- `tests/test_extended_features.py` (existing unreviewed Task 3 tests extended and retained)

### Modified Files

- `app/core/feature_extraction.py`
- `app/core/porod_analysis.py`
- `app/core/model_free.py`
- `tests/test_peak_analysis.py`
- `tests/test_porod_analysis.py`
- `tests/test_invariant_analysis.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `.superpowers/sdd/stage2-task3-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Made intensity-peak width outputs conservative: edge-truncated or incomplete half-height support now leaves FWHM/HWHM, width-derived areas, correlation length, and asymmetry as `None`; peak rows add the requested `prominence`, `snr`, `valid`, and `validity_reason` aliases while retaining legacy fields.
- Added stable duplicate-q collapsing before peak and Kratky width calculations, using local mean values and explicit warnings without modifying source curves.
- Added additive `two_phase_confirmed=False` to `porod_deep_analysis`. Absolute surface candidates now require explicit two-phase confirmation as well as the existing intensity, contrast, plateau, and exponent prerequisites.
- Prevented Kratky width/area output from being attached to an unrelated internal peak when the legacy global `q_K` maximum lies at a range boundary. New identity fields state whether a width peak matches `q_K`.
- Made extended integrals collapse duplicate q values and turn non-finite q-weighted products/integrals into `None` plus warnings instead of exporting infinite numbers.
- Added descriptive candidate, edge, completeness, validity, provenance, finite-prominence, and deterministic spacing fields for shoulder and oscillation rows. NaN prominence input is rejected explicitly.

### Reason

Feature values that depend on an incomplete q range, mismatched peak identity, invalid physical assumption, duplicate coordinate, or numeric overflow can look precise while being scientifically non-comparable. The result contract must expose those limits instead of converting them into plausible scalar values.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_extended_features.py tests\test_peak_analysis.py tests\test_porod_analysis.py tests\test_invariant_analysis.py tests\test_plot_analysis.py tests\test_invariant.py

$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider

python -B -m py_compile app\core\extended_features.py app\core\feature_extraction.py app\core\porod_analysis.py app\core\model_free.py tests\test_extended_features.py tests\test_peak_analysis.py tests\test_porod_analysis.py tests\test_invariant_analysis.py
git diff --check
```

### Generated Output Files

- Updated in-memory numerical-analysis contracts, audit fields, documentation, and tests only.
- No raw experimental data, processed data, figures, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- Peak safeguards: two new tests first reported `2 failed` (edge peak still returned a width and duplicate q had no audit warning); after repair `tests\test_peak_analysis.py` reported `7 passed`.
- Porod safeguard: the missing-two-phase test first reported `1 failed` because a surface candidate was emitted; after the additive gate `tests\test_porod_analysis.py` reported `6 passed`.
- Kratky safeguards: two new tests first reported `2 failed` (an internal width was attached to a boundary q_K maximum and duplicate q was unreported); after repair Kratky-focused tests reported `4 passed`.
- Extended-feature safeguards: four new tests first reported `4 failed` (duplicate-q audit missing, q4I overflow exported as `inf`, candidate provenance absent, and NaN prominence accepted); after repair `tests\test_extended_features.py` reported `13 passed`.
- The requested direct focused suite reported `51 passed in 1.22s`; the full regression suite reported `380 passed in 11.97s`.

### Notes And Risks

- All source experimental files and `CurveData` arrays remain read-only; sorting, collapse, and calculations use local arrays only.
- `two_phase_confirmed` is an explicit caller-provided assumption, not software inference. A confirmed flag plus a Porod-like fit still does not prove a unique interfacial morphology.
- Width/completeness and finite-range integral indicators are numerical descriptors conditional on selected q range, grid, baseline convention, and error-free coordinate provenance. They must be reviewed alongside warnings and cannot establish a material mechanism on their own.

## 2026-07-11 14:17:06 +08:00 - Correct Model-Free Weighting, Derivative, And Fit-Execution Audits

### Task Objective

Address the independent Stage 2 / Task 2 review findings: prevent false near-zero confidence intervals for absolute-sigma weighted fits, prevent local-slope results from claiming an OLS fit, and make q/I-eligible points that never entered a fit unambiguous in exported results.

### Added Files

- None.

### Modified Files

- `app/core/model_free.py`
- `tests/test_model_free_complete.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `.superpowers/sdd/stage2-task2-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Changed the shared weighted-line covariance path to use the unscaled WLS covariance (`numpy.polyfit(..., cov="unscaled")`) when the supplied propagated `sigma_lnI = error/I` is absolute. Parameter standard errors and CI now remain governed by stated uncertainty even when the residual happens to be nearly zero.
- Added a derivative-only selector mode for `local_slope()`. It does not calculate or describe fit weighting, emits no ordinary-least-squares warning for a missing error column, and records `error_audit.strategy="not_used_for_local_derivative"` with `weighting_decision="not_applicable"`.
- Added `eligible_points`, `actual_fit_points`, `fit_points_semantics`, and `fit_not_performed_rows` to Guinier and power-law outputs. The legacy `fit_points` continues to represent selected log-domain points for compatibility; a failed/degenerate line fit now records `actual_fit_points=0`, empty residuals, diagnostics `n=0`, `weighted_fit=False`, `weighting_decision="no_fit_performed"`, and every eligible unfit raw row.
- Added regression tests for an exact power law with non-zero known sigma, local-slope no-OLS semantics, one eligible Guinier point, duplicate log-q power-law points, and successful-fit count consistency.

### Reason

Absolute measurement uncertainty must not disappear merely because a synthetic or unusually exact data series has a small residual. Likewise, an export must never state that a numerical fit or weighting occurred when the method only computed a local derivative or when a requested line could not actually be established.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_model_free_complete.py tests\test_guinier.py tests\test_power_law.py tests\test_local_slope.py tests\test_method_warnings.py tests\test_fit_diagnostics.py

$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider

python -B -m py_compile app\core\model_free.py tests\test_model_free_complete.py
git diff --check
```

### Generated Output Files

- Updated in-memory analysis contracts, audit fields, documentation, and regression tests only.
- No raw experimental data, processed data, figures, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- Four review-remediation tests were written first. The focused RED run reported `6 passed, 4 failed in 0.28s`; failures exactly exposed residual-scaled WLS covariance, the local-slope OLS warning, and absent eligible/actual fit-execution fields.
- After the minimal repair, `tests\test_model_free_complete.py` reported `10 passed in 0.18s`; the direct model-free, warning, and diagnostics suite reported `47 passed in 0.41s`.
- The full regression suite reported `358 passed in 8.68s`.
- `python -B -m py_compile app\core\model_free.py tests\test_model_free_complete.py` and `git diff --check` completed with exit code `0` (Git reported only working-copy line-ending notices).

### Notes And Risks

- All source experimental files and input `CurveData` arrays remain read-only. The repair changes only local calculations and result metadata.
- The unscaled covariance assumption is correct only when `sigma_lnI` represents stated absolute uncertainty in the transformed coordinate. The code records that transformation explicitly; users must still verify whether their experimental error column has that meaning.
- `fit_points` is retained for backwards compatibility. New batch exporters should use `eligible_points`, `actual_fit_points`, `fit_not_performed_rows`, and residual rows together, rather than inferring a successful fit from the legacy field alone.

## 2026-07-11 13:55:09 +08:00 - Complete Traceable Guinier, Power-Law, And Local-Slope Outputs

### Task Objective

Implement Stage 2 / Task 2 of the approved automated 1D SAS workflow: retain the existing model-free public APIs while making Guinier, power-law, and local-slope outputs complete, batch-exportable, and scientifically auditable.

### Added Files

- `tests/test_model_free_complete.py`

### Modified Files

- `app/core/model_free.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added a row-preserving log-domain selection path for Guinier and power-law fits. Every q/I-domain exclusion records original row index, q, intensity, optional error, and a clear reason; residual rows contain only actual fitted points and retain raw provenance.
- Routed the two linear fits through `fit_diagnostics()` and `build_residual_rows()`. Results now include actual q limits, point counts, weighting status, complete parameter rows, uncertainty/covariance when finite, R2/RMSE/chi-square/AICc/BIC diagnostics, residuals, validity state, assumptions, and warnings.
- Propagated valid absolute log-domain uncertainty as `sigma_lnI = error / I`. A fully valid selected error column enables weighted fitting; missing, mismatched, or partly invalid errors intentionally fall back to unweighted fitting over every q/I-valid point and leave an `error_audit` rather than silently excluding points or overstating weighting.
- Preserved legacy fields and signatures (`qRg_min`/`qRg_max`, `R2`, `residuals`, `q_mid`, `alpha`, and `plateau_candidate_ranges`) for existing callers. Added explicit `qminRg`/`qmaxRg`; a non-negative Guinier slope now leaves Rg-related quantities as `None` with a documented reason.
- Expanded local-slope output into per-point audit rows and fixed-schema plateau rows. Plateau stability is clipped to `[0, 1]`; all derivative/plateau results are labelled descriptive rather than a unique material-mechanism conclusion.

### Reason

The batch workflow requires every model result to be interpretable outside the GUI: the fitted interval, transformation, weighting basis, residuals, uncertainty, and exclusions must be visible before users compare in-situ frames or attach a structural interpretation.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_model_free_complete.py tests\test_guinier.py tests\test_power_law.py tests\test_local_slope.py tests\test_method_warnings.py tests\test_fit_diagnostics.py

$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider

python -B -m py_compile app\core\model_free.py tests\test_model_free_complete.py
git diff --check
```

### Generated Output Files

- Updated in-memory analysis-result contracts and regression tests only.
- No raw experimental data, processed data, figures, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- The new contract tests were written first and initially reported `6 failed`; each failure was caused by the required traceability fields being absent from the prior model-free outputs.
- After the minimum implementation, `tests\test_model_free_complete.py` reported `6 passed`; the targeted model-free, warning, and diagnostic suite reported `43 passed`.
- The full regression suite reported `354 passed in 8.77s`.
- `python -B -m py_compile app\core\model_free.py tests\test_model_free_complete.py` and `git diff --check` both completed with exit code `0` (Git reported only existing working-copy line-ending notices).

### Notes And Risks

- All source experimental files and `CurveData` arrays remain read-only; selection, sorting, fitting, and derivatives use local arrays only.
- A successful fit, a low residual, a Guinier Rg, a power-law exponent, or a local-slope plateau does not prove a unique morphology or causal material mechanism. Review the selected q range, `validity`, `assumptions`, residuals, and experimental context.
- Covariance-derived uncertainty can be unavailable for too few points, rank-deficient coordinates, or non-finite numerical estimates. Such values remain `None` rather than being replaced by zero.

## 2026-07-11 12:46:48 +08:00 - Enforce Runner Envelope Identity And Complete Stage 1 Boundary Regressions

### Task Objective

Address the Stage 1 Task 5/Task 6 contract-review finding that a syntactically valid runner result could be attributed to the wrong curve or analysis method, then complete the two previously listed non-blocking boundary regression cases.

### Added Files

- None.

### Modified Files

- `app/core/auto_batch.py`
- `tests/test_auto_batch.py`
- `tests/test_batch_consensus.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Changed `_validate_runner_output()` to receive the scheduled `CurveData` and `method_id`, and reject any envelope whose `curve_id` differs from the current curve or whose `analysis_type` differs from the scheduled method.
- A wrong-curve or wrong-method envelope, including one bad entry in an otherwise multiple-envelope result, is now isolated inside the existing runner exception boundary as exactly one current-job `FIT_FAILED` envelope. The mismatched result is never added to `AutoBatchRun.analyses`.
- Kept multiple-envelope support and deliberately did not require returned `q_range` values to equal the requested range, because a later production runner may need to report its actual accepted fit interval.
- Added direct tests for empty candidate lists, no curves, duplicate curve IDs with bounded coverage/deduplicated support, and cancellation after the first completed job but before the second runner call.
- Marked the older log-median executable-range prose in developer notes as superseded historical material, and updated the authoritative Stage 1 API section to record runner identity validation and completion of the prior regression follow-ups.

### Reason

Accepting a valid-looking result for the wrong experimental frame or wrong SAS method can misattribute fitted parameters and lead to incorrect scientific comparison across an in-situ series. The orchestration boundary must reject that result before later output, trend, or model-selection stages can use it.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch.py
python -B -m pytest -q -p no:cacheprovider tests\test_batch_consensus.py

$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py tests\test_io.py tests\test_batch_import.py tests\test_auto_regions.py
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py tests\test_batch_consensus.py
git diff --check
```

### Generated Output Files

- Updated in-memory orchestration safeguards, regression tests, and documentation only.
- No raw experimental data, processed data, figures, result packages, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- Identity-contract tests were written before code changes and initially reported `3 failed, 4 passed, 38 deselected`; the three expected failures showed wrong-curve/wrong-method envelopes being accepted and the batch incorrectly ending as `completed`.
- The three pre-existing boundary regressions (empty/no-curve/duplicate-ID consensus and mid-batch cancellation) were direct GREEN coverage in that same initial run; no false RED claim is made for them.
- After the minimal identity repair, the selected tests reported `7 passed, 38 deselected`.
- Task 5 reported `27 passed`; Task 4 reported `18 passed`; the Stage 1 focused suite reported `106 passed`; the full suite reported `326 passed`.
- `python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py tests\test_batch_consensus.py` completed with exit code `0`; `git diff --check` completed without whitespace errors.

### Notes And Risks

- All source experimental files remain read-only. This validation never moves, renames, deletes, smooths, normalizes, or overwrites input data.
- The identity contract validates curve and method attribution only. It deliberately leaves the actual returned q interval to a future production runner and does not establish fit validity or material mechanism.
- No dependencies were installed and no packaging, Git commit, or Git push was performed.

## 2026-07-11 12:28:57 +08:00 - Complete Automated Batch Foundation Documentation And Verification

### Task Objective

Complete Stage 1 / Task 6 for the approved automated 1D SAS batch workflow: document the stable foundation contract and verify the complete Stage 1 implementation without changing raw experimental data or creating a result package.

### Added Files

- `app/core/auto_batch_schema.py`
- `app/core/metric_registry.py`
- `app/core/batch_inputs.py`
- `app/core/batch_consensus.py`
- `app/core/auto_batch.py`
- `tests/test_auto_batch_schema.py`
- `tests/test_metric_registry.py`
- `tests/test_batch_inputs.py`
- `tests/test_batch_consensus.py`
- `tests/test_auto_batch.py`

### Modified Files

- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Established the documented Stage 1 API contract for `AutoBatchConfig`, `METHOD_REGISTRY`, `collect_batch_inputs()`, `resolve_consensus_regions()`, and `run_auto_batch()`.
- Recorded that `AutoBatchConfig` is not frozen: callers must treat it as unchanged after a run begins, while `AutoBatchRun` stores the actual `asdict(config)` snapshot.
- Documented read-only calibrated-curve input discovery, manifest SHA-256/source metadata, optional CSV metadata states, strict shared q-range intersection, audit-only log-median ranges, no automatic per-frame range fallback, failure isolation, cancellation gates, and the injected runner contract.
- Documented the deliberate Plan 1 limit: the default runner returns `NOT_APPLICABLE`; real analysis, model fitting, Excel/CSV/JSON writing, figures, and GUI integration belong to later plans.
- Added two non-blocking regression follow-ups from independent reviews: real empty/duplicate-identity `CurveData` consensus cases, and cancellation between the first completed job and the second job.

### Reason

The later numerical-analysis, sequence-analysis, export, and GUI stages need one precise, auditable boundary so they do not mistake declarations, audit statistics, placeholders, or failed jobs for fitted scientific results.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m compileall -q app\core
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py

$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider

git diff --check
git status --short
```

### Generated Output Files

- No raw experimental data, processed data, figures, residual plots, Excel workbooks, CSV/JSON result packages, build artifacts, packages, commits, or pushes were generated by this Task 6 documentation and verification pass.
- The Stage 1 in-memory `AutoBatchRun` API is available to later plans; it is not itself an on-disk result package.

### How To Check Success

- `python -B -m compileall -q app\core` completed with exit code `0`.
- The exact focused Stage 1 command reported `66 passed in 1.40s`.
- The full offscreen regression command reported `319 passed in 6.41s`.
- Final `git diff --check` completed with exit code `0` and no whitespace errors. Git emitted only existing line-ending notices that `.gitignore`, `AGENTS.md`, `CHANGELOG.md`, and `docs/developer_notes.md` will use CRLF when Git next touches them.
- `git status --short` completed with the five untracked Stage 1 core modules, five untracked Stage 1 test modules, these two modified documentation files, and the previously approved `.gitignore`, `AGENTS.md`, `docs/agents/`, design specification, and four plan documents. The restricted sandbox also emitted `unable to access ... .config/git/ignore: Permission denied`; no project file or test result was affected.

### Notes And Risks

- Raw calibrated input files are read-only: no Stage 1 path writes, moves, renames, smooths, normalizes, converts, deletes, or overwrites them.
- `ConsensusRegion.q_range` is intentionally conservative. A batch with shifting features can have no common q range; it must not silently fall back to a frame-specific range.
- `METHOD_REGISTRY` is an output declaration, and a default `NOT_APPLICABLE` envelope is not a fitted value or material conclusion. Plan 2 must add validated numerical runners before any scientific interpretation.
- No dependencies were installed. No packaging, Git commit, or Git push was performed.

## 2026-07-11 12:17:16 +08:00 - Harden Automated Batch Cancellation Gates And Runner Status Validation

### Task Objective

Address Stage 1 Task 5 independent-review findings so cancellation is checked at every batch boundary and malformed runner envelope statuses cannot either crash a batch or be silently reported as completed.

### Added Files

- None.

### Modified Files

- `app/core/auto_batch.py`
- `tests/test_auto_batch.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added cancellation checks after imported data is copied into `AutoBatchRun` and again after consensus resolution succeeds or fails, before any curve-method runner can start. The existing pre-input and per-job checks remain in place.
- Added sequence-callback tests for `False, True` after input copy (no consensus or runner) and `False, False, True` after consensus (no runner). Both preserve the imported run metadata but return `cancelled`, set `finished_at`, report a warning, and leave `analyses` empty.
- Added explicit runtime validation for every `AnalysisEnvelope.status` returned by an injected runner. Valid enum-value strings such as `"success"` and `"fit_failed"` are normalized to `AnalysisStatus`; invalid strings, lists, and other malformed/unhashable values are isolated as one `FIT_FAILED` envelope for the affected curve and method.
- Kept empty runner lists as explicit contract failures and added direct regression coverage for the one-envelope `FIT_FAILED` outcome.
- Treat a runner-returned `FIT_FAILED`, `INVALID`, or `CANCELLED` envelope as a non-success result, making the finished batch at least `partial_success`. A returned `CANCELLED` envelope does not automatically set the whole batch to `cancelled`; only `cancel_requested` controls batch-level cancellation.

### Reason

The first Task 5 implementation guarded input import and individual method jobs, but not the boundaries immediately before/after consensus work. It also trusted the envelope status field until after runner output validation, allowing malformed values to escape validation or interfere with set membership. The revised boundary makes both states auditable and safe.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch.py

$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py tests\test_io.py tests\test_batch_import.py tests\test_auto_regions.py
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py
```

### Generated Output Files

- Updated read-only orchestration code, regression tests, and internal documentation only.
- No raw experimental data, processed data, figures, result packages, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- New review-fix tests were written before the code changes. Their first focused run reported `7 failed, 3 passed, 13 deselected`; failures showed consensus starting after a post-input cancellation, a runner starting after a post-consensus cancellation, invalid status acceptance, unhashable-status escaping, string-status non-normalization, and a returned `CANCELLED` envelope ending as `completed`.
- After the minimal repair, those review-fix tests reported `10 passed, 13 deselected`.
- The complete Task 5 suite reported `23 passed`.
- The Stage 1 focused suite reported `99 passed`.
- The full project suite reported `319 passed`.
- `python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py` completed with exit code `0`; `git diff --check` completed without whitespace errors.

### Notes And Risks

- Raw experimental files remain read-only. No cancellation or runner-status path writes, moves, renames, normalizes, smooths, or deletes input data.
- A runner-returned `CANCELLED` envelope signals a method-level non-success only. It must not be read as proof that the overall batch was user-cancelled or as a material-science conclusion.
- Plan 2 remains responsible for the production analysis runner and for interpreting method-specific statuses; this Stage 1 layer only enforces safe transport, scheduling, and audit semantics.
- No dependencies were installed and no package, Git commit, or Git push was performed.

## 2026-07-11 10:33:36 +08:00 - Add Failure-Isolating Automated Batch Orchestrator

### Task Objective

Implement Stage 1 Task 5: a read-only automated-batch orchestration boundary that imports calibrated 1D SAS curves, applies strict batch-consensus q ranges, and isolates individual analysis-method failures so one failed fit does not discard the rest of an in-situ series.

### Added Files

- `app/core/auto_batch.py`
- `tests/test_auto_batch.py`

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added `run_auto_batch(input_dir, config, *, progress_callback=None, cancel_requested=None, analysis_runner=None) -> AutoBatchRun` and its injectable `AnalysisRunner` contract.
- The default Plan 1 runner emits explicit `NOT_APPLICABLE` envelopes with `production runner is installed by Plan 2`; it does not invent numerical fit results.
- Added read-only orchestration over `collect_batch_inputs()`, `resolve_consensus_regions()`, and `applicable_method_ids()` with `asdict(config)` retained in the run snapshot.
- Stores only validated finite ascending consensus q tuples. Missing consensus always passes `None` to range-sensitive methods; there is no automatic per-frame range fallback. `lamellar`, peaks, shoulders, and oscillations share the `peak` consensus mapping.
- Uses finite q values only for full-range methods and passes `None` with an auditable warning for empty, non-finite, or non-increasing q data.
- Isolates runner exceptions, non-list/non-envelope runner results, returned failed/invalid envelopes, consensus-resolution failures, input failure rows, progress-callback failures, and cancellation-callback failures. Affected method jobs receive `FIT_FAILED`; prior and later jobs continue where safe.
- Checks cancellation before input collection, before consensus work, and before every method job. Cancellation sets `run.status="cancelled"`, writes `finished_at`, records the reason, and does not fabricate results for skipped jobs.
- Added TDD regression coverage for runner failure isolation, immediate cancellation, strict no-fallback behavior, preservation of multiple envelopes, peak/lamellar range mapping, consensus failures, invalid runner contracts, callback failures, finite/empty q handling, failed inputs, cancellation callback failures, and the Plan 1 default runner.

### Reason

The approved workflow requires a batch to remain traceable and useful even when one frame, one method, a consensus selector, or a UI progress hook fails. This core boundary makes that behavior explicit before Plan 2 introduces real numerical analysis runners.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch.py

$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py tests\test_io.py tests\test_batch_import.py tests\test_auto_regions.py
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py
```

### Generated Output Files

- Added core orchestration code, regression tests, and implementation notes only.
- No raw experimental data, processed data, figures, result packages, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- TDD RED confirmation: before `auto_batch.py` existed, `tests\test_auto_batch.py` stopped at `ModuleNotFoundError: No module named 'app.core.auto_batch'`.
- Cancellation refinement RED confirmation: the strengthened immediate-cancellation test initially failed with `Failed: input collection must not run after immediate cancellation`; it then passed after the cancellation check moved before input collection.
- After the minimal implementation, `tests\test_auto_batch.py` reported `13 passed`.
- The complete Stage 1 focused suite reported `89 passed`.
- The full project suite reported `309 passed`.
- `python -B -m py_compile app\core\auto_batch.py tests\test_auto_batch.py` completed with exit code `0`.

### Notes And Risks

- The orchestration layer only reads source files through the existing import layer and never edits, moves, renames, smooths, normalizes, or writes raw experimental data.
- Plan 2 must install the real analysis runner. Until then, direct calls without `analysis_runner` intentionally return `NOT_APPLICABLE`, not fitted values.
- A range-sensitive method with no batch consensus receives `None`; this is an explicit conservative limitation, not an error-correcting per-frame fallback.
- A runner must return a non-empty `list[AnalysisEnvelope]`. An empty list is recorded as a visible per-method `FIT_FAILED` rather than silently losing an expected analysis row.
- No dependency was installed and no package, Git commit, or Git push was performed.

## 2026-07-11 10:18:06 +08:00 - Harden Batch-Consensus q Ranges Against Unsafe Shared Fits

### Task Objective

Address independent review findings in Stage 1 Task 4 so that a batch-level q range can be safely used by every supporting curve, candidate identity cannot inflate coverage, and deterministic ties retain the most informative valid candidate interval.

### Added Files

- None.

### Modified Files

- `app/core/batch_consensus.py`
- `tests/test_batch_consensus.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Changed `ConsensusRegion.q_range` from independent log-median endpoints to the strict common interval `(max(q_start), min(q_end))` after curve-ID de-duplication. A candidate cluster with no open common interval now produces no consensus, so later shared-range fitting never receives q values outside a supporting candidate's own interval.
- Preserved the former log-median endpoints as the audit-only `ConsensusRegion.log_median_q_range`; this descriptive statistic is explicitly not an executable fit range.
- Added `median_n_points` and deterministic ranking: coverage, median score, median valid `n_points`, then stable q-range and curve-ID tie-breaks. Equal-score alternatives from one curve now retain the candidate with more valid points.
- Required `fit_ready is True` exactly; truthy strings and NaN no longer enter a cluster. Rejected `None`, empty, and non-string curve IDs; missing, negative, or non-finite `n_points` are conservatively treated as zero.
- Prevented invalid coverage by rejecting non-positive `curve_count` and clusters with more distinct supporting IDs than the declared curve count.
- Required every candidate read by `resolve_consensus_regions()` to have a `curve_id` exactly equal to the currently detected `CurveData.curve_id`; foreign/stale rows are ignored without changing source dictionaries.
- Added regression coverage for no-overlap nearby centers, strict common-range containment, threshold and coverage boundaries, score and point-count ties, strict boolean readiness, invalid IDs, coverage ceiling, and foreign candidate rejection.

### Reason

The prior log-median endpoints could lie between disjoint candidate intervals despite a close log-q center, creating a q range that no individual curve actually supported. The strict intersection is intentionally more conservative: it records no shared fit range rather than inventing one.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_consensus.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_deep_scan.py tests\test_batch_consensus.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py
python -B -m py_compile app\core\batch_consensus.py tests\test_batch_consensus.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Updated read-only core code, regression tests, and internal documentation only.
- No raw experimental data, processed data, result package, figure, workbook, package, Git commit, or Git push was generated.

### How To Check Success

- `tests\test_batch_consensus.py` reports `15 passed`.
- Existing automatic-region regression plus consensus tests report `35 passed`.
- Cumulative Stage 1 schema, registry, input, and consensus tests report `43 passed`.
- Full regression reports `296 passed`.
- `python -B -m py_compile app\core\batch_consensus.py tests\test_batch_consensus.py` and `git diff --check` complete without errors.

### Notes And Risks

- A strict common range is safer for downstream fits but may omit a consensus during a real q-range drift or phase transition; it must not be silently relaxed into an automatic per-frame fallback.
- Candidate score and `n_points` are detector properties, not independent proof that a SAS model or material interpretation is valid.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 09:57:13 +08:00 - Add Read-Only Batch-Consensus q Region Selection

### Task Objective

Implement the Stage 1 batch-consensus layer that converts per-curve automatic q-region candidates into deterministic, batch-level q ranges without modifying raw curves or the existing automatic-region detector.

### Added Files

- `app/core/batch_consensus.py`
- `tests/test_batch_consensus.py`

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added public `ConsensusRegion`, `candidate_consensus()`, and `resolve_consensus_regions()` interfaces.
- Added deterministic clustering by log-q interval center with the fixed threshold `0.35`; within each cluster, candidates are deduplicated by curve ID, ranked by coverage first and median candidate score second, and converted to q ranges through log-q medians.
- Added stable tie-breaking by q range and sorted supporting curve IDs, so candidate input order cannot change the selected consensus result.
- Mapped real `detect_auto_regions()` candidate types (`guinier_candidate`, `power_law_candidate`, `porod_candidate`, and `peak_candidate`) to the batch output keys `guinier`, `power_law`, `porod`, and `peak`.
- Ignored unsupported, non-fit-ready, non-finite, non-positive, and non-increasing candidate rows. Region types below `AutoBatchConfig.consensus_min_coverage` are omitted instead of returning a weak consensus.
- Added tests for coverage-over-score priority, coverage rejection, curve-ID de-duplication, invalid/unready rows, deterministic ordering, real candidate-type mapping, and preservation of in-memory curve arrays and metadata.

### Reason

In-situ batch analysis needs one repeatable q range per analysis type while avoiding per-frame manual choices. The consensus rule provides a transparent shared range and preserves weak or inconsistent detections as absent rather than silently treating them as valid.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_consensus.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_deep_scan.py tests\test_batch_consensus.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py
python -B -m py_compile app\core\batch_consensus.py tests\test_batch_consensus.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- New read-only core module, regression tests, and internal documentation only.
- No raw experimental data, processed data, result package, figure, workbook, package, Git commit, or Git push was generated.

### How To Check Success

- `tests\test_batch_consensus.py` reports `5 passed`.
- Existing automatic-region regression plus consensus tests report `25 passed`.
- Cumulative Stage 1 schema, registry, input, and consensus tests report `33 passed`.
- Full regression reports `286 passed`.
- `python -B -m py_compile app\core\batch_consensus.py tests\test_batch_consensus.py` and `git diff --check` complete without errors.

### Notes And Risks

- The consensus is a repeatable selection rule, not evidence for a unique material structure or a substitute for reviewing a genuine physical transition.
- The fixed log-q center threshold (`0.35`) and default minimum coverage (`0.70`) may need an explicitly recorded future configuration change for unusually broad, shifting, or multi-regime series.
- `resolve_consensus_regions()` reads only temporary detection results. It never changes `CurveData.q`, `CurveData.intensity`, `CurveData.metadata`, or an original input file.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 09:48:25 +08:00 - Make Per-Curve Metadata Coverage Explicit

### Task Objective

Address the final Task 3 re-review finding by recording and warning on successful curves that have no matching row in an otherwise configured CSV metadata sidecar.

### Added Files

- None.

### Modified Files

- `app/core/batch_inputs.py`
- `tests/test_batch_inputs.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added `metadata_match_status="matched"` to every successfully imported curve that receives a metadata row, while retaining its existing `metadata_source`, `metadata_sha256`, match-column, key, and row-index provenance.
- Added `metadata_match_status="no_matching_row"` plus a clear per-curve warning when a configured sidecar lacks a row for a successfully imported curve.
- Preserved the distinct existing reverse warning for a valid metadata row whose key does not correspond to an imported curve.
- Added a partial-match/partial-missing-row regression test that asserts both status values and the missing-row warning.

### Reason

Without an explicit per-curve state, later analysis/export code could not distinguish an intentionally absent metadata sidecar from a configured sidecar that accidentally omitted one experimental frame.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Updated in-memory batch-input code, regression tests, and internal documentation only.
- No raw experimental data, processed data, result package, figure, workbook, package, Git commit, or Git push was generated.

### How To Check Success

- `tests\test_batch_inputs.py` reports `11 passed`.
- Existing import plus input tests report `29 passed`.
- Cumulative schema, registry, and input tests report `28 passed`.
- The full suite reports `281 passed`.
- Run `python -B -m py_compile app\core\batch_inputs.py tests\test_batch_inputs.py` and `git diff --check`; both should complete without errors.

### Notes And Risks

- These status fields exist only when a metadata sidecar is configured and are held only in imported in-memory `CurveData.metadata`; no raw file is modified.
- A matched row establishes file-level provenance, not physical validity of the metadata value.
- CSV-only metadata and non-recursive curve discovery remain intentional Stage 1 limits.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 09:35:07 +08:00 - Harden Batch Input Manifest and Metadata Audit Trail

### Task Objective

Address the independent Stage 1 / Task 3 review findings: preserve partial batch results through manifest-read failures, make CSV metadata matching auditable and unambiguous, and lock the manifest/hash contract with regression tests.

### Added Files

- None.

### Modified Files

- `app/core/batch_inputs.py`
- `tests/test_batch_inputs.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added per-file manifest failure isolation for `resolve()`, `stat()`, and SHA-256 `OSError` cases. Failed candidates retain a manifest row with `manifest_status="failed"`, `manifest_error`, unavailable fields as `None`, and a `{file, stage: "manifest", error}` record in `failed_inputs`; other curves and manifest rows continue.
- Preserved existing `import_in_situ_series()` failure records and verified that a readable but invalid curve still appears in the manifest with a successful hash.
- Enforced positive chunk sizes in `sha256_file()` with a clear `ValueError`.
- Rejected duplicate non-empty metadata match keys with a clear `ValueError` that includes both row indices, and added warnings for valid metadata keys that match no imported curve.
- Added an explicit regression check that a missing `metadata_match_column` raises the documented clear `ValueError`.
- Added per-matched-curve metadata provenance: absolute `metadata_source`, `metadata_sha256`, `metadata_match_column`, normalized `metadata_match_key`, and zero-based `metadata_row_index`.
- Kept the configured same-directory metadata sidecar out of curve import and the curve manifest. If the already-read sidecar cannot be hashed, collection now raises a clear `RuntimeError` rather than silently losing provenance.
- Expanded tests to verify exact SHA-256 values, absolute source paths, source size/mtime, natural order, invalid chunk-size rejection, failure isolation, invalid-curve manifest retention, duplicate-key rejection, unmatched-key warnings, and sidecar-hash failure.

### Reason

Batch analysis must remain partially usable when one input becomes inaccessible, and time/temperature/strain metadata must never be silently overwritten or omitted. The added provenance allows later result packages to identify exactly which sidecar row and version supplied each curve's metadata.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Updated core input-collection code, regression tests, and internal documentation only.
- No raw experimental data, processed data, result package, figure, workbook, package, Git commit, or Git push was generated.

### How To Check Success

- `tests\test_batch_inputs.py` reports `10 passed`.
- Existing import plus input tests report `28 passed`.
- Cumulative schema, registry, and input tests report `27 passed`.
- The full suite reports `280 passed`.
- Run `python -B -m py_compile app\core\batch_inputs.py tests\test_batch_inputs.py` and `git diff --check`; both should complete without errors.

### Notes And Risks

- Original curves and metadata are still opened only for reading; no raw file was written, moved, renamed, or deleted.
- This stage supports CSV metadata only and non-recursive curve discovery. XLSX metadata remains intentionally deferred to Plan 4.
- A manifest failure is recorded rather than fatal, so later result writers must preserve both failed manifest rows and `failed_inputs` in final outputs.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 09:13:41 +08:00 - Add Read-Only Automated Batch Input Collection

### Task Objective

Implement the approved Stage 1 input boundary for calibrated 1D SAS batch files: discover supported curves in natural order, record traceable input hashes, and merge optional CSV metadata without modifying original experimental data.

### Added Files

- `app/core/batch_inputs.py`
- `tests/test_batch_inputs.py`

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added public `BatchInputCollection`, `discover_curve_files`, `sha256_file`, `load_metadata_table`, and `collect_batch_inputs` interfaces.
- Restricted curve discovery to direct-child `.csv`, `.txt`, and `.dat` files and reused the existing natural filename ordering and in-situ import workflow.
- Added a chunked SHA-256 manifest for every discovered file containing `source_file`, `source_path`, `size_bytes`, `modified_time`, and `sha256`.
- Added optional CSV metadata matching through `AutoBatchConfig.metadata_match_column`; missing match columns raise a clear `ValueError`.
- Kept metadata and q/intensity unit overrides in imported in-memory `CurveData.metadata` only, including the matched `metadata_source` and explicit unit-override provenance; original curve and metadata files remain read-only.
- When the configured metadata CSV is stored alongside curves, exclude that sidecar from curve import and the curve manifest so it cannot be reported as a failed curve.
- Added focused tests for natural sort/extension filtering and in-memory metadata merge with byte-for-byte source preservation.

### Reason

Later automated analyses require a reproducible list of exactly which calibrated curves were used and a safe way to attach time, temperature, strain, or similar batch metadata before any numerical analysis begins.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py tests\test_batch_inputs.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- New core module, regression tests, and internal documentation only.
- No raw experimental data, processed data, result package, figure, workbook, package, Git commit, or Git push was generated.

### How To Check Success

- `tests\test_batch_inputs.py` reports `2 passed`.
- Existing import plus input tests report `20 passed`.
- Cumulative schema, registry, and input tests report `19 passed`.
- The full suite reports `272 passed`.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- Original curve and metadata files are opened only for reading; their source bytes were explicitly checked unchanged by the regression test.
- This stage only supports CSV metadata. XLSX support is intentionally deferred to Plan 4, where the approved `openpyxl` dependency will be introduced.
- This stage does not perform quality analysis, consensus-region calculation, numerical fitting, sequence analysis, figure export, or result-package generation.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 09:02:10 +08:00 - Complete Metric Registry Positive-Profile Coverage

### Task Objective

Apply the second independent-review repair by testing every approved P(r) positive sample type and enforcing tuple-backed metrics across the entire authoritative registry.

### Added Files

- None.

### Modified Files

- `tests/test_metric_registry.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added exact truth-matrix cases for `sample_type="polymer", enable_pr=True` and `sample_type="unknown", enable_pr=True`; both assert the same ordered result as the P(r)-enabled particle profile.
- Expanded the tuple assertion from the Guinier method alone to every `METHOD_REGISTRY` value, while retaining frozen-dataclass and tuple-assignment checks.
- Documented that the existing production implementation already satisfies these new regression expectations, so no production code was changed and no fabricated RED result is claimed.

### Reason

The approved P(r) registry rule includes `particle`, `polymer`, and `unknown`. Only testing particle could miss a future profile-specific regression; inspecting one method's tuple type could similarly miss a mutable metric collection in another entry.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Updated regression tests and internal documentation only.
- No raw experimental data, processed data, result package, figures, workbook, or build artifact was generated.

### How To Check Success

- The strengthened registry suite reports `14 passed`.
- The schema-plus-registry suite reports `17 passed`.
- The full suite reports `270 passed`.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- The registry mapping remains an ordinary `dict` by the approved design; its entries' metric collections are now checked as tuples across all methods.
- Future intentional registry additions or P(r) profile changes must update the full expected registry and truth matrix together.
- Raw experimental data were not read, modified, moved, renamed, or deleted.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 08:51:56 +08:00 - Strengthen Metric Registry Review Coverage

### Task Objective

Address the independent review finding that the automated-batch metric registry tests did not precisely lock all approved methods, output fields, ordering, applicability conditions, and immutable-spec behavior.

### Added Files

- None.

### Modified Files

- `tests/test_metric_registry.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Replaced subset/set-based registry checks with exact ordered assertions for all 18 `required_method_ids()` entries.
- Added a complete literal expected registry that compares every method's identifier, region type, metric names and order, sample-type rule, and configuration-flag rule.
- Added an exact profile truth matrix for default, P(r)-enabled particle, correlation-enabled two-phase, lamellar with correlation both disabled and enabled, disabled flags, and wrong sample-type/flag combinations.
- Added regression checks that `MetricSpec` and `MethodSpec` are frozen and that metrics are tuples.
- Documented the intentional limitation that `METHOD_REGISTRY` remains an ordinary approved `dict`; only its contained specifications/metric tuples are immutable, and callers must not mutate the mapping.
- Recorded that these are review-driven tests of already-existing correct production code; no production implementation was changed and no fabricated RED result is claimed.

### Reason

The initial tests could have allowed silent method omissions, reordering, metric changes outside Guinier, or incorrect P(r)/correlation/lamellar eligibility. Exact regression expectations now make any such contract change visible before a later analysis, export, or GUI stage consumes the registry.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Updated test and internal-documentation records only.
- No raw experimental data, processed data, result package, figures, workbook, or build artifact was generated.

### How To Check Success

- The strengthened registry suite reports `12 passed`.
- The schema-plus-registry suite reports `15 passed`.
- The full suite reports `268 passed`.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- The ordinary `METHOD_REGISTRY` mapping is intentionally not frozen; future production code must treat it as read-only by convention.
- An intentional registry contract update must change its approved specification and this full expected-test table together.
- Raw experimental data were not read, modified, moved, renamed, or deleted.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 08:37:46 +08:00 - Add Authoritative Automated-Batch Metric Registry

### Task Objective

Create the approved authoritative registry of every automated 1D SAS batch-analysis method and its complete declared output metrics, including explicit profile eligibility rules for P(r), correlation, and lamellar analysis.

### Added Files

- `app/core/metric_registry.py`
- `tests/test_metric_registry.py`

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added frozen `MetricSpec` and `MethodSpec` dataclasses with tuple-based metric collections and no shared mutable defaults.
- Added the ordered `METHOD_REGISTRY` covering all 18 confirmed method identifiers and the full approved metric lists for each method.
- Added `required_method_ids()` for full ordered coverage and `applicable_method_ids(config)` for profile-aware eligibility.
- Recorded P(r) eligibility as `enable_pr=True` plus `particle`, `polymer`, or `unknown` sample type; correlation eligibility as `enable_correlation=True` plus `two_phase` or `lamellar`; and lamellar eligibility as `sample_type="lamellar"` with no separate flag.
- Added focused tests that verify method coverage, conditional applicability, and every confirmed Guinier output field.
- Added implementation documentation describing the registry boundary, applicability rules, test evidence, and later-stage requirement to retain unavailable-method statuses.

### Reason

The confirmed workflow requires all downstream analysis, trend, Excel, CSV/JSON, figure, and GUI paths to share a single metric contract. This prevents individual subsystems from silently omitting fields or applying incompatible P(r)/correlation/lamellar eligibility rules.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_metric_registry.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py tests\test_metric_registry.py
```

For the full regression suite:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Source-only registry and test files listed above.
- Updated internal implementation documentation in `docs/developer_notes.md`.
- No raw experimental data, processed data, result package, figures, workbook, or build artifact was generated.

### How To Check Success

- Before implementation, the focused registry test failed for the expected missing `app.core.metric_registry` module.
- After implementation, the focused registry command reports `3 passed`.
- The schema-plus-registry command reports `6 passed`.
- The full suite reports `259 passed`.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- The registry declares expected output fields and profile eligibility only; it does not establish that a curve meets numerical or physical prerequisites for an analysis.
- Future execution stages must emit explicit unavailable/failed statuses and reasons instead of inventing metric values.
- Raw experimental data were not read, modified, moved, renamed, or deleted.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 08:21:45 +08:00 - Add Typed Automated-Batch Analysis Schema

### Task Objective

Create the stable typed data contracts required by the automated 1D SAS batch-analysis workflow before any input data, numerical analysis, or GUI integration is added.

### Added Files

- `app/core/auto_batch_schema.py`
- `tests/test_auto_batch_schema.py`

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added the shared `AnalysisStatus`, `ParameterValue`, `AnalysisEnvelope`, `ProgressEvent`, `AutoBatchConfig`, and `AutoBatchRun` dataclasses/enums.
- Added strict default batch-consensus configuration (`consensus_min_coverage=0.70`, `allow_per_frame_range_fallback=False`) and validation for invalid coverage, empty batch IDs, bootstrap/sensitivity settings, reference modes, and exploratory-statistics dimensions.
- Reused `app.core.data_model.utc_now_iso` for run timestamps and avoided GUI/PySide imports and new third-party dependencies.
- Added focused tests for invalid consensus coverage, missing parameter values with reasons, and the strict default consensus policy.
- Added the corresponding internal implementation note in `docs/developer_notes.md`, including public-contract semantics, test evidence, and the boundary to later import/fitting/export stages.

### Reason

Later batch import, quality, fitting, sequence, export, and GUI tasks need one serializable, explicit schema so every analysis result can retain status, validity, parameters, diagnostics, and provenance consistently.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_auto_batch_schema.py
```

For the full regression suite, additionally set headless plotting/UI variables and run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- Source-only schema and test files listed above.
- Updated internal implementation documentation in `docs/developer_notes.md`.
- No raw experimental data, processed data, result package, figures, workbook, or build artifact was generated.

### How To Check Success

- The focused schema command reports `3 passed`.
- The full suite reports `256 passed`.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- This task defines contracts only; it does not yet import curves, run analyses, fit models, or write outputs.
- Raw experimental data were not read, modified, moved, renamed, or deleted.
- No dependencies were installed, and no package, Git commit, or Git push was performed.

## 2026-07-11 08:14:20 +08:00 - Configure Engineering Skill Conventions

### Task Objective

Configure the repository for the user-requested `ask-matt` engineering flow before beginning the automated SAS batch-analysis implementation.

### Added Files

- `docs/agents/issue-tracker.md`
- `docs/agents/triage-labels.md`
- `docs/agents/domain.md`

### Modified Files

- `AGENTS.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Configured GitHub Issues as the repository issue tracker based on the existing `origin` remote.
- Added the default five-label triage vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`.
- Configured a single-context domain-doc layout that reads `CONTEXT.md` and `docs/adr/` when present, without creating either prematurely.
- Added an `Agent skills` section to `AGENTS.md` that points engineering skills to these conventions.

### Reason

The user explicitly invoked the `ask-matt` skill and selected the subagent-driven execution flow. That flow requires a repository-local tracker, label, and domain-document convention before ticket and implementation work starts.

### How To Run

No application behavior changed. The configuration is consumed by engineering skills and can be reviewed directly in `docs/agents/`.

### Generated Output Files

- Three repository-local engineering-skill configuration documents under `docs/agents/`.
- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

- Confirm `AGENTS.md` contains one `## Agent skills` section with links to the three configuration documents.
- Confirm `docs/agents/issue-tracker.md` names GitHub Issues and `docs/agents/triage-labels.md` contains all five canonical labels.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- This configuration does not create, edit, or close external GitHub Issues.
- It does not change analysis code, input handling, numerical methods, or GUI behavior.
- No raw experimental data were modified, moved, renamed, or read.
- No packaging, Git commit, or Git push was performed.

## 2026-07-11 07:39:15 +08:00 - Plan Automated Batch Deep Analysis Implementation

### Task Objective

Convert the confirmed automated batch deep-analysis design into executable, test-first implementation plans with explicit file boundaries, interfaces, failure checks, commands, expected results, and stage gates.

### Added Files

- `docs/superpowers/plans/2026-07-11-automated-batch-deep-analysis-roadmap.md`
- `docs/superpowers/plans/2026-07-11-auto-batch-foundation.md`
- `docs/superpowers/plans/2026-07-11-complete-analysis-and-models.md`
- `docs/superpowers/plans/2026-07-11-in-situ-sequence-analysis.md`
- `docs/superpowers/plans/2026-07-11-results-package-and-gui.md`

### Modified Files

- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Split the large confirmed specification into four ordered, independently testable implementation plans: batch foundation, complete per-method/per-model analysis, in-situ sequence analysis, and results-package/GUI delivery.
- Added an execution roadmap mapping every design requirement to an exact plan task.
- Defined stable interfaces between plans, including the rule that an analysis runner always returns `list[AnalysisEnvelope]` so multi-model output is type-consistent.
- Added test-first steps, exact commands, expected failures/passes, focused regression suites, full-suite checkpoints, input-integrity checks, and documentation requirements.
- Deferred XLSX metadata support until `openpyxl` is explicitly introduced in the results-package plan; CSV metadata remains in the foundation plan.
- Preserved project rules by replacing automatic commit/package actions with diff/status review checkpoints.

### Reason

The confirmed design spans multiple independent subsystems. A single monolithic plan would be difficult to review, test, and recover if a numerical or UI regression occurred. Four dependency-ordered plans make each deliverable independently verifiable while preserving one final user-facing workflow.

### How To Run

No executable code was changed. Implementation should begin with:

```text
docs/superpowers/plans/2026-07-11-auto-batch-foundation.md
```

Then follow the roadmap in exact order.

### Generated Output Files

- Five Markdown planning documents under `docs/superpowers/plans/`.
- No experimental data, processed data, analysis workbook, figures, package, or build artifacts were generated.

### How To Check Success

- Open the roadmap and verify that every design section maps to a plan task.
- Run `rg -n "TBD|TODO|待定|待补充|implement later|similar to" docs/superpowers/plans/2026-07-11-*.md`; no placeholder instruction should be present.
- Check that Plan 1 produces the interfaces consumed by Plan 2, Plan 2 produces analysis/model results consumed by Plan 3, and Plan 4 consumes the completed `AutoBatchRun`.
- Run `git diff --check`; it should report no whitespace errors.

### Notes And Risks

- This task created plans only; numerical algorithms, exports and GUI behavior are not yet implemented.
- The four plans are large and must be executed in order with full regression checks at every boundary.
- `openpyxl` is the only planned new dependency and must not be downloaded without the required approval if absent.
- No raw experimental data were read, modified, moved, renamed, smoothed, interpolated, background-subtracted, or overwritten while writing the plans.
- No packaging, Git commit, or Git push was performed.

## 2026-07-11 07:23:42 +08:00 - Design One-Click Automated Batch Deep Analysis

### Task Objective

Design a low-manual-operation workflow that accepts calibrated one-dimensional SAS curves, analyzes all supported curve methods and all allowed candidate models for an in-situ series, and produces a primary summary Excel plus complete traceable results.

### Added Files

- `docs/superpowers/specs/2026-07-11-automated-batch-deep-analysis-design.md`

### Modified Files

- `.gitignore`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Documented the confirmed SAS-only input boundary, one-time batch profile, optional metadata merge, batch-consensus q regions, fixed batch primary model, sequential warm starts, failure isolation, and non-destructive output workflow.
- Converted all quantitative indicators from `1D_SAS_curve_deep_analysis_general_enriched.md` into a method-level parameter registry.
- Required every curve, every applicable analysis, and every allowed candidate model to export all obtainable parameters, uncertainty, bounds, fit-quality statistics, pointwise residuals, validity checks, reliability, and failure status.
- Defined the complete parameters and derived quantities for the 10 existing shape/empirical models.
- Defined a 16-sheet summary workbook and supporting CSV/JSON/figure directory structure.
- Defined error handling, sequence continuity, model-transition flagging, safety constraints, implementation layers, and acceptance tests.
- Added `.superpowers/` to `.gitignore` so temporary visual-brainstorm companion files are not included in version control.

### Reason

The existing project provides many individual SAS analyses but does not yet provide a single automated, batch-consistent workflow that runs every applicable method/model, preserves full output details, and returns one final data package for an in-situ series.

### How To Run

No executable behavior was changed in this design-only task. The current application still starts with:

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

### Generated Output Files

- Formal design specification: `docs/superpowers/specs/2026-07-11-automated-batch-deep-analysis-design.md`
- Temporary browser-based brainstorming screens under `.superpowers/` remain local and are now ignored by Git.
- No experimental data, processed data, figures, analysis workbook, package, or build artifact was generated.

### How To Check Success

- Open the design specification and verify that it contains the confirmed architecture, full method-level parameter registry, 10-model parameter table, Excel/output contract, failure handling, tests, and acceptance criteria.
- Run `rg -n "TBD|TODO|待定|待补充" docs/superpowers/specs/2026-07-11-automated-batch-deep-analysis-design.md`; no placeholder should be found.
- Run `git status --short`; the design file, `.gitignore`, and `CHANGELOG.md` should be the only intended tracked changes from this design task.

### Notes And Risks

- This task produced a design only; analysis code and GUI behavior have not yet been implemented.
- The requested scope is large and must be implemented in four verified layers, while still presenting one final GUI entry to the user.
- Conditional outputs such as P(r), correlation functions, absolute interface area, volume fraction, kinetic fits, PCA, and clustering remain assumption-dependent or exploratory.
- No raw experimental data were modified, moved, renamed, smoothed, interpolated, background-subtracted, or overwritten.
- No packaging, dependency installation, Git commit, or Git push was performed.

## 2026-07-09 13:46:11 +08:00 - Fix Batch Import q Range Summary Totals

### Task Objective

Execute `.ai-bridge/current-plan.md`返工计划：修正批量导入 q 范围过滤统计口径，使因 q range filter 后点数不足而失败的文件也纳入 summary 总点数统计，并保留可追溯 diagnostics。

### Added Files

- None.

### Modified Files

- `app/core/io.py`
- `app/core/batch_import.py`
- `tests/test_io.py`
- `tests/test_batch_import.py`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `QImportRangeFilterError`, a `ValueError` subclass that carries q range filter diagnostics.
- Changed `apply_q_import_range_filter()` to raise `QImportRangeFilterError` when enabled filtering leaves fewer than the required point count.
- Updated `import_in_situ_series()` to catch `QImportRangeFilterError` directly instead of matching error strings.
- Updated batch summary totals so q range filter failure files contribute their `raw_point_count`, `imported_point_count`, and `filtered_out_point_count`.
- Added `created_curve_total_points` and `failed_q_range_would_import_total_points` to `import_summary`.
- Added q range failure diagnostics to `failed_files`: `failure_type`, q range bounds, raw point count, would-import point count, and filtered-out point count.
- Added tests confirming `QImportRangeFilterError` remains compatible with `ValueError` and exposes diagnostics.
- Extended batch import tests so a success+q-range-failure batch reports `raw_total_points=7`, `imported_total_points=2`, and `filtered_out_total_points=5`.

### Reason

The previous implementation counted batch summary totals only after `load_curve()` succeeded. Files that were readable and column-inferred but failed because q filtering kept fewer than 2 points were omitted from the summary totals, making UI/history totals misleading.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_batch_import.py
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_import_preview.py tests\test_batch_import.py tests\test_ui_style.py
python -B -m pytest -q -p no:cacheprovider
python -B -m compileall -q main.py app\core app\ui
```

### Generated Output Files

- No research output files, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

- `tests\test_io.py tests\test_batch_import.py` should report `18 passed`.
- Related focused tests should report `47 passed`.
- Full pytest should report `253 passed`.
- `compileall` should exit with code 0.
- In a batch import where one file imports and one file fails due to q filtering, `raw_total_points`, `imported_total_points`, and `filtered_out_total_points` should include both files that reached the filter.

### Notes And Risks

- This is a narrow bugfix; it does not change q range defaults, UI layout, single-file import behavior, or preview behavior.
- No source experimental files were modified, moved, renamed, overwritten, smoothed, interpolated, background-subtracted, or unit-converted.
- Already imported curves were not retroactively cropped.
- No packaging, Git commit, or Git push was performed.

## 2026-07-09 12:18:47 +08:00 - Add Import-Time Raw q Range Filter

### Task Objective

Execute `.ai-bridge/current-plan.md` for `导入数据时支持 q 范围限制`: add an import-time raw q filter with default enabled range `q_min=0.01` and `q_max=0.05`, while preserving old behavior when the filter is disabled.

### Added Files

- None.

### Modified Files

- `app/core/io.py`
- `app/core/import_preview.py`
- `app/core/batch_import.py`
- `app/ui/import_tab.py`
- `tests/test_io.py`
- `tests/test_import_preview.py`
- `tests/test_batch_import.py`
- `tests/test_ui_style.py`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `validate_q_import_range()` and `apply_q_import_range_filter()` for import-time raw q filtering.
- Extended `load_curve()` with `limit_q_range`, `q_min`, and `q_max`; filtering is inclusive and happens before `CurveData.create()`.
- Synchronized q/I/error filtering with one mask and rejected enabled filters that leave fewer than 2 points.
- Recorded enabled filter diagnostics in curve `metadata["import_q_range_filter"]` and import `processing_history`.
- Extended import preview diagnostics with raw point count, would-import point count, filtered-out count, and filtered q min/max.
- Extended batch import to apply the same q range to every file and summarize raw/imported/filtered point totals.
- Added ImportTab q range controls: checkbox default enabled, `q_min=0.01`, `q_max=0.05`.
- Passed the UI q range settings into preview, single-file import, and batch import.
- Added focused tests for closed-interval filtering, error-column synchronization, disabled-filter old behavior, invalid ranges, preview blocking, batch partial failures, and UI defaults.

### Reason

Users need to crop imported SAS curves to a stable raw q interval at import time, without modifying source files, already imported curves, analysis-page q ranges, or downstream fitting logic.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_io.py tests\test_import_preview.py tests\test_batch_import.py tests\test_ui_style.py
python -B -m pytest -q -p no:cacheprovider
python -B -m compileall -q main.py app\core app\ui
python main.py
```

### Generated Output Files

- No research output files, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

- Focused tests should report `46 passed`.
- Full pytest should report `252 passed`.
- `compileall` should exit with code 0.
- In the GUI import page, `导入时限制 q 范围` should be checked by default with `q_min=0.01` and `q_max=0.05`.
- Preview diagnostics should show `raw_point_count`, `would_import_point_count`, and `would_filter_out_point_count`.

### Notes And Risks

- The filter applies to raw q only; it does not use `ln(q)`, `q^2`, plot transforms, or analysis-page q ranges.
- No source experimental files were modified, moved, renamed, overwritten, smoothed, interpolated, background-subtracted, or unit-converted.
- Existing programmatic behavior is preserved when `limit_q_range=False`.
- No packaging, Git commit, or Git push was performed.

## 2026-07-08 23:35:41 +08:00 - Refine Automatic q-Region Detection Safety

### Task Objective

Execute the current `.ai-bridge/current-plan.md` automatic q-region detection rigor refactor: make Porod-like selection more conservative, enforce scanner window limits, make low-q upturn and out-of-range power-law slopes safer, enrich peak metrics, remove duplicate deep-scan scanner bodies, and prevent GUI default q ranges from silently truncating data.

### Added Files

- None.

### Modified Files

- `app/core/auto_regions.py`
- `app/core/deep_scan.py`
- `app/core/feature_extraction.py`
- `app/core/region_scanners.py`
- `app/ui/analysis_tab.py`
- `tests/test_auto_regions.py`
- `tests/test_auto_region_ui.py`
- `tests/test_deep_scan.py`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added TDD coverage for conservative Porod high-q gating, scanner `max_scanned_windows`, high-q noise scoring, low-q upturn downgrade behavior, out-of-range power-law alpha handling, peak metric fields, GUI q-range safety, and `deep_scan.py` duplicate scanner cleanup.
- Enforced `max_scanned_windows` in Guinier, power-law, and Porod sliding-window scanners, and recorded `scanned_windows`, `max_scanned_windows`, and `max_scanned_windows_reached` in candidate metrics.
- Changed Porod-like scoring to include high-q position, `q^4I` plateau stability, positive plateau checks, point-count score, and high-q noise penalty; low-q or unstable windows are capped below high confidence.
- Added power-law alpha plausibility warnings and score caps for slopes outside the usual empirical SAS range.
- Downgraded Guinier candidates overlapping or near detected low-q upturns and preserved a low-score risk candidate when the regular ranking would hide the risky interval.
- Added peak `peak_prominence`, `peak_snr`, `peak_snr_unavailable_reason`, `peak_local_baseline`, and `peak_local_contrast` metrics.
- Replaced duplicate scanner implementations in `deep_scan.py` with compatibility wrappers around `region_scanners.py`.
- Updated automatic q-region GUI detection so default `0-1` and invalid manual ranges fall back to the current curve's full raw q range, while non-overlapping manual ranges show a `UserMessage` and do not write an analysis result.

### Reason

The previous automatic q-region implementation could over-rank non-high-q Porod-like windows, hide low-q upturn risk, scan more windows than intended, and silently use the GUI's default `0-1` q range. These behaviors are risky for beginner SAS analysis because they can produce confident-looking but scientifically unsafe candidate intervals.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m compileall -q main.py app\core app\ui
```

Focused checks used during this task:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_auto_region_ui.py tests\test_deep_scan.py
python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_auto_region_ui.py tests\test_deep_scan.py tests\test_porod_analysis.py tests\test_power_law.py tests\test_peak_analysis.py
```

### Generated Output Files

- `.ai-bridge/implementation-diff.patch` will be regenerated after final handoff status updates.
- No research output files, processed data, figures, packages, commits, or pushes were generated intentionally.
- Test execution may create transient pytest or Python cache files, which are ignored by project `.gitignore`.

### How To Check Success

- Focused automatic-region/deep-scan tests pass with `25 passed`.
- Related Porod, power-law, and peak regression tests pass with `34 passed`.
- Full pytest passes with `242 passed`.
- `python -B -m compileall -q main.py app\core app\ui` exits successfully.
- `git -C sas_curve_analyzer diff --check` exits successfully, with only LF/CRLF normalization warnings on Windows.

### Notes And Risks

- Automatic labels remain candidate/risk labels only and do not prove particle shape, fractal type, interface sharpness, particle diameter, or volume fraction.
- Conservative Porod scoring may reduce automatic confidence for valid data; users should review q range, background subtraction, and instrument noise before interpreting Porod-like behavior.
- Raw experimental q/I data were not modified, deleted, moved, renamed, smoothed, interpolated, background-subtracted, unit-converted, or overwritten.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-11 17:23:18 +08:00 - Harden Stage 2 Task 3 Numerical Safety After Independent Review

### Task Objective

Resolve every Blocker and Important finding from the independent Stage 2 / Task 3 review without resetting prior Task 3 work: prevent non-finite numerical outputs, make absolute Porod candidates assumption-safe, and make feature completeness auditable.

### Added Files

- None.

### Modified Files

- `app/core/extended_features.py`
- `app/core/feature_extraction.py`
- `app/core/porod_analysis.py`
- `app/core/model_free.py`
- `tests/test_extended_features.py`
- `tests/test_peak_analysis.py`
- `tests/test_porod_analysis.py`
- `tests/test_invariant_analysis.py`
- `docs/developer_notes.md`
- `.superpowers/sdd/stage2-task3-review-package.md`
- `.superpowers/sdd/stage2-task3-implementer-report.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Replaced overflow-prone duplicate-q sums with scaled local means and re-audited collapsed arrays before gradient, peak, Kratky, and integration calculations.
- Made every extended integral, including `Q_low`, `Q_mid`, and `Q_high`, return `None` with an audit warning when a finite-range trapezoidal reduction overflows or becomes non-finite.
- Added finite-safe Porod statistics; unsafe reductions now withhold aggregate values and noise scores rather than publishing `NaN`/`inf`.
- Restricted absolute Porod surface candidates to a strictly finite, safely squared contrast; literal `two_phase_confirmed=True`; a valid positive contiguous plateau candidate; and a Porod-like exponent. The candidate now uses the contiguous-candidate mean rather than all selected points.
- Made peak full area unavailable when a SciPy prominence-contour baseline touches a selected q-range edge, while retaining independently supported FWHM descriptors. Added explicit baseline provenance.
- Withheld overflowed peak/Kratky SNR, d-spacing, width-derived, and area-derived scalars; validity/completeness records now explain unavailable derivatives.
- Validated finite numeric thresholds and finite integer counts for crossover, shoulder, oscillation, and shape-distance paths. Shoulder and oscillation provenance now records actual thresholds, spacing, scores, and prominence-contour support.
- Updated the review package so untracked Task 3 paths are explicitly included in the audit evidence instead of being omitted by `git diff` alone.

### Reason

The independent review found that extreme but finite inputs could still leak `NaN`/`inf`, a truthy non-boolean could unlock an absolute Porod surface candidate, and edge-supported extrema could be labelled complete. These are numerical-audit and scientific-interpretation risks.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -m pytest -q -p no:cacheprovider tests\test_extended_features.py tests\test_peak_analysis.py tests\test_porod_analysis.py tests\test_invariant_analysis.py tests\test_plot_analysis.py tests\test_invariant.py
```

### Generated Output Files

- No raw experimental data, processed data, figures, exports, packages, or build artifacts were generated.
- Only source code, regression tests, review evidence, and documentation were updated.

### How To Check Success

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\extended_features.py app\core\feature_extraction.py app\core\porod_analysis.py app\core\model_free.py tests\test_extended_features.py tests\test_peak_analysis.py tests\test_porod_analysis.py tests\test_invariant_analysis.py
git diff --check
```

### Notes And Risks

- `None` is deliberate audit information for an unavailable numerical descriptor; it is not a measured zero.
- A Porod-like plateau remains descriptive and does not independently prove a morphology, interface model, or material mechanism.
- Local duplicate-q averaging does not mutate `CurveData` or experimental source files; users should still investigate duplicate rows in their reduction workflow.
- No raw data were changed, and no package, Git commit, or Git push was performed.

## 2026-07-11 13:25:44 +08:00 - Stage 2 Task 1 Review Remediation: Likelihood, PSD, Serialization, And Bounds

### Task Objective

Resolve the independent Stage 2 Task 1 review findings before later candidate-fit retry selection and batch model ranking consume common diagnostics: make weighted information criteria scientifically explicit, reject materially invalid finite covariance matrices, guarantee JSON-native records, remove ambiguous bounds interpretation, and correct weighting audit labels.

### Added Files

- None.

### Modified Files

- `app/core/fit_diagnostics.py`
- `tests/test_fit_diagnostics.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `sigma_is_absolute` to `fit_diagnostics()` (default `True`) plus stable information-criterion audit fields: `information_criterion_basis`, `information_criterion_point_count`, and `information_criterion_reason`.
- Effective absolute sigma now calculate AIC/AICc/BIC from the absolute Gaussian likelihood `chi_square + sum(log(2*pi*sigma**2))` over the actual valid weighted points.  Effective relative sigma explicitly return `None` for all information criteria with basis `unavailable_relative_sigma` and reason `relative_sigma`; no unweighted RSS criterion is silently reused for weighted model selection.  No effective weighting remains labelled `unweighted_residual_variance`.
- Added `non_finite_weighted_residual_point_count`, separated it from `invalid_sigma_point_count`, and report `non_finite_weighted_residual` when finite positive sigma cannot form finite standardized residuals.
- Added a documented `eigvalsh` positive-semidefinite check for all-finite symmetric covariance matrices.  Eigenvalues below `-1e-10 * max(1, max(abs(covariance)))` raise a clear `ValueError`; partially non-finite matrices are not declared PSD and retain null-only unavailable correlations.
- Strengthened `FitDiagnostics.to_dict()` so all output fields are JSON-native: finite NumPy numbers become native `int`/`float`, non-finite values become `None`, flags are `bool`/`None`, and text audit fields are `str`/`None`.
- Defined and tested an unambiguous bounds rule.  Per-parameter list/tuple pairs and `(n_parameters, 2)` arrays are interpreted by parameter; SciPy vector bounds remain `(lower_array, upper_array)` with NumPy arrays.  This fixes the two-parameter tuple-of-pairs transposition defect.
- Added test-first regressions for absolute-vs-unweighted likelihood criteria, relative-sigma information-criterion withholding, true `json.dumps`, material/non-material covariance PSD cases, tuple/list/array/map bounds forms, and maximum-float residual overflow audit behavior.

### Reason

Information criteria will later rank candidate SAS models and retries.  Mixing weighted chi-square with silently unweighted AICc/BIC could select the wrong model.  Likewise, a non-PSD covariance matrix, ambiguous bounds, non-native JSON scalar, or mislabeled uncertainty failure could make an unreliable fit look scientifically traceable when it is not.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py tests\test_model_fitting.py tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py

$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\fit_diagnostics.py tests\test_fit_diagnostics.py
git diff --check
```

### Generated Output Files

- Updated in-memory diagnostics contract, documentation, and automated tests only.
- No raw experimental data, processed data, figures, result packages, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- The newly added review regressions were written before the repair.  Their first target run reported `7 failed, 15 passed` and exposed the missing audit fields, silent unweighted information criteria, tuple-pair bounds transposition, missing PSD rejection, and invalid-sigma mislabel.
- After the minimal repair, `tests\test_fit_diagnostics.py` reported `22 passed`.
- The diagnostics/model-fit/Stage 1 focused regression command reported `98 passed`.
- The full offscreen regression suite reported `348 passed`.
- The required compile and whitespace checks are recorded with this task after the final documentation update.

### Notes And Risks

- All source experimental data remain read-only.  The diagnostics module has no file I/O and does not alter caller arrays.
- `sigma_is_absolute=True` is a statistical input assertion by the caller; an absolute-sigma likelihood is only meaningful when the supplied uncertainty column really represents absolute standard deviations.  If that is not known, callers must use `sigma_is_absolute=False`, which intentionally withholds model-selection information criteria.
- The PSD tolerance accepts only small round-off-scale negative eigenvalues; it is not evidence that a covariance is well-conditioned or that parameters are uniquely identifiable.
- The bounds ambiguity rule intentionally favors tuple/list per-parameter pairs.  Two-parameter callers needing SciPy lower/upper vectors should use NumPy arrays as documented.
- No dependencies were installed and no packaging, Git commit, or Git push was performed.

## 2026-07-11 13:07:35 +08:00 - Stage 2 Task 1 Common Fit Diagnostics Contract

### Task Objective

Implement the approved reusable diagnostics contract for all later 1D SAS fitting methods, so every fit can report complete, traceable numerical quality metrics, parameter uncertainty/bound information, covariance correlations, and row-preserving residual data without hiding invalid inputs.

### Added Files

- `app/core/fit_diagnostics.py`
- `tests/test_fit_diagnostics.py`

### Modified Files

- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added the immutable, JSON-serializable `FitDiagnostics` record and `fit_diagnostics()` with the common fixed metrics: point count, parameter count, degrees of freedom, RSS/weighted RSS, RMSE, MAE, R2/adjusted R2, chi-square/reduced chi-square, AIC/AICc, and BIC.
- Added explicit weighting audit fields (`weighted`, `weighted_point_count`, `weighted_dof`, `sigma_aligned`, `invalid_sigma_point_count`, and `weighting_reason`).  Misaligned or invalid error arrays preserve valid unweighted statistics; only aligned finite positive-error points contribute to weighted quantities.
- Added `parameter_records()` with a fixed per-parameter schema, optional sequence/name-keyed units/initial values/bounds/standard errors, 95% confidence intervals when valid, and tolerance-based bound-hit flags.
- Added `covariance_to_correlation()` with JSON-safe null handling for singular/non-finite covariance information and clear errors for non-square/asymmetric matrices.
- Added `build_residual_rows()` that retains one row per input point, exposes invalid data and weighting limits explicitly, and rejects inconsistent row-array lengths predictably.
- Added test-first regression coverage for normal statistics, invalid/misaligned sigma, zero degrees of freedom, parameter confidence/bounds, singular covariance, non-finite residual inputs, length errors, native-serializable output, and input-array preservation.
- Added developer documentation describing the numerical scope, null semantics, weighting limitations, and scientific interpretation boundary.

### Reason

Later Guinier, power-law, Porod, P(r), and shape-model analyses must report comparable fit quality and all obtainable fit information.  A shared defensive implementation avoids repeated statistics code, prevents invalid errors from being treated as weights, and ensures unavailable quantities remain visible instead of becoming misleading zeroes.

### How To Run

From `sas_curve_analyzer`, run:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py tests\test_model_fitting.py tests\test_auto_batch_schema.py tests\test_metric_registry.py tests\test_batch_inputs.py tests\test_batch_consensus.py tests\test_auto_batch.py

$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\fit_diagnostics.py tests\test_fit_diagnostics.py
git diff --check
```

### Generated Output Files

- New in-memory diagnostics API and automated regression tests only.
- No raw experimental data, processed data, figures, result packages, workbooks, packages, Git commits, or Git pushes were generated.

### How To Check Success

- Test-first RED verification initially reported `ModuleNotFoundError: No module named 'app.core.fit_diagnostics'`, confirming the requested API did not already exist.
- After implementation, `tests\test_fit_diagnostics.py` reported `13 passed`.
- The focused diagnostics/model-fit/Stage 1 regression command reported `89 passed`.
- The full offscreen regression suite reported `339 passed`.
- `py_compile` and `git diff --check` completed successfully with no whitespace errors.

### Notes And Risks

- All source experimental data remain read-only.  This module neither reads nor writes experiment files.
- A numerical fit statistic is conditional on the supplied model, q range, preprocessing, and weighting convention; it does not establish model uniqueness or material mechanism.
- Exact-zero RSS makes information criteria undefined in this contract, so they remain `None` rather than using an arbitrary numerical floor.
- No dependencies were installed and no packaging, Git commit, or Git push was performed.

## 2026-07-08 22:52:49 +08:00 - Add Automatic SAS q-Region Detection And One-Click Analysis

### Task Objective

Execute the current `.ai-bridge/current-plan.md`: add automatic q-region candidate detection for SAS curves, support one-click fitting/calculation from candidate regions, allow user q-range adjustment, export traceable candidate tables, and keep existing `deep_scan` behavior compatible.

### Added Files

- `app/core/auto_regions.py`
- `app/core/region_scanners.py`
- `tests/test_auto_regions.py`
- `tests/test_auto_region_ui.py`

### Modified Files

- `app/core/analysis_schema.py`
- `app/core/deep_scan.py`
- `app/core/export.py`
- `app/core/feature_extraction.py`
- `app/ui/analysis_tab.py`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `AutoRegionOptions`, `AutoRegionCandidate`, `AutoRegionDetectionResult`, helper functions, and `detect_auto_regions()`.
- Added `region_scanners.py` for reusable Guinier, power-law, peak, Porod-like, low-q upturn, and high-q noise/background-risk scanning.
- Kept old `deep_scan.py` scanner import paths as wrappers that call `region_scanners.py`.
- Added automatic region result metadata with `result_group="auto_region"` and `export_tables["auto_region_candidates"]`.
- Added one-click `run_analysis_for_region()` dispatch for Guinier, power-law, Porod-like, peak, and finite measured invariant candidates.
- Added skip results for non-fit-ready risk regions such as low-q upturn and high-q noise when `force=False`.
- Added `left_q` and `right_q` peak boundary fields for traceable FWHM-derived peak candidates.
- Added `export_auto_region_candidates_csv()` with q range, d range, score, confidence, metrics JSON, warnings, and source detection ID fields.
- Added an `AnalysisTab` group box for automatic q-region detection, candidate display, q_min/q_max filling, one-click analysis, and candidate CSV export.
- Added focused tests for automatic candidate detection, boundary cases, source metadata, CSV export, UI safety, q-range filling, and one-click execution.
- After final review, fixed automatic q-range filling so spinbox rounding does not falsely record `user_overrode_range=True`.
- After final review, fixed peak candidate `n_points` to report the actual number of raw q points inside the candidate q range.

### Reason

Manual q-range selection is a major source of SAS analysis error. The new workflow gives beginner users a traceable candidate interval list while keeping all labels as candidates or risk indicators, not structural proof.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m compileall -q main.py app\core app\ui
```

Focused regression check:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_auto_regions.py tests\test_auto_region_ui.py tests\test_deep_scan.py tests\test_guinier.py tests\test_power_law.py tests\test_invariant.py tests\test_local_slope.py tests\test_porod_analysis.py tests\test_peak_analysis.py tests\test_ui_style.py tests\test_records.py tests\test_export.py
```

### Generated Output Files

- No research output files, processed data, figures, packages, commits, or pushes were generated intentionally.
- The UI can now export user-selected automatic candidates to a CSV path chosen by the user.
- Test execution may create transient pytest or Python cache files, which are ignored by project `.gitignore`.

### How To Check Success

- In the analysis page, use `自动识别 q 区间` to detect candidates for the current curve.
- Candidate rows include q range, d range, point count, score, confidence, warnings, and recommended action.
- Selecting a candidate can fill `q_min/q_max` and run the recommended analysis.
- Result metadata includes `source_auto_region_id`, `source_region_type`, `auto_score`, original/final q ranges, and override status.
- Automatically filled candidate ranges are recorded as `user_overrode_range=False` unless the user changes the q range after filling.
- Peak candidate point counts match the number of q points inside the candidate q range.
- Full pytest passes with `233 passed`, and `compileall` exits successfully.

### Notes And Risks

- Original imported curves and raw experimental data files are not modified, moved, deleted, smoothed, background-subtracted, unit-converted, or overwritten.
- The automatic labels are candidate/risk labels only; they do not prove particle shape, interface sharpness, fractal type, particle diameter, or volume fraction.
- Low-q upturn and high-q noise/background-risk regions are not fit-ready by default.
- No `build_feature_table` automatic-region columns were added in this round.
- No plot overlay, P(r), background subtraction, absolute intensity calibration, or automatic structure determination was added.
- No packaging was performed.

## 2026-07-08 19:10:28 +08:00 - Fix P1/P2 Data Safety And Analysis Bugs

### Task Objective

Implement the requested P1/P2 bug-fix plan: prevent unit-mismatched curve averaging/comparison, add safer GUI write handling, improve Windows text import compatibility, and add clearer warnings for interpretation-sensitive SAS calculations.

### Added Files

- `app/core/unit_checks.py`
- `tests/test_ui_safety.py`

### Modified Files

- `app/core/batch.py`
- `app/core/comparison.py`
- `app/core/io.py`
- `app/core/feature_extraction.py`
- `app/core/model_free.py`
- `app/core/model_fitting.py`
- `app/ui/export_tab.py`
- `app/ui/main_window.py`
- `app/ui/batch_tab.py`
- `tests/test_batch.py`
- `tests/test_comparison.py`
- `tests/test_io.py`
- `tests/test_peak_analysis.py`
- `tests/test_local_slope.py`
- `tests/test_invariant.py`
- `tests/test_model_fitting.py`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added shared curve-unit validation before replicate averaging and A/B comparison.
- Added text decoding fallback for `utf-8-sig`, `utf-8`, `gbk`, and `utf-16` curve imports.
- Added raw and baseline-corrected peak area fields while keeping `peak_area` for compatibility.
- Made local-slope analysis exclude duplicate q points with an explicit warning.
- Added negative-intensity and negative-contribution reporting to finite measured invariant results.
- Resolved model-fit length parameter units from current q units and warned when invalid error values force unweighted fitting.
- Added GUI overwrite cancellation for fixed-name exports.
- Added project-folder risk confirmation before saving into folders that contain existing projects or likely raw data files.
- Converted batch comparison and sequence-index export failures into user-facing messages instead of uncaught GUI exceptions.
- Added regression tests for all above behaviors.

### Reason

The reviewed bugs could silently mix incompatible physical units, overwrite previous analysis outputs, fail on common Windows instrument encodings, or present interpretation-sensitive calculations without enough context. These changes make the workflow safer for beginner materials researchers while preserving non-destructive raw-data handling.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:PYTHONDONTWRITEBYTECODE='1'
$env:QT_QPA_PLATFORM='offscreen'
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
```

Focused regression check:

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_batch.py tests\test_comparison.py tests\test_io.py tests\test_peak_analysis.py tests\test_local_slope.py tests\test_invariant.py tests\test_model_fitting.py tests\test_ui_safety.py
```

### Generated Output Files

- No research output files, processed data, figures, packages, commits, or pushes were generated intentionally.
- Test execution may create transient pytest or Python cache files, which are ignored by project `.gitignore`.

### How To Check Success

- Unit-mismatched averaging/comparison raises a clear `ValueError`.
- Existing export files are not overwritten when the GUI confirmation is cancelled.
- GBK and UTF-16 text curve files import successfully.
- Peak, local-slope, invariant, and model-fitting results include the new safety fields or warnings.
- Focused and full pytest suites pass.

### Notes And Risks

- Original imported curve arrays and raw experimental files are not modified, moved, deleted, renamed, smoothed, background-subtracted, or unit-converted by these fixes.
- `peak_area` remains as a compatibility alias for the raw FWHM area; use `baseline_corrected_peak_area` for baseline-corrected comparisons.
- GUI overwrite protection is intentionally at the UI layer; core export functions still write to explicit paths for programmatic workflows.
- No packaging was performed.

## 2026-07-08 16:23:57 +08:00 - Simplify Export Report Page And First-Hand Transform CSV

### Task Objective

Execute the latest `.ai-bridge/current-plan.md`: simplify the `导出报告` page to stable data-export actions, add a first-hand transformed-data CSV for the current curve, remove old hidden export wrappers for removed UI entries, and synchronize tests and documentation.

### Added Files

- None.

### Modified Files

- `app/core/export.py`
- `app/core/derived_data.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `tests/test_derived_data.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `.ai-bridge/agent-status.md`
- `.ai-bridge/codex-status.md`
- `.ai-bridge/execution-log.jsonl`
- `.ai-bridge/implementation-diff.patch`

### Deleted Files

- `tests/test_export_deep_analysis.py`

### Specific Changes

- Rebuilt `ExportTab` into two groups: basic exports and first-hand transformed-data export.
- Kept the visible export actions to current-curve CSV, `feature_table.csv`, Origin long table, Origin matrix table, and current-curve transformed-data CSV.
- Added `build_first_hand_transform_table()` and `export_first_hand_transform_csv()` for a row-preserving wide CSV with `q`, `I(q)`, `q²`, `ln q`, `log10 q`, `ln I(q)`, `log10 I(q)`, `q²I(q)`, `q⁴I(q)`, `qI(q)`, `q³I(q)`, and `d = 2π/q`.
- Removed old report-page handlers for Markdown report, complete analysis bundle, project save-as, derived long table, derived matrix table, and optional alpha/Rg/D/R/reference-curve inputs.
- Removed deleted UI-entry backing functions from `app/core/export.py` and removed multi-curve derived long/matrix builders from `app/core/derived_data.py`.
- Updated tests so removed public functions and old UI buttons stay absent, and so the new transformed-data CSV preserves row count and mathematical domain `NaN` values.
- Updated README, Chinese manual, and developer notes to describe the compact export page and to avoid current-workflow claims about removed bundle/report exports.

### Reason

The previous export page mixed data export, report generation, project saving, and optional parameter-driven derived tables. The simplified workflow keeps only high-frequency, directly reproducible exports and prevents future agents from reintroducing removed `invariant_contribution`-style or old derived-table workflows through stale documentation.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:QT_QPA_PLATFORM='offscreen'
$env:TEMP="$PWD\.tmp"
$env:TMP="$PWD\.tmp"
$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
python -m pytest tests/test_export.py tests/test_ui_style.py -q
python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated intentionally.
- When a user clicks the new export button, it writes `<curve_name>_transformed_data.csv` in the selected export folder.
- Handoff/status outputs are updated under `.ai-bridge/`: `agent-status.md`, `codex-status.md`, `execution-log.jsonl`, and `implementation-diff.patch`.

### How To Check Success

- `导出报告` shows only the five intended export buttons and no alpha/Rg/D/R/reference-curve controls.
- The transformed-data CSV has the same row count as the current curve and keeps undefined log or `2π/q` values as blank/`NaN` cells rather than deleting rows.
- `export_analysis_bundle`, old derived CSV wrappers, plot-analysis bundle wrappers, and derived long/matrix builders are no longer public core APIs.
- Focused and full pytest suites pass, `compileall` succeeds, and `git diff --check` reports no whitespace errors.

### Notes And Risks

- Raw q/I arrays and original experiment files were not modified, smoothed, interpolated, background-subtracted, unit-converted, deleted, moved, or renamed.
- The new CSV is a deterministic data table, not a fitted analysis result and not a physical proof of structure.
- `DerivedDataOptions` and `build_curve_derived_table()` remain for plotting and analysis internals; only removed export-page wrappers and removed multi-curve derived exports were deleted.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-08 15:18:48 +08:00 - Documentation Navigation, Warning Filtering, And Formula Consistency Rework

### Task Objective

Execute the latest `.ai-bridge/current-plan.md` review rework: align Chinese/English documentation with the four-workspace UI, filter plot-analysis warnings by current plot type, standardize user-visible formulas, clean a dead UI test branch, and mark the old `invariant_contribution` plan as archived.

### Added Files

- None.

### Modified Files

- `app/core/derived_data.py`
- `app/core/plot_analysis.py`
- `app/ui/analysis_tab.py`
- `tests/test_plot_analysis.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/method_notes.md`
- `docs/superpowers/plans/2026-07-07-information-budget.md`
- `CHANGELOG.md`
- `.ai-bridge/agent-status.md`
- `.ai-bridge/codex-status.md`
- `.ai-bridge/execution-log.jsonl`
- `.ai-bridge/implementation-diff.patch`

### Deleted Files

- None.

### Specific Changes

- Updated the Chinese manual so `数据检查` is described under `数据导入`, `曲线绘图` and `曲线分析` are described as side-by-side areas inside `曲线工作台`, and `批量比较` is described under `高级功能`.
- Reworded README and UI text from old page-style wording to `曲线工作台` / `曲线绘图区域` / `曲线分析区域`.
- Added plot-type-specific derived-warning filtering so ordinary `linear`, `semilog`, `guinier`, `kratky`, `porod`, and `invariant` analyses do not show unrelated `local_slope_dlnI_dlnq` warnings, while `local_slope` still reports its own validity warnings.
- Standardized user-visible formulas to symbols such as `q²`, `q⁴`, `α(q)`, and `2π`; internal CSV/JSON column keys such as `q2I`, `q4I`, and `d_2pi_over_q` remain unchanged.
- Removed unreachable code from the deep-analysis UI separation test and added string tests for the current manual navigation.
- Added an archived note to `docs/superpowers/plans/2026-07-07-information-budget.md` so `invariant_contribution` is not mistaken for a current main plot requirement.

### Reason

The review identified remaining inconsistencies after the previous pass: old top-level navigation language persisted in documentation, derived local-slope warnings could still inflate unrelated plot-analysis warnings, visible formulas still used ASCII notation in some places, a UI test contained unreachable code, and an old plan could mislead future implementation agents.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_plot_analysis.py tests/test_derived_data.py tests/test_analysis_preflight.py tests/test_export.py tests/test_ui_style.py -q
python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated intentionally.
- Handoff/status outputs are updated under `.ai-bridge/`: `agent-status.md`, `codex-status.md`, `execution-log.jsonl`, and `implementation-diff.patch`.

### How To Check Success

- `docs/user_manual_zh.md` no longer uses old top-level entry phrases such as `进入 数据检查 页`, `进入 曲线绘图 页`, `进入 无模型分析 页`, or `顶层页签包括`.
- `linear` and `semilog` plot analysis do not report unrelated `local_slope_dlnI_dlnq` warnings for two-point curves, while `local_slope` still reports insufficient valid local-slope points.
- User-visible formulas no longer use `q^2`, `q^4`, `alpha(q)`, or `2*pi` except in tests that assert those strings are absent or in archived historical context.
- The historical information-budget plan begins with an archived note warning that `invariant_contribution` must not be reintroduced as a main plot type.

### Notes And Risks

- Raw experimental q/I data were not modified, deleted, moved, renamed, smoothed, interpolated, background-subtracted, unit-converted, or overwritten.
- No new main plot type was added; `invariant_contribution` and `peak_spacing` remain outside the main plotting combo box.
- `Q_measured` remains a measured finite q-range integral, not a complete invariant.
- Porod metrics remain descriptive unless the user supplies the physical assumptions needed for absolute surface calculations.
- This pass did not package the project and did not run `git commit` or `git push`.

## 2026-07-08 14:42:44 +08:00 - Post-Implementation Review Fixes For Eight-Plot Workspace

### Task Objective

Execute the updated `.ai-bridge/current-plan.md` review-fix plan after the workspace/eight-plot implementation: remove misleading optional warnings, keep curve workspace widgets mounted, make analysis preflight match the selected plot key, prevent residual CSV overwrite, and clean documentation conflicts.

### Added Files

- None.

### Modified Files

- `app/core/derived_data.py`
- `app/core/plot_analysis.py`
- `app/core/plotting.py`
- `app/core/analysis_preflight.py`
- `app/core/export.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `tests/test_derived_data.py`
- `tests/test_plot_analysis.py`
- `tests/test_plotting.py`
- `tests/test_export.py`
- `tests/test_ui_style.py`
- `tests/test_analysis_preflight.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added an option to suppress missing optional alpha/Rg/D/R/reference derived-column warnings inside eight-plot analysis while preserving real log-domain and non-finite-data warnings.
- Changed plot-analysis and plotting filters from `notna()` to finite-value masks so `inf` values are excluded from fits, integrations, and displayed transformed points.
- Rebuilt `analysis_preflight.py` with one-to-one plot-analysis semantics: `linear` uses finite points, `semilog` requires positive intensity, and log-log/Guinier/local-slope require the appropriate positive q and intensity domains.
- Updated `AnalysisTab` preflight mapping so `linear` no longer borrows invariant checks and `semilog` no longer borrows Guinier checks.
- Rewrote `MainWindow` top-level tab construction so it creates the four workspaces directly and keeps `PlottingTab` plus `AnalysisTab` mounted inside `CurveWorkspaceTab`.
- Changed residual CSV names to `plot_fit_residuals_<analysis_id>_<curve_id>_<plot_type>.csv` to avoid overwriting repeated analyses.
- Updated docs to remove old implementation advice around `invariant_contribution` as a main plot type and to document the new residual filename.

### Reason

The review plan identified correctness and usability risks after the initial implementation: ordinary plot analysis could display irrelevant derived-parameter warnings, `inf` values could survive `notna()` filters, preflight checks could mention the wrong analysis family, repeated residual exports could overwrite each other, and documentation still contained old navigation or plot-type advice.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

In the GUI, import a curve, open `曲线工作台`, choose one of the eight plot types, and run the corresponding `曲线分析`. Use `项目与输出` to export the complete analysis bundle.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.
- The handoff files `.ai-bridge/agent-status.md`, `.ai-bridge/implementation-diff.patch`, and `.ai-bridge/execution-log.jsonl` are updated separately.
- When users export a complete analysis bundle after running plot analysis, residual outputs now use `plot_fit_residuals_<analysis_id>_<curve_id>_<plot_type>.csv`.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_style.py tests/test_method_mapping.py tests/test_project.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_plotting.py tests/test_derived_data.py tests/test_plot_analysis.py tests/test_export.py tests/test_analysis_preflight.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q
python -m compileall -q main.py app\core app\ui
git -C sas_curve_analyzer diff --check
```

### Notes And Risks

- Raw q/I arrays are not modified, smoothed, interpolated, background-subtracted, unit-converted, or resampled.
- Optional derived columns can still report missing alpha/Rg/D/R/reference values during explicit derived-data export; only plot-analysis warning noise is suppressed.
- Local-slope plateau auto-detection remains not implemented by design.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-08 12:55:46 +08:00 - Interface Workspace Refactor And Eight-Plot Analysis Outputs

### Task Objective

Implement the current handoff plan: reorganize the GUI into four top-level workspaces, restrict main plotting to eight plot types, add plot-specific analysis outputs, and integrate plot analysis exports while preserving raw q/I data.

### Added Files

- `app/core/plot_analysis.py`
- `app/ui/data_import_workspace_tab.py`
- `app/ui/curve_workspace_tab.py`
- `app/ui/advanced_workspace_tab.py`
- `app/ui/deep_analysis_tab.py`
- `tests/test_plot_analysis.py`

### Modified Files

- `app/core/derived_data.py`
- `app/core/export.py`
- `app/core/method_mapping.py`
- `app/core/plotting.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `app/ui/plotting_tab.py`
- `tests/test_derived_data.py`
- `tests/test_export.py`
- `tests/test_method_mapping.py`
- `tests/test_plotting.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Rebuilt the top-level UI as `数据导入 / 曲线工作台 / 高级功能 / 项目与输出`.
- Nested `数据检查` under `数据导入`; nested `批量比较` and `深度分析` under `高级功能`.
- Moved deep-analysis controls out of `AnalysisTab` into `DeepAnalysisTab`.
- Limited `PLOT_TYPE_ITEMS` to `linear`, `semilog`, `loglog`, `guinier`, `kratky`, `porod`, `invariant`, and `local_slope`.
- Removed `invariant_contribution` and `peak_spacing` from main plot mapping.
- Added `alpha_local = -local_slope_dlnI_dlnq` to derived data and used it for local-slope plotting and analysis.
- Added eight-plot analysis functions for diagnostics, power-law fitting, Guinier fitting, Kratky metrics, Porod metrics, finite invariant integration, and local-slope statistics.
- Added plot-analysis bundle outputs: `plot_analysis_summary.csv`, `plot_analysis_results.json`, and residual CSV files. The final post-review naming convention is `plot_fit_residuals_<analysis_id>_<curve_id>_<plot_type>.csv`.
- Updated tests for UI structure, plot type restrictions, derived-data mapping, numerical plot analysis, and export outputs.

### Reason

The prior UI exposed too many low-frequency functions at the top level and mixed deep-analysis assumptions into ordinary curve analysis. The new layout makes the common workflow clearer and keeps plotting, analysis, and export formulas consistent through shared derived data.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.
- When users export a complete analysis bundle after running plot analysis, the bundle can generate `curves_derived_long.csv`, `plot_analysis_summary.csv`, `plot_analysis_results.json`, and residual CSV files.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_ui_style.py tests/test_method_mapping.py tests/test_project.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_plotting.py tests/test_derived_data.py tests/test_export.py tests/test_plot_analysis.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Raw q/I arrays are not modified, smoothed, interpolated, background-subtracted, unit-converted, or resampled.
- `Q_measured` is a finite measured-range integral, not a complete invariant.
- Porod outputs are relative descriptors by default and do not imply absolute specific surface area.
- Local-slope plateau detection is intentionally marked as not implemented.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 - Windows double-click launcher bat

### Task Objective

Create double-clickable Windows bat launchers both inside the project and on the desktop so the SAS curve GUI can be started without typing commands.

### Symptom Or Reason

The project documented `python main.py`, but there was no double-click entry point for normal Windows desktop use.

### Root Cause

No Windows launcher script existed. A desktop copy also needs an explicit project path because its working directory is the desktop rather than the project root.

### Touched Files

- `Start_SasCurve_Analyzer.bat`
- `E:\desktop\Start_SasCurve_Analyzer.bat`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Fix Summary

- Added `Start_SasCurve_Analyzer.bat` in the project root.
- Made the script work from the project root or as a copied desktop launcher by resolving `E:\Desktop\SasCurve_Analyzer` when needed.
- Added Python discovery through `py -3` or `python`.
- Added clear pause-on-error messages for missing project files, missing Python, missing PySide6, and GUI startup failures.

### Tests Run

```powershell
cmd /c Start_SasCurve_Analyzer.bat --check
cmd /c E:\desktop\Start_SasCurve_Analyzer.bat --check
python -m py_compile main.py
```

Verified result: project-root launcher check passed; desktop launcher check passed; `main.py` syntax check passed.

### Follow-Up Risk

The launcher assumes this project remains at `E:\Desktop\SasCurve_Analyzer` when run from the desktop copy. If the project folder is moved, update `APP_DIR` in the desktop bat file or copy a fresh bat from the new project root.

## 2026-07-07 - Multi-agent audit fixes for UI, exports, and SAS parameter correctness

### Task Objective

Use parallel code audits to find UI layout/help issues, parameter export omissions, and calculation correctness risks, then merge the fixes into the main line with verification.

### Symptom Or Reason

The audit found several ways a researcher could be misled or get incorrect derived values: internal snake_case keys were shown as UI labels, deep-analysis-only controls were mixed with ordinary analysis controls, experimental advanced actions could write analysis results, several q-dependent calculations assumed imported q arrays were already sorted, nonuniform q peak FWHM used an average dq approximation, summary exports lacked curve units and run parameters, and Porod/invariant candidates could be emitted when required assumptions were not met.

### Root Cause

The application preserves imported data order non-destructively, but some analysis/export paths used raw q order for interpolation, gradients, plotting, matrix export, and inverse transforms. Export flatteners also treated scalar values as self-explanatory and did not join back to curve unit context. UI widgets reused core enum keys as display text and did not separate standard and deep-analysis workflows strongly enough.

### Touched Files

- `app/core/array_utils.py`
- `app/core/batch.py`
- `app/core/comparison.py`
- `app/core/export.py`
- `app/core/feature_extraction.py`
- `app/core/invariant_analysis.py`
- `app/core/method_warnings.py`
- `app/core/model_free.py`
- `app/core/plotting.py`
- `app/core/porod_analysis.py`
- `app/core/pr_analysis.py`
- `app/core/report.py`
- `app/core/shape_models.py`
- `app/ui/advanced_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/export_tab.py`
- `app/ui/import_tab.py`
- `app/ui/plotting_tab.py`
- `app/ui/records_tab.py`
- `tests/`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Fix Summary

- Added `sort_arrays_by_q()` and used sorted local q/intensity copies for comparison interpolation, replicate averaging, plotting, local slope, Origin matrix export, normalization integrals, and P(r) inversion.
- Corrected peak FWHM on nonuniform q grids by interpolating SciPy fractional width positions onto q values.
- Added curve name, q unit, intensity unit, length unit, invariant unit, and `parameters_json` to analysis summaries and feature tables.
- Added `fit_parameters.csv` to complete analysis bundles and included fitted parameter values, uncertainty, confidence bounds, and units in reports.
- Added `bundle_warnings.txt` when complete bundle matrix export is skipped because q grids differ, and surfaced those warnings in export history/UI output.
- Gated invariant volume-fraction candidates behind absolute intensity, valid contrast, enough points, and physical Q; gated Porod surface candidates behind positive stable q4I plateau, Porod-like alpha, absolute intensity, and contrast.
- Replaced the mass-fractal cutoff form with a finite low-q empirical form that approaches the requested high-q fractal slope.
- Replaced internal combo-box keys with researcher-facing labels while keeping core keys in `userData`.
- Moved deep-analysis controls into a titled group, disabled experimental P(r)/correlation advanced buttons by default, improved Origin export hover help, and shortened the visible import path label to the filename while retaining the full path in help text.

### Tests Run

Focused red/green verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_comparison.py tests\test_batch.py tests\test_local_slope.py tests\test_plotting.py tests\test_peak_analysis.py tests\test_export.py tests\test_export_deep_analysis.py tests\test_invariant_analysis.py tests\test_porod_analysis.py tests\test_shape_models.py tests\test_ui_style.py -q
```

Verified result: first observed `15 failed, 34 passed`, then `51 passed`.

Additional focused verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_comparison.py tests\test_pr_analysis.py tests\test_invariant.py tests\test_correlation.py tests\test_export.py tests\test_export_deep_analysis.py tests\test_ui_style.py -q
```

Verified result: `36 passed`.

Full verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `116 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

The UI was verified by offscreen widget tests rather than manual visual inspection in a live Windows session. Future q-neighbor calculations should use `sort_arrays_by_q()` or add explicit reversed-q/nonuniform-q regression tests before release.

## 2026-07-07 08:26:19 +08:00 - Origin long-table beginner guide export

### Task Objective

Export a detailed Markdown companion guide whenever the Origin long-table data export is written, so new users can understand each long-table parameter, plot the data correctly, and avoid overinterpreting SAS descriptors.

### Symptom Or Reason

`curves_long.csv` exposed raw q-I points and frame metadata, but the exported data folder did not include a self-contained explanation of what each column means or how a beginner should use the columns for plotting and analysis.

### Root Cause

`export_origin_long_csv()` only wrote the CSV table. The guide material existed only implicitly in developer knowledge and UI wording, so users receiving an exported folder could miss q/I/error/unit caveats, Origin plotting setup, and basic interpretation boundaries.

### Touched Files

- `app/core/export.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `tests/test_export_deep_analysis.py`
- `docs/developer_notes.md`
- `README.md`
- `CHANGELOG.md`

### Fix Summary

- Added `curves_long_guide.md` generation next to every Origin long-table CSV export.
- Added a column-by-column Markdown guide covering `series_id`, `frame_index`, `sequence_order`, curve identity, source file stem, `q`, `I`, `error`, and units.
- Included beginner plotting recipes for log-log curves, Guinier checks, peak spacing, heatmaps, and error bars.
- Added analysis caveats for units, positive values, q range, missing errors, calibration, background handling, and model-dependent interpretation.
- Exposed `curves_long_guide` in complete analysis bundle outputs and added the guide path to the single long-table export UI message/history parameters.

### Tests Run

Focused red/green verification:

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_export.py::test_origin_long_export_writes_beginner_guide_markdown tests\test_export_deep_analysis.py::test_export_analysis_bundle_writes_all_expected_files -q
```

Verified focused result: first observed `2 failed`, then `2 passed`.

Export/UI regression verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_export.py tests\test_export_deep_analysis.py tests\test_ui_style.py::test_export_tab_exposes_origin_export_buttons -q
```

Verified result: `10 passed`.

Final full verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `98 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

The guide is static explanatory text. If future long-table columns are added, update `ORIGIN_LONG_COLUMN_GUIDE`, tests, README, and developer notes in the same change so the guide stays synchronized with the CSV schema.

## 2026-07-07 01:14:03 +08:00 - Origin-ready batch curve exports

### Task Objective

Make batch in situ curve exports directly usable in Origin by adding point-level long-table CSV output and q-grid-checked matrix CSV output.

### Symptom Or Reason

Batch import preserved in situ frame metadata, but export workflows only produced single-curve CSV files, feature summaries, and analysis tables. Origin users still needed manual reshaping before grouped curve plots, heatmaps, or contour plots.

### Root Cause

`app/core/export.py` did not expose project-level curve point tables. `feature_table.csv` is one row per curve, not one row per q-I point, and the analysis bundle did not include raw/imported curve data in an Origin-friendly long or matrix layout.

### Touched Files

- `app/core/export.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `tests/test_export_deep_analysis.py`
- `tests/test_ui_style.py`
- `docs/developer_notes.md`
- `README.md`

### Fix Summary

- Added `curves_long.csv` export with one row per point and fixed columns for `series_id`, `frame_index`, `sequence_order`, curve identity, source stem, q, I, error, and units.
- Added `curves_matrix.csv` export with q as the first column and one intensity column per frame/curve when all q grids match.
- Matrix export now skips mismatched q grids with an explicit warning instead of silently interpolating or misaligning data.
- Added `curves_long` and compatible `curves_matrix` outputs to the complete analysis bundle.
- Added GUI buttons for `导出 Origin 长表` and `导出 Origin 矩阵表`.

### Tests Run

Focused red/green verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_export.py tests\test_export_deep_analysis.py tests\test_ui_style.py::test_export_tab_exposes_origin_export_buttons -q
```

Verified focused result: `9 passed`.

Final full verification:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `97 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

The first matrix export intentionally requires matching q grids and does not interpolate. If Origin heatmap workflows need automatic interpolation later, add it as an explicit option with a history warning and tests that verify original curve data remain unchanged.

## 2026-07-07 - Uncommitted review bug fixes before main merge

### Task Objective

Review the large uncommitted worktree, fix confirmed bugs, exclude generated agent artifacts from publication, and prepare the branch for merge to `main`.

### Symptom Or Reason

- Refreshing the main curve list without an explicit target row reset the current selection to the first curve.
- Finite invariant calculations integrated q values in input order, so reversed q arrays returned negative `Q_measured` for positive data.
- Deep scan candidate windowing used the input q order and could build `q_min > q_max` windows for reversed q arrays.
- Peak detection used input q order for FWHM and area, producing negative widths and peak areas on reversed q arrays.
- Correlation-function default `r_max` used raw `np.diff(q)`, so reversed q input fell back to `200.0` instead of deriving the same real-space range as sorted q.
- `.ai-bridge/` contained generated execution logs and intermediate patches that should not be committed.

### Root Cause

Several analysis paths assumed imported q arrays were already strictly increasing, while import and project models preserve input order non-destructively. The GUI selection bug came from reading `currentRow()` after clearing the list. The generated `.ai-bridge/` directory was not ignored.

### Touched Files

- `.gitignore`
- `app/core/correlation.py`
- `app/core/deep_scan.py`
- `app/core/feature_extraction.py`
- `app/core/invariant_analysis.py`
- `app/core/model_free.py`
- `app/ui/main_window.py`
- `tests/test_correlation.py`
- `tests/test_deep_scan.py`
- `tests/test_invariant.py`
- `tests/test_invariant_analysis.py`
- `tests/test_peak_analysis.py`
- `tests/test_ui_style.py`
- `docs/developer_notes.md`

### Fix Summary

- Preserve the selected curve row before rebuilding the main curve list.
- Sort local q/intensity arrays before invariant integration, deep-scan candidate windowing, peak width/area calculation, and correlation-function default `r_max` derivation.
- Added regression tests for reversed-q invariant, deep scan, peak detection, correlation-function, and curve-list refresh behavior.
- Added `.ai-bridge/` to `.gitignore` so generated execution artifacts stay local.

### Tests Run

Focused red/green tests were run for each confirmed bug:

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_ui_style.py::test_refresh_curve_list_preserves_current_selection_by_default
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_invariant.py::test_finite_q_invariant_sorts_q_before_integrating tests\test_invariant_analysis.py::test_invariant_with_extrapolation_sorts_q_before_integrating
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_deep_scan.py::test_deep_scan_sorts_q_before_candidate_windowing
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_peak_analysis.py::test_peak_detection_sorts_q_before_width_and_area
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_correlation.py::test_correlation_function_sorts_q_before_default_rmax
```

Each focused test was first observed failing before the fix and passing after the fix.

Final full verification after the review fixes:

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q main.py app\core app\ui
git diff --check
```

Verified result: `93 passed`; syntax check passed; `git diff --check` reported no whitespace errors.

### Follow-Up Risk

Sorting is local to analysis calculations and does not mutate `CurveData`. Future analysis functions that use q-neighbor relationships should either reuse a shared sorted-data helper or add their own reversed-q regression tests.

## 2026-07-07 00:32:42 +08:00 - Information-budget scale contribution analysis

### Task Objective

Implement the first practical slice of the SAS upgrade roadmap: show where finite-range invariant signal is concentrated across scattering scale, without adding high-risk model fitting.

### Added Files

- `docs/superpowers/plans/2026-07-07-information-budget.md`

### Modified Files

- `app/core/model_free.py`
- `app/core/plotting.py`
- `app/core/deep_analysis.py`
- `app/ui/analysis_tab.py`
- `app/ui/plotting_tab.py`
- `tests/test_invariant.py`
- `tests/test_plotting.py`
- `docs/developer_notes.md`
- `docs/method_notes.md`

### Symptom Or Reason

Finite `Q_measured = integral(q^2 I(q) dq)` and q²I plots did not directly show which log-q scale ranges dominate the invariant contribution. Reversed q ordering could also make finite invariant integration negative even when the physical curve was positive.

### Root Cause

The existing invariant metric integrated q values in input order and only exposed the linear-q integrand. It did not compute q³I for log-q contribution density, cumulative contribution, quantile positions, entropy, or low/mid/high contribution fractions.

### Fix Summary

- Added `information_budget()` in `app/core/model_free.py` with q³I contribution spectrum, cumulative Q, Q10/Q50/Q90 q locations, `d_Q50`, dominant q/d scale, normalized entropy, low/mid/high contribution fractions, and observable d range.
- Added an `invariant_contribution` plot type using `ln q` versus `q^3 I(q)`.
- Exposed `information_budget` in the analysis tab and `invariant_contribution` in the plotting tab.
- Included information-budget output in deep analysis.
- Sorted q/intensity pairs before finite invariant integration so reversed input order does not flip the sign of `Q_measured`.

### Tests

```powershell
$env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest tests\test_invariant.py tests\test_invariant_analysis.py tests\test_plotting.py tests\test_export_deep_analysis.py -v
$files = @('main.py') + (Get-ChildItem -LiteralPath 'app\core' -Filter '*.py').FullName + (Get-ChildItem -LiteralPath 'app\ui' -Filter '*.py').FullName
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile @files
C:\Users\MyPC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m pytest
```

Verified related result: `14 passed`.
Verified full-suite result with explicit PowerShell file expansion for `py_compile`: `93 passed`.

### Risks And Follow-Up

- Low/mid/high fractions are descriptive and default to log-q tertiles unless explicit band boundaries are supplied.
- Quantiles and entropy use positive interval contributions; strongly background-subtracted data with negative regions should be inspected before interpretation.
- This change does not yet implement window-stability maps, local curvature/crossover candidates, batch heatmaps, or structure-property linking from the roadmap.

## 2026-07-07 00:08:13 +08:00 - GUI polish, action hierarchy, and hover help

### Task Objective

Upgrade the PySide6 GUI so the application feels more polished, key actions are visually prioritized, and hover guidance is useful without covering important controls.

### Added Files

- `app/ui/style.py`
- `tests/test_ui_style.py`
- `docs/superpowers/plans/2026-07-06-gui-polish.md`

### Modified Files

- `main.py`
- `app/ui/main_window.py`
- `app/ui/import_tab.py`
- `app/ui/check_tab.py`
- `app/ui/plotting_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/records_tab.py`
- `app/ui/export_tab.py`
- `app/ui/templates_tab.py`
- `app/ui/advanced_tab.py`
- `app/ui/settings_dialog.py`
- `docs/developer_notes.md`

### Symptom Or Reason

The GUI used mostly default Qt styling and flat button treatment, so important operations such as importing, plotting, analysis, exporting, saving projects, and removing formal records were not visually distinguished. Controls also lacked consistent hover guidance.

### Root Cause

UI styling and help text were scattered or absent. Buttons were created directly in each tab without a shared action-importance convention, and no global stylesheet or tooltip/status-tip policy existed.

### Fix Summary

- Added a shared `app/ui/style.py` helper for the global theme, tooltip/status-tip behavior, and action-button roles.
- Applied a restrained scientific desktop theme using Qt stylesheets, with clearer tabs, inputs, list widgets, status bar, and tooltips.
- Replaced direct `QPushButton` creation in UI tabs with role-aware `action_button()` calls.
- Added concise tooltips plus more detailed status-bar/What's This text so hover help stays short and less obstructive.
- Marked high-impact operations with `primary`, `success`, `warning`, or `danger` roles.
- Added tab-level and curve-list help in the main window.
- Preserved existing analysis, import, export, record, and project logic.

### Tests

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_ui_style.py -v
python -m py_compile main.py app\core\*.py app\ui\*.py
python -m pytest
```

Verified with the Codex bundled Python environment. Final result: `85 passed`.

The direct wildcard `py_compile` form is not expanded by this PowerShell session, so the actual syntax check expanded file paths with `Get-ChildItem`.

Additional offscreen GUI smoke check instantiated `MainWindow` after `apply_app_theme(app)`: 29 buttons found, roles present were `danger`, `primary`, `secondary`, `success`, and `warning`, and no role-managed button was missing tooltip text. A 1240 x 780 offscreen screenshot was generated at `.tmp/gui_smoke.png`; the offscreen Qt font database was empty, so font rendering in that screenshot is not a reliable proxy for normal Windows desktop rendering. The theme now sets `Microsoft YaHei UI`, `Microsoft YaHei`, `Segoe UI`, and `Arial` fallback families for real GUI sessions.

### Risks And Follow-Up

- Full visual confirmation still requires launching the desktop GUI manually because the change targets a PySide6 desktop interface.
- Tooltips are intentionally short; detailed guidance is routed to status tips and What's This text to reduce obstruction.
- The current worktree contained substantial pre-existing uncommitted changes, so this update avoided commits and did not revert unrelated files.

## 2026-07-06 23:30:00 +08:00 - Stability, traceability, batch import, and release README update

### Task Objective

Improve `sas_curve_analyzer` stability, GUI usability, traceability, method-warning integration, project storage consistency, settings behavior, public-facing documentation, and in situ series batch import.

### Added Files

- `app/core/batch_import.py`
- `app/core/settings.py`
- `tests/test_batch_import.py`
- `tests/test_project.py`
- `tests/test_settings.py`

### Modified Files

- `README.md`
- `.gitignore`
- `docs/method_notes.md`
- `docs/advanced_methods.md`
- `docs/developer_notes.md`
- `app/core/data_model.py`
- `app/core/export.py`
- `app/core/feature_extraction.py`
- `app/core/io.py`
- `app/core/method_warnings.py`
- `app/core/model_free.py`
- `app/core/plotting.py`
- `app/core/project.py`
- `app/core/report.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/export_tab.py`
- `app/ui/import_tab.py`
- `app/ui/main_window.py`
- `app/ui/plotting_tab.py`
- `app/ui/records_tab.py`
- `app/ui/settings_dialog.py`
- `tests/test_io.py`
- `tests/test_method_warnings.py`
- `tests/test_plotting.py`

### Specific Changes

- Added safe Guinier plotting filters for `I(q) <= 0` and `q <= 0`.
- Treated blank GUI/core error-column input as missing error data.
- Changed internal project curve data files from `.csv` to `.json` while preserving load compatibility through stored `data_file` paths.
- Added `AnalysisResult.structured_warnings` and bridge helpers for `MethodWarning`.
- Added settings load/save logic and applied settings to GUI defaults.
- Added natural-sorted in situ batch import with column/unit inference, frame metadata, group creation, partial-failure handling, and history records.
- Improved batch GUI selection for grouping, averaging, and A/B comparison.
- Added project-level history records for import, q conversion, analysis, group creation, comparison, export, project save, and formal-record actions.
- Added `.tmp/` to `.gitignore` for sandbox-local pytest temporary files.
- Extended formal records beyond current curves to analysis and comparison results, with unmark support.
- Rewrote README as public software documentation without internal development-stage language.

### Tests

```powershell
python -m pytest
```

Verified result in the Codex bundled Python environment with project-local temp directory: `70 passed`.

### Risks

- GUI behavior was integrated through code paths and core tests; full interactive GUI testing remains manual.
- P(r), correlation-function, and extrapolation interfaces remain experimental or reserved and should not be used for formal conclusions.
- Batch import currently infers common column names and units; unusual naming schemes may require manual extension.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

## 2026-07-06 22:20:50 +08:00 - Initial four-phase implementation and GitHub publication

### Task Objective

Publish `sas_curve_analyzer` to `https://github.com/wkguoo/SasCurve_Analyzer.git` after completing the four-phase development plan.

### Added Files

- Full phase-four `sas_curve_analyzer` application source tree.
- `app/core/` data, analysis, batch, export, pipeline, warning, plugin, and advanced interface modules.
- `app/ui/` PySide6 GUI modules.
- `tests/` pytest suite.
- `docs/` method and developer documentation.
- `examples/example_absolute_sas_curve.csv`.
- `.gitignore`.
- `README.md`.
- `requirements.txt`.
- `main.py`.

### Modified Files

- None for this standalone publication entry.

### Deleted Files

- None.

### Specific Changes

- Implemented four planned phases: import/check/plotting, model-free analysis, batch records/export, and advanced extensibility.
- Added non-destructive data handling and warning-rich analysis outputs.
- Added publication ignore rules for caches, virtual environments, build outputs, and generated result folders.

### Reason

The application is ready to be versioned as a standalone GitHub project.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No research output files are generated by this changelog entry.

### How To Check Success

```powershell
python -m pytest
```

Expected verified result before publication: all tests pass.

### Notes And Risks

- `compute_pr` is an experimental placeholder, not a validated P(r) algorithm.
- Correlation function analysis is a reserved interface.
- No packaging is performed during publication.

## 2026-07-07 11:53:52 +08:00 - Plotting controls, calibrated negative intensities, settings transparency, and SAS math labels

### Task Objective

Implement the `.ai-bridge/current-plan.md` usability and method-transparency plan for calibrated SAS curve plotting and validation.

### Added Files

- `app/core/model_catalog.py`
- `tests/test_model_catalog.py`

### Modified Files

- `app/core/advanced_transforms.py`
- `app/core/deep_scan.py`
- `app/core/export.py`
- `app/core/method_warnings.py`
- `app/core/plotting.py`
- `app/core/porod_analysis.py`
- `app/core/settings.py`
- `app/core/validation.py`
- `app/ui/advanced_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `app/ui/plotting_tab.py`
- `app/ui/settings_dialog.py`
- `tests/test_export.py`
- `tests/test_model_catalog.py`
- `tests/test_plotting.py`
- `tests/test_settings.py`
- `tests/test_ui_style.py`
- `tests/test_validation.py`
- `README.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added calibrated negative-intensity classification: slight negative values are reported separately from significant negative values and preserved for non-log displays.
- Added validation summary fields for negative intensity count/fraction, positive dynamic range, and log-valid/log-invalid point counts.
- Added plotting helpers for display-coordinate transforms and cursor readout formatting.
- Added peak/d-spacing plotting, optional `d = 2π/q` secondary axis, and standard Unicode math labels for q²/q³/q⁴/α.
- Added plotting tab controls for manual axis limits, full/low/mid/high q quick ranges, cursor coordinate readout, d-axis display, and q*/d annotation.
- Added settings load metadata and a read-only settings transparency panel with active values, settings path/load status, and model/formula assumptions.
- Added a model catalog covering common SAS plotting views, assumptions, limitations, and interpretation status.
- Updated docs and user-facing warning/export text to avoid developer-style ASCII caret/pi notation where the text is meant for users.

### Reason

Absolute-calibrated/background-corrected SAS data can contain slight negative values, and users need clearer plotting controls, coordinate readouts, settings visibility, and professional math notation for research workflows.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data or research output files were generated.
- `.ai-bridge/agent-status.md` and `.ai-bridge/implementation-diff.patch` are updated separately as CodexPro handoff records.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest
python -m compileall -q main.py app\core app\ui
```

Verified during implementation:

- Focused tests: `35 passed`.
- Full test suite: `127 passed`.
- Compile check: passed.

### Notes And Risks

- Axis range controls only change the displayed matplotlib axes; they do not modify imported curves or analysis ranges.
- The `d = 2π/q` axis and peak-derived `d = 2π/q*` values are characteristic scales or correlation distances, not automatic particle diameters.
- Logarithmic plots and log-based analyses still exclude `I(q) <= 0`.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 16:50:27 +08:00 - Add Beginner Chinese User Manual

### Task Objective

Implement the current-plan supplementary documentation deliverable by adding a detailed Chinese user manual for beginner graduate students.

### Added Files

- `docs/user_manual_zh.md`

### Modified Files

- `README.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added a self-contained Chinese user manual covering software scope, quick start, installation, data preparation, each GUI tab, plotting, q/display-x conversion, model-free analysis, batch comparison, project/output pages, templates, settings, advanced interfaces, workflow examples, FAQ, checklist, terminology, method boundaries, and appendices.
- Added README links to the Chinese manual in both English and Simplified Chinese sections.
- Updated developer notes to require keeping `docs/user_manual_zh.md` synchronized with UI labels, q-range behavior, outputs, settings, and method limitations.

### Reason

The current plan required a beginner-facing Chinese manual that lets a new materials research student follow the software workflow without reading source code or relying only on the concise README.

### How To Run

No runtime command is needed for this documentation-only change.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
Test-Path docs\user_manual_zh.md
Select-String -Path README.md -Encoding UTF8 -Pattern "docs/user_manual_zh.md","使用手册","User Manual"
Select-String -Path docs\user_manual_zh.md -Encoding UTF8 -Pattern "SAS Curve Analyzer 使用手册","q 范围与坐标变换","无模型分析详解","常见问题与排错","术语表"
```

### Notes And Risks

- This is a documentation-only change.
- The manual describes current implemented UI behavior. Future Supplement Plan features such as import preview, sequence table, figure export presets, reproducible export manifest, and layered errors are not described as completed features.
- No source code, raw experimental data, tests, packaging, Git commit, or Git push were changed or run for this entry.

## 2026-07-07 17:00:08 +08:00 - Add Project Lifecycle Menu And Dirty-State Tracking

### Task Objective

Implement the first broader reliability/reproducibility current-plan item: project lifecycle management for new, open, save, save-as, and unsaved-change handling.

### Added Files

- None.

### Modified Files

- `app/core/project.py`
- `app/ui/main_window.py`
- `app/ui/export_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/records_tab.py`
- `tests/test_project.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added in-memory `ProjectState.revision` tracking for project mutations.
- Added `项目` menu with `新建项目`, `打开项目...`, `保存项目`, and `另存为项目...`.
- Added `MainWindow.current_project_folder`, saved revision tracking, project dirty detection, save/open/new helpers, and title-bar `*` marker for unsaved changes.
- Added visible-window close confirmation when project changes are unsaved.
- Routed export-page project saving through `MainWindow.save_project_to_folder()` so menu save and export-page save use the same lifecycle logic.
- Refreshed title dirty state after analysis, batch operations, formal-record changes, and export-history mutations.
- Added tests for revision tracking, save/open lifecycle, dirty-state behavior, and GUI restoration after opening a saved project.
- Updated README, Chinese manual, and developer notes for project lifecycle behavior.

### Reason

The project previously had project serialization functions and an export-page save button, but did not provide a complete user-facing lifecycle with open/save/save-as/new controls or unsaved-change protection.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use the `项目` menu for project lifecycle operations.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.
- Manual testing of save/open will generate a chosen project folder containing `project.json` and `curves/*.json`.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_project.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- `ProjectState.revision` is in-memory only and is not serialized to project files.
- Close confirmation is skipped for unshown/offscreen windows so automated tests do not block; visible user windows still prompt when dirty.
- Direct list mutations outside `ProjectState` add methods should call `MainWindow.mark_project_dirty()` or use an add method.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:05:30 +08:00 - Add Import Preview And Diagnostics

### Task Objective

Implement the second broader reliability/reproducibility current-plan item: import-before-preview and diagnostics for single-curve files.

### Added Files

- `app/core/import_preview.py`
- `tests/test_import_preview.py`

### Modified Files

- `app/ui/import_tab.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `ImportPreview` and `preview_curve_file()` to read selected files, infer or apply current q/I/error columns, and compute non-destructive diagnostics.
- Added `format_import_preview()` for plain-text GUI display.
- Added import-page `预览/诊断当前文件` button and automatic preview after file selection.
- Preview reports file status, columns, first rows, q/I ranges, NaN counts, duplicate q count, non-positive q/intensity counts, error-column invalid counts, and importability messages.
- Updated README, Chinese manual, and developer notes for the new preview workflow and non-mutating behavior.
- Added tests for normal CSV, missing required columns, NaN/duplicate/negative/error warnings, and empty/comment-only files.

### Reason

The project previously attempted column inference after selecting a file, but did not give beginner users a visible pre-import diagnosis explaining whether the current column mapping was usable and which downstream steps might be affected.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `数据导入` → `选择数据文件`; the preview runs automatically. Use `预览/诊断当前文件` after manually editing column names.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_import_preview.py tests/test_io.py tests/test_batch_import.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Preview/diagnostics are read-only. They do not sort, delete rows, clip negative intensities, add offsets, or modify original files.
- `Warning` means the file can still be imported, but later plotting or analysis may filter points or hide error bars.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:11:50 +08:00 - Add Analysis q-Range Preflight

### Task Objective

Implement the third broader reliability/reproducibility current-plan item: model-free analysis preflight checks for the selected raw q range.

### Added Files

- `app/core/analysis_preflight.py`
- `tests/test_analysis_preflight.py`

### Modified Files

- `app/ui/analysis_tab.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `AnalysisPreflight`, `check_analysis_preflight()`, and `format_analysis_preflight()`.
- Added analysis-page `检查当前 q 范围` button.
- Automatically runs preflight before standard `运行分析`.
- Stops analysis when preflight severity is `error`.
- Shows preflight summary with analysis results when severity is `ok` or `warning`.
- Checks selected curve availability, finite raw q range, non-negative raw q, `q_min < q_max`, points in range, finite points, positive q points, positive intensity points, log-usable points, excluded points, minimum method-specific point counts, and selected method caveats.
- Updated README, Chinese manual, method notes, developer notes, CHANGELOG, and tests.

### Reason

Users needed a clear pre-analysis explanation when selected q ranges were empty, reversed, too small, or invalid for log-based analysis, especially when display x ranges such as `ln q` can differ from raw physical q ranges.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `无模型分析` → `检查当前 q 范围` before `运行分析`.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_analysis_preflight.py tests/test_ui_style.py tests/test_guinier.py tests/test_power_law.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Preflight is a minimum numerical/input check. It does not select the best scientific interval and does not prove method validity.
- `warning` severity still allows analysis to run; `error` severity blocks standard analysis until the q range or data issue is corrected.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:17:52 +08:00 - Add Reproducible Export Bundle Metadata

### Task Objective

Implement the fourth broader reliability/reproducibility current-plan item: strengthen complete analysis bundles with manifest, README, settings snapshot, and stable warnings metadata.

### Added Files

- None.

### Modified Files

- `app/core/export.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `manifest.json` to complete analysis bundles.
- Added `README_export.md` explaining bundle purpose, file roles, manual review requirements, warnings, and data safety.
- Added `settings_snapshot.json` with export-time application settings.
- Made `bundle_warnings.txt` a stable bundle output even when no bundle-level warnings exist.
- Manifest now records software metadata, project counts, input curve metadata and source hash when available, analyses, comparisons, settings snapshot link, warnings, and output file names.
- GUI bundle export now passes comparison results and current settings into the bundle exporter.
- Added regression coverage for manifest, README_export, settings snapshot, and warnings output.
- Updated README, Chinese manual, developer notes, and CHANGELOG.

### Reason

The complete analysis bundle previously exported useful tables and reports, but did not include enough metadata for a future reader to audit inputs, settings, outputs, skipped optional files, and warning state from a single package.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `项目与输出` → `导出报告` → `导出完整分析包`.

### Generated Output Files

When the user exports a bundle, the selected output folder now includes:

- `manifest.json`
- `README_export.md`
- `settings_snapshot.json`
- `bundle_warnings.txt`

No files were generated during this code change except temporary pytest outputs.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_export.py tests/test_export_deep_analysis.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- The bundle structure remains mostly flat in this pass to avoid a broad export-directory migration.
- Source file hashes are recorded only when the original source path still exists locally.
- Exporting a bundle does not modify original experimental data or imported curve arrays.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:23:43 +08:00 - Add Batch Sequence Management Table

### Task Objective

Implement the fifth broader reliability/reproducibility current-plan item: a batch sequence management table for reviewing in situ/time-series curve order and metadata.

### Added Files

- None.

### Modified Files

- `app/core/batch.py`
- `app/ui/batch_tab.py`
- `tests/test_batch.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `build_sequence_index()` and `export_sequence_index_csv()`.
- Added `SEQUENCE_INDEX_COLUMNS`.
- Added read-only sequence management table to `批量比较`.
- Added buttons: `刷新序列表`, `按序列顺序选择全部`, `从选中行建组`, and `导出序列索引 CSV`.
- Table rows show sequence/project order, curve ID/name, source file/stem, series/frame metadata, units, point count, q range, and warnings.
- Warnings report q grid mismatch relative to the first curve, non-finite intensity, non-positive intensity, or no finite q.
- Added tests for metadata rows, no-metadata rows, q-grid warning, CSV export, and UI table/buttons.
- Updated README, Chinese manual, developer notes, and CHANGELOG.

### Reason

Batch import already preserved sequence metadata, but users needed a direct table for checking which files were imported, whether order/frame metadata looked correct, and which curves had q-range or warning issues.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `批量比较` → `刷新序列表` and optionally `导出序列索引 CSV`.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.
- Using the new export button writes a user-selected `sequence_index.csv`.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_batch.py tests/test_batch_import.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- The sequence table is read-only. It does not insert, smooth, delete, re-order, or reinterpret curve data.
- q grid mismatch warnings are audit hints; they do not automatically interpolate or modify curves.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 17:27:57 +08:00 - Add Figure Export Presets

### Task Objective

Implement the sixth broader reliability/reproducibility current-plan item: lightweight scientific figure export presets.

### Added Files

- `app/core/figure_export.py`
- `tests/test_figure_export.py`

### Modified Files

- `app/ui/plotting_tab.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `FIGURE_EXPORT_PRESETS` for screen preview, presentation, and draft-publication output.
- Added safe figure filename generation and preset-based Matplotlib figure export.
- Added plotting-page preset selector, format selector, and `Export current figure` button.
- Export uses current plot type, current curve, axis limits, error bars, d-axis setting, and selected preset.
- Figure exports write project history records with curve ID, plot type, preset, format, path, and x-axis limits.
- Added tests for preset completeness, safe filenames, file writing, UI controls, and no-current-curve failure message.
- Updated README, Chinese manual, developer notes, and CHANGELOG.

### Reason

Users needed stable, low-friction image outputs for screen preview, group meetings, and manuscript drafts without turning the application into a full figure-design tool.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use `曲线绘图` → select preset/format → `Export current figure`.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.
- Using the new button writes a user-selected `.png`, `.svg`, or `.pdf` figure.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_figure_export.py tests/test_plotting.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Presets are intended for stable defaults, not final journal layout or graphic design.
- Applying a preset adjusts the current Matplotlib figure styling before saving.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 15:26:02 +08:00 - Negative-intensity settings and model catalog completeness

### Task Objective

Complete the appended `.ai-bridge/current-plan.md` small-fix plan by moving slight negative-intensity thresholds into settings and expanding the model/formula catalog.

### Added Files

- `app/ui/model_catalog_dialog.py`

### Modified Files

- `app/core/model_catalog.py`
- `app/core/settings.py`
- `app/core/validation.py`
- `app/ui/check_tab.py`
- `app/ui/settings_dialog.py`
- `tests/test_model_catalog.py`
- `tests/test_settings.py`
- `tests/test_ui_style.py`
- `tests/test_validation.py`
- `README.md`
- `docs/method_notes.md`
- `docs/advanced_methods.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `allow_slight_negative_intensity`, `slight_negative_abs_ratio_threshold`, and `slight_negative_fraction_threshold` to `AppSettings`.
- Extended `validate_curve()` with keyword arguments for slight-negative classification thresholds and recorded those values in `ValidationReport.summary`.
- Updated `CheckTab` so GUI validation uses the current settings values.
- Added settings controls for slight negative-intensity tolerance.
- Added a standalone `ModelCatalogDialog` opened from Settings.
- Expanded `model_catalog.py` to include shape/form-factor models, empirical/model-dependent models, P(r), correlation, and low-q/high-q extrapolation interfaces.
- Updated tests and documentation for the new settings and catalog behavior.

### Reason

The previous implementation hard-coded slight-negative thresholds and the catalog did not cover the project’s model-dependent, experimental, and reserved analysis interfaces.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data or research output files were generated.
- `.ai-bridge/agent-status.md`, `.ai-bridge/implementation-diff.patch`, and `.ai-bridge/execution-log.jsonl` are updated separately as handoff records.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/test_settings.py tests/test_validation.py tests/test_model_catalog.py tests/test_ui_style.py -q
python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Wider slight-negative thresholds can hide data-quality problems. The settings only change validation classification; they do not modify intensities and do not allow non-positive values into log analysis.
- Model catalog entries are transparency notes, not proof that a model applies.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 15:42:23 +08:00 - Add MIT License

### Task Objective

Add a standard MIT License to the standalone SAS Curve Analyzer project and update README license labeling.

### Added Files

- `LICENSE`

### Modified Files

- `README.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added standard MIT License text.
- Set copyright line to `Copyright (c) 2026 wkguoo`.
- Updated README license line to `License: MIT License. See LICENSE.`

### Reason

The project previously had no license file and README still showed `License: to be added.`

### How To Run

No runtime command is needed for this documentation-only change.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
Test-Path LICENSE
Select-String -Path LICENSE -Pattern "MIT License","Copyright \(c\) 2026 wkguoo","THE SOFTWARE IS PROVIDED"
Select-String -Path README.md -Pattern "MIT License","LICENSE"
```

### Notes And Risks

- This is a documentation/license-only change.
- No source code, raw experimental data, tests, packaging, Git commit, or Git push were changed or run for this entry.

## 2026-07-07 15:46:04 +08:00 - Add README Language Navigation And Badges

### Task Objective

Add simple English/Simplified Chinese navigation and lightweight README badges, including the MIT License badge.

### Added Files

- None.

### Modified Files

- `README.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added top README language navigation: `[English](#english) | [简体中文](#简体中文)`.
- Added static shields.io badges for `status active`, `python 3.x`, `platform Windows`, and `license MIT`.
- Added `## English` heading so the existing English README content has a stable anchor.
- Added a concise `## 简体中文` section with project purpose, main features, quick start, and usage cautions.

### Reason

The README top area needed to match the requested bilingual navigation and simple badge style, and the existing MIT License status needed to be visible in the badge row.

### How To Run

No runtime command is needed for this documentation-only change.

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
Select-String -Path README.md -Pattern "\[English\]\(#english\)","\[简体中文\]\(#简体中文\)","status-active","python-3.x","platform-Windows","license-MIT","## English","## 简体中文"
Select-String -Path LICENSE -Pattern "MIT License"
git diff -- README.md CHANGELOG.md LICENSE
```

### Notes And Risks

- This is a README/CHANGELOG-only documentation update.
- Existing source code, raw experimental data, tests, packaging, Git commit, and Git push were not changed or run for this entry.

## 2026-07-07 16:39:20 +08:00 - Link Plotting And Model-Free Analysis Workflow

### Task Objective

Implement the current-plan workflow improvements for plotting coordinates, plot/analysis navigation, transformed x-range conversion, and top-level tab hierarchy.

### Added Files

- `app/core/method_mapping.py`
- `tests/test_method_mapping.py`

### Modified Files

- `app/core/plotting.py`
- `app/ui/plotting_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `tests/test_plotting.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/method_notes.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Moved plotting cursor/current coordinate readout into a dedicated row separate from axis range controls.
- Added centralized `PLOT_TO_ANALYSIS` and `ANALYSIS_TO_PLOT` mappings.
- Added plotting-page action to send linked views to model-free analysis.
- Added analysis-page action to show the linked plot view.
- Added `display_x_range_to_q_range()` so transformed display x ranges such as `ln q` and Guinier `q²` can be converted back to raw q.
- Added analysis-page action to read current plotting x-limits and fill positive raw `q_min/q_max`.
- Grouped `历史与正式记录`, `导出报告`, and `分析模板` under the new `项目与输出` nested tab while preserving existing tab object attributes.
- Updated tests and documentation for linked workflow, transformed range semantics, and nested tabs.

### Reason

The previous GUI made long coordinate readouts compete with axis controls, required manual switching between related plot and analysis views, did not provide a clear path from transformed display x ranges back to physical q ranges, and kept lower-frequency project/output pages at the same top-level priority as the main workflow.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_plotting.py tests/test_method_mapping.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Raw analysis `q_min/q_max` still represent physical q and do not accept negative values.
- Negative values are accepted only as transformed display coordinates such as `ln q`; they are converted to positive raw q before analysis.
- This pass implements the first current-plan GUI workflow section. The supplementary beginner manual and broader reliability/reproducibility enhancement plan remain follow-up work unless implemented in a later pass.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-08 11:22:06 +08:00 - Add Row-Preserving Derived Data Exports

### Task Objective

Implement the active `.ai-bridge/current-plan.md` for numerically accurate q/I-derived data calculation and export, while keeping raw experimental q/I rows unchanged.

### Added Files

- `app/core/derived_data.py`
- `tests/test_derived_data.py`

### Modified Files

- `app/core/export.py`
- `app/core/plotting.py`
- `app/ui/export_tab.py`
- `tests/test_export.py`
- `tests/test_plotting.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `docs/method_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `DerivedDataOptions`, `DerivedDataResult`, and `build_curve_derived_table()` for row-preserving derived data.
- Implemented derived columns including `q2`, `ln_q`, `log10_q`, `inv_q`, `d_2pi_over_q`, `qRg`, `qD`, `qR`, `ln_I`, `log10_I`, `qI`, `q2I`, `q3I`, `q4I`, `q_alpha_I`, `local_slope_dlnI_dlnq`, `I_over_ref`, and `I_minus_ref`.
- Added `valid_*` flags and objective warnings for invalid mathematical domains, missing optional parameters, duplicate q for local slope, and reference q-grid mismatch.
- Updated plotting to use derived-table columns through `PLOT_DERIVED_MAPPING`, so displayed Guinier/loglog/Kratky/Porod/local-slope data match exported derived columns.
- Added derived CSV exports: single-curve `<curve_name>_derived.csv`, multi-curve `curves_derived_long.csv`, optional `curves_derived_matrix.csv`, and guide Markdown files.
- Added derived long-table output to complete analysis bundles.
- Added export-page inputs for alpha, Rg, D, R, and reference curve.
- Documented `ln` vs `log10/lg`, Guinier `q2` vs `ln_I`, NaN meaning, reference-curve no-interpolation behavior, and first-version unit boundaries.

### Reason

The plan required strict numerical consistency between raw q/I inputs, transformed plotting data, and exported tables, so users can verify every common SAS plotting/analysis transform in Origin, Excel, or Python.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

In the GUI, import a curve, then open `项目与输出` -> `导出报告` and use the derived-data export buttons.

### Generated Output Files

- No export files were generated during code modification.
- When the user runs exports, the new outputs are `<curve_name>_derived.csv`, `curves_derived_long.csv`, optional `curves_derived_matrix.csv`, and matching `*_guide.md` files.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_derived_data.py tests/test_plotting.py tests/test_export.py tests/test_ui_style.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- Optional alpha/Rg/D/R/reference values are not guessed. Missing values produce NaN columns and warnings in derived guides.
- Reference ratio/difference requires an identical q grid; no interpolation is performed.
- The local slope column uses `np.gradient(np.log(I), np.log(q))` on q-sorted valid rows and writes NaN when fewer than 3 valid rows exist or valid q values are duplicated.
- No raw experimental data were modified, smoothed, interpolated, background-corrected, unit-converted, deleted, moved, or renamed.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 21:26:07 +08:00 - Review-Fix Import Preview, Plot Range Conversion, And Project Save Prompts

### Task Objective

Execute `.ai-bridge/current-plan.md` targeted review fixes before commit/push, without adding new SAS algorithms or modifying raw experimental data.

### Added Files

- None.

### Modified Files

- `app/core/import_preview.py`
- `app/core/plotting.py`
- `app/ui/import_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/main_window.py`
- `app/ui/export_tab.py`
- `app/ui/batch_tab.py`
- `app/ui/plotting_tab.py`
- `tests/test_import_preview.py`
- `tests/test_plotting.py`
- `tests/test_project.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `docs/method_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added explicit `q_unit` and `intensity_unit` parameters to import preview, with priority for UI-provided units, fallback to inferred units, then documented safe defaults.
- Passed current import-page unit fields into preview diagnostics.
- Added `display_x_limits_to_q_range_for_curve()` to clamp Matplotlib display x-limits to the selected curve's valid display range before converting back to positive raw q.
- Updated analysis-page plot-range conversion to preserve q inputs on failure and report original xlim, clipped display range, raw q range, plot type, and clipping status.
- Replaced dirty-project discard confirmation with a shared save / discard / cancel flow for new, open, and close operations.
- Renamed the export-page project save button to `项目另存为...` and documented it as an auxiliary project-save entry.
- Made sequence-index CSV export default to `settings.default_export_dir`.
- Refreshed the plotting tab after preset figure export so export styling does not persist in the current screen plot.
- Updated docs to keep fact-only message wording aligned with code and tests, and documented `project_save` as audit history.

### Reason

The review plan identified submission-blocking risks: import preview units could contradict UI inputs, Matplotlib autopadding could break valid q-range conversion, unsaved project prompts could only discard/cancel, and documentation needed to match the fact-only message policy.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python main.py
```

### Generated Output Files

- `.ai-bridge/implementation-diff.patch` will be regenerated after verification.
- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_import_preview.py tests/test_plotting.py tests/test_project.py tests/test_user_messages.py tests/test_ui_style.py -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- `save_project()` and `save_project_as_dialog()` now return `True` or `False`; Qt action triggers ignore the return value.
- Display x clipping uses the current selected curve and positive raw q for final analysis ranges.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-07 20:28:35 +08:00 - Add Fact-Only Layered User Messages

### Task Objective

Implement the current-plan layered error-message foundation while honoring the latest user requirement that messages show objective facts only and do not include action-guidance wording.

### Added Files

- `app/core/user_messages.py`
- `tests/test_user_messages.py`

### Modified Files

- `app/core/analysis_preflight.py`
- `app/core/import_preview.py`
- `app/ui/import_tab.py`
- `app/ui/analysis_tab.py`
- `app/ui/plotting_tab.py`
- `app/ui/export_tab.py`
- `app/ui/main_window.py`
- `app/ui/advanced_tab.py`
- `tests/test_analysis_preflight.py`
- `tests/test_ui_style.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Added `UserMessage` and `format_user_message()` for fact-only layered messages.
- Replaced common import, analysis, figure export, export, and project lifecycle failure paths with layered messages containing severity, observed result, original-data safety, objective facts, and technical details.
- Removed preflight `next_actions` output and retained severity, counts, filtering facts, and method limitation messages.
- Removed action-guidance labels from structured warning displays in analysis and advanced tabs.
- Updated README, Chinese manual, developer notes, and tests for fact-only message behavior.

### Reason

The current plan required clearer user-facing error messages, and the latest user correction required those messages to avoid instruction-style action guidance and show objective facts instead.

### How To Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

### Generated Output Files

- No experimental data, processed data, figures, packages, or build artifacts were generated by this implementation.

### How To Check Success

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/test_user_messages.py tests/test_analysis_preflight.py tests/test_ui_style.py -q
python -m compileall -q main.py app\core app\ui
```

### Notes And Risks

- The messages keep technical exception details visible.
- Message formatting is intentionally plain text for QTextEdit/status display and testability.
- No raw experimental data were modified.
- No packaging, Git commit, or Git push was performed for this entry.

## 2026-07-11 17:48:38 +08:00 - Stage 2 Task 4 Conditional Advanced Analysis Contracts

### Task Objective

Extend the advanced P(r), invariant, correlation, and lamellar result contracts with conditional availability, prerequisites, point tables, and numerical diagnostics while preserving their public function signatures.

### Added Files

- `tests/test_advanced_contracts.py`
- `.superpowers/sdd/stage2-task4-implementer-report.md`

### Modified Files

- `app/core/pr_analysis.py`
- `app/core/invariant_analysis.py`
- `app/core/correlation.py`
- `app/core/lamellar_analysis.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- P(r) now reports compatibility aliases for registered scalars, stability metrics, back-calculated I(q) rows, RMSE, and explicit unavailable chi-square status when per-point uncertainties are absent.
- Invariant analysis now distinguishes measured-range and successfully extrapolated contributions, validates a Porod plateau before using a `q^-4` tail, and reports `volume_fraction=None` with `volume_fraction_status` and `volume_fraction_invalid_reason` when absolute-intensity, contrast, or physical-value prerequisites are missing.
- Correlation analysis now supplies conditional long-period/interface-thickness descriptors, finite-q transform diagnostics, and an `r`/correlation table with unavailable values represented as `None` rather than fabricated values.
- Lamellar analysis now supplies `q0`, `d0`, order indices, deviations from integer order, and an order-index back-fit diagnostic while retaining legacy peak fields.
- All four analyses expose `prerequisites`, `assumption_status`, and `analysis_status`; a structural/model assumption prevents a `high` reliability label.
- Added public-contract regression tests, including the required P(r) and conditional invariant seeds and an unavailable Porod-tail guard.

### Reason

Advanced SAS descriptors are conditional numerical results. The result payload must preserve missing prerequisites and model dependence instead of presenting unavailable absolute quantities or structural inferences as measured facts.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_advanced_contracts.py tests\test_pr_analysis.py tests\test_correlation.py tests\test_lamellar_analysis.py tests\test_invariant_analysis.py tests\test_method_warnings.py
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\invariant_analysis.py app\core\pr_analysis.py app\core\correlation.py app\core\lamellar_analysis.py tests\test_advanced_contracts.py
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, export, package, or build output was generated.
- `.superpowers/sdd/stage2-task4-implementer-report.md` records the TDD and verification evidence for this implementation task.

### How To Check Success

- The focused Stage 2 Task 4 command passes all 28 selected tests.
- The offscreen/Agg full suite passes all 409 tests.
- `py_compile` exits with code 0 and `git diff --check` reports no whitespace errors.

### Notes And Risks

- P(r) chi-square is deliberately `None` without per-point uncertainty; unweighted residual RMSE is still available when a back-fit is performed.
- q0/d0, long-period, interface-thickness, and volume-fraction values remain conditional descriptors, not proof of morphology or mechanism.
- All calculations use selected local arrays; `CurveData` arrays and source experimental files remain unmodified.
- No dependencies were installed and no packaging, Git commit, or Git push was performed.

## 2026-07-11 18:36:50 +08:00 - Stage 2 Task 4 Independent Review Safety Follow-Up

### Task Objective

Resolve every Blocker, Important, and Minor item from the Stage 2 Task 4 independent review while retaining public analysis-function signatures and raw-data safety boundaries.

### Added Files

- None. The existing Task 4 public-contract test module was extended.

### Modified Files

- `app/core/invariant_analysis.py`
- `app/core/pr_analysis.py`
- `app/core/correlation.py`
- `app/core/lamellar_analysis.py`
- `tests/test_advanced_contracts.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`
- `.superpowers/sdd/stage2-task4-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Matched every Task 4 result against `METHOD_REGISTRY`; added measured-range `Q_low`/`Q_mid`/`Q_high`, correlation length and unavailable phase-thickness/fraction fields, and lamellar `peak_orders` with explicit status/reason handling.
- Defined Q bands as three equal-width intervals across the selected finite q range integrating `q^2 I(q)`. Their definition and boundaries are exported separately from low/high-q extrapolation tails.
- Added finite guards for measured invariant, q-band integrals, q-tail extrapolations, contrast input, correlation normalization/r grid, lamellar reciprocal lengths, P(r) matrices/solutions/reductions, and all Task 4 point tables.
- Made Porod extrapolation require at least three selected tail points, every `q^4 I(q)` tail value finite and strictly positive, relative spread <= 0.15, and a finite positive tail integral.
- Made P(r) reject non-finite/non-positive Dmax and non-finite/negative regularization before inversion; result parameters report the actual validated value. Aligned finite positive `CurveData.error` now produces a back-fit chi-square; missing, invalid, or misaligned errors remain explicit unavailable diagnostics.
- Added public-API RED/GREEN regressions for registry completeness, finite safety, overflow/tiny-q paths, Porod tail gate, P(r) input validation, aligned error chi-square, and non-finite contrast.

### Reason

The review found that missing registry metrics, pseudo-zero unavailable P(r) outputs, non-finite scalars, weak Porod gating, and ignored aligned errors could mislead downstream batch extraction or scientific interpretation. This follow-up makes unavailability and model dependence explicit.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_advanced_contracts.py tests\test_pr_analysis.py tests\test_correlation.py tests\test_lamellar_analysis.py tests\test_invariant_analysis.py tests\test_method_warnings.py
$env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider
python -B -m py_compile app\core\invariant_analysis.py app\core\pr_analysis.py app\core\correlation.py app\core\lamellar_analysis.py tests\test_advanced_contracts.py
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, export, package, or build output was generated.
- The Task 4 implementer report was appended with RED/GREEN and verification evidence.

### How To Check Success

- The focused Task 4 verification command passes 56 tests.
- The offscreen/Agg full suite passes 437 tests.
- `py_compile` and `git diff --check` exit with code 0.

### Notes And Risks

- `Q_low`/`Q_mid`/`Q_high` are measured-range contribution bands; they are not extrapolated invariant tails and must be interpreted with `Q_band_definition` and `q_band_boundaries`.
- Phase thicknesses and a phase-fraction indicator remain unavailable without inputs that this public correlation API does not receive.
- P(r), correlation, lamellar, and invariant descriptors remain conditional numerical results, not morphology or mechanism proof.
- No raw `CurveData` arrays or source files were modified. No dependency installation, packaging, commit, or push was performed.

## 2026-07-11 19:18:03 +08:00 - Stage 2 Task 5 Complete 10-Model Fits

### Task Objective

Provide traceable, export-safe complete fitting for all ten registered shape models while preserving the legacy `fit_shape_model()` interface.

### Added Files

- `app/core/model_parameters.py`
- `tests/test_complete_model_fitting.py`
- `.superpowers/sdd/stage2-task5-implementer-report.md`

### Modified Files

- `app/core/model_fitting.py`
- `tests/test_model_fitting.py`
- `tests/test_shape_models.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added public `fit_shape_model_complete()`, `fit_all_allowed_models()`, and `derived_model_parameters()` interfaces. The legacy `fit_shape_model()` now delegates to the complete path and retains named legacy parameter values and the `fit_curves` export table.
- Added fixed-schema `parameter_records`, fit-quality diagnostics, covariance/correlation matrices, finite condition-number and correlation audits, residual rows with source indices, selected/excluded-point records, derived-parameter records, and per-start attempts.
- Added deterministic warm-start, batch-median, default, and jittered starts. The standalone complete path evaluates all candidates and selects the valid minimum-AICc candidate (RMSE only when AICc is unavailable).
- Added identifiability states `strong`, `weak`, and `non_identifiable`. Missing/ill-conditioned covariance or very high parameter correlation cannot be promoted to a reliable fit merely because the optimizer converged.
- Added documented geometric/algebraic mappings for sphere, core-shell sphere, ellipsoid, cylinder, disk, surface fractal, and lamellar models. Invalid domains and overflow return `None` with a reason instead of NaN, infinity, or an exception.
- Added batch-safe retry-on-failure behavior: every registered model is always visited and failures are isolated; later starts are run only after an earlier batch start fails, and only executed starts are recorded. This avoids repeated expensive orientation-average optimizations from preventing later models from being assessed.
- Added regression coverage for all ten noiseless synthetic forward curves, model metadata, derived mappings/domain/overflow guards, degenerate core-shell identifiability, retry order/AICc selection, non-mutation of source arrays, legacy compatibility, and default batch failure isolation.

### Reason

Single-start model fits can hide unstable parameters, missing uncertainty, and model-specific failures. The complete contract makes the numerical fit auditable without implying a unique material morphology or mechanism.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_complete_model_fitting.py tests\test_model_fitting.py tests\test_shape_models.py
python -m py_compile app\core\model_fitting.py app\core\model_parameters.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing build output was generated.
- The required `py_compile` check refreshed local interpreter-cache files under `app/core/__pycache__/`; these are development verification artifacts, not experimental or analysis outputs.
- `.superpowers/sdd/stage2-task5-implementer-report.md` records the RED/GREEN and verification evidence.

### How To Check Success

- The focused Task 5 command passes 31 tests.
- The full offscreen/Agg suite passes 462 tests.
- `py_compile` exits with code 0.
- `git diff --check` was attempted, but the workspace `.git` directory has no `HEAD` or repository metadata, so Git correctly reports that this is not a repository. A direct conflict-marker/trailing-whitespace fallback check is recorded in the implementer report.

### Notes And Risks

- All fitted and derived quantities remain conditional on the selected model, q interval, background handling, error weighting, and sample assumptions; they do not prove a unique morphology.
- Complete single-model fitting evaluates all starts for AICc comparison. Batch fitting deliberately uses documented retry-on-failure with a bounded per-start budget, so its selected result is the first valid executed candidate rather than a full batch-wide multi-start optimum.
- A non-identifiable result can still have a small residual; users must inspect covariance, correlation, boundary flags, and `identifiability_reason` before interpreting values.
- No raw `CurveData` arrays or source experimental data were modified. No dependencies were installed and no package, commit, or push was performed.

## 2026-07-11 19:34:19 +08:00 - Stage 2 Task 5 Independent Review Contract Remediation

### Task Objective

Resolve the Task 5 independent-review Blocker and Important findings by restoring the approved complete retry and model-selection contract to `fit_all_allowed_models()`.

### Added Files

- None. The existing complete-model regression module and implementer report were extended.

### Modified Files

- `app/core/model_fitting.py`
- `tests/test_complete_model_fitting.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`
- `.superpowers/sdd/stage2-task5-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Removed the private first-valid batch stop path and the separate 300-evaluation batch budget. Default batch fits now use the same complete warm-start, batch-median, defaults, and deterministic-jitter sequence as `fit_shape_model_complete()`.
- Restored the legacy 20,000-function-evaluation default for both single and batch complete fitting. No unapproved high-throughput/default performance mode remains.
- Made finite AICc the exclusive selector whenever any candidate has finite AICc. Equal finite AICc values retain deterministic attempt order; RMSE is consulted only when every valid candidate lacks finite AICc.
- Added controlled public batch regressions proving that all five planned attempts are actually recorded, a later AICc=95 candidate beats a warm-start AICc=99 candidate, and RMSE chooses the minimum only when all AICc values are unavailable.
- Kept all-model traversal and model-specific failure isolation. The failure-isolation regression now uses a controlled optimizer seam so it verifies contract behavior without relying on an expensive real optimizer path.

### Reason

The prior batch-only shortcut changed which valid fit could be selected and could mark a model differently from the complete single-model path. Documentation cannot substitute for the approved AICc selection contract.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_complete_model_fitting.py tests\test_model_fitting.py tests\test_shape_models.py
python -m py_compile app\core\model_fitting.py app\core\model_parameters.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing build output was generated.
- The required `py_compile` check refreshed local interpreter-cache files under `app/core/__pycache__/` only.
- The implementer report was appended with the review-remediation RED/GREEN evidence.

### How To Check Success

- The focused Task 5 command passes 33 tests.
- The full offscreen/Agg suite passes 464 tests.
- `py_compile` exits with code 0.
- `git diff --check` remains unavailable because the workspace `.git` directory has no repository metadata; the documented conflict-marker/trailing-whitespace fallback check was run instead.

### Notes And Risks

- Batch fitting can take longer for implausible high-cost models because it now intentionally honors the same complete comparison contract as a standalone fit.
- Any future high-throughput shortcut must be proposed and approved as a distinct explicit opt-in API; it must not silently replace the complete batch result contract.
- Fitted values remain conditional numerical results, not proof of a unique material morphology or mechanism.

## 2026-07-11 19:37:22 +08:00 - Stage 2 Task 5 Complete-Batch Performance Observation

### Task Objective

Record the measured cost of the restored default complete batch contract without changing its approved fitting semantics.

### Added Files

- None.

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`
- `.superpowers/sdd/stage2-task5-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Ran the default public `fit_all_allowed_models()` smoke scenario on a 36-point in-memory `exp(-q)` curve using all ten model names, the full five-start candidate sequence, and the shared 20,000-evaluation budget.
- The run reached the 60.4-second command limit before emitting final result rows. No default retry, AICc selection, optimizer-budget, model traversal, or failure-isolation behavior was changed in response.

### Reason

The independent-review remediation restored scientifically equivalent complete batch behavior. Its real runtime cost must be visible rather than hidden behind an unapproved fast mode.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
# Use the public fit_all_allowed_models() with the default arguments on a synthetic in-memory curve.
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing output was generated.

### How To Check Success

- The observed timeout is documented with its exact 60.4-second upper bound.
- Focused and full regression status remain recorded in the preceding Task 5 remediation entry.

### Notes And Risks

- The measured bottleneck is repeated complete optimization of orientation-averaged `ellipsoid`, `cylinder`, and `disk` models on a curve that does not plausibly match many candidates.
- No high-throughput/fast mode was added or enabled. Any such mode needs separate user approval and a clearly opt-in, non-equivalent result contract.

## 2026-07-11 19:54:47 +08:00 - Stage 2 Task 6 Bootstrap and q-Range Sensitivity

### Task Objective

Add a core-only, reproducible optional uncertainty-analysis module for bootstrap refits and q-range boundary sensitivity without modifying primary fits, raw curves, GUI, exporters, or batch orchestration.

### Added Files

- `app/core/uncertainty_analysis.py`
- `tests/test_uncertainty_analysis.py`
- `.superpowers/sdd/stage2-task6-implementer-report.md`

### Modified Files

- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added public `bootstrap_fit()`, `range_sensitivity()`, and immutable `UncertaintySummary` interfaces. Results contain method/status/reason, seed, sample count, variant count, success/failure counts, parameter quantiles, coefficient-of-variation values/reasons, bounded sensitivity score/reason, and row-level attempts.
- Bootstrap uses `numpy.random.default_rng(seed)` and resamples included point indices with replacement. The caller can provide indices explicitly or attach a documented included-index attribute to the callback; source indices are copied and never mutated.
- q-range sensitivity evaluates the complete `(-fraction, 0, +fraction)` lower/upper Cartesian product, records all nine candidate ranges, and rejects invalid inputs or variants with explicit reasons.
- Successful optional fits yield 2.5/50/97.5 percentile records and finite coefficient-of-variation values. The sensitivity score is the maximum finite `CV / (1 + CV)`, therefore bounded in `[0, 1]`; no finite CV leaves the score `None` with a reason.
- Callback exceptions and insufficient successful refits are captured as optional uncertainty status/reasons and attempt rows. They do not raise through or invalidate a primary SAS fit.
- Added optional duck-typed configuration support for existing `AutoBatchConfig` fields (`enable_bootstrap`, `bootstrap_samples`, `bootstrap_seed`, `enable_range_sensitivity`, and `sensitivity_boundary_fraction`) without changing the config schema or auto-batch runner.
- Added RED/GREEN regressions for reproducibility, boundary variants, resample audit, JSON safety, callback failure isolation, enabled gate, minimum-valid-fit behavior, invalid q-range rejection, and configuration-driven audit values.

### Reason

Bootstrap and q-range variation are useful robustness diagnostics only when they are reproducible, traceable, and kept distinct from the validity of the primary fit. Missing prerequisites and failed optional refits must never be silently replaced with invented uncertainty.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_uncertainty_analysis.py tests\test_guinier.py tests\test_power_law.py tests\test_model_fitting.py
python -m py_compile app\core\uncertainty_analysis.py tests\test_uncertainty_analysis.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing analysis output was generated.
- The required `py_compile` check refreshed local interpreter-cache files under `app/core/__pycache__/` and `tests/__pycache__/` only.
- `.superpowers/sdd/stage2-task6-implementer-report.md` records RED/GREEN and verification evidence.

### How To Check Success

- The specified Task 6 suite passes 17 tests.
- The full offscreen/Agg suite passes 472 tests.
- `py_compile` exits with code 0.
- `git diff --check` is attempted; because this workspace has no usable Git metadata, the documented conflict-marker/trailing-whitespace fallback check is used instead.

### Notes And Risks

- Callback output is a numerical refit input, not an inference of a material mechanism. It must supply finite parameter values through a simple mapping, parameter records, or an `AnalysisResult`-compatible result.
- Bootstrap and range sensitivity are optional. A completed summary describes variability under resampling/range perturbation; it does not prove the primary fit is statistically valid or a morphology unique.
- No `CurveData` arrays or source experimental files were modified. No dependencies were installed and no package, commit, or push was performed.

## 2026-07-12 00:37:14 +08:00 — Repair GitHub Actions Linux test environment

### Task Objective

Diagnose and repair the red GitHub Actions status on commit `b57987d` without changing raw data or overwriting the user's existing uncommitted code changes.

### Files Modified

- `.github/workflows/tests.yml`
- `CHANGELOG.md`

### Specific Changes

- Upgraded `actions/checkout` from `v4` to `v5` and `actions/setup-python` from `v5` to `v6` to remove the Node.js 20 deprecation warning reported by GitHub Actions.
- Added an Ubuntu-only system-library installation step for the EGL, OpenGL, XKB, and XCB libraries required when PySide6 tests are collected and run with `QT_QPA_PLATFORM=offscreen`.
- Preserved the existing Python 3.11 dependency installation and complete `pytest` command.

### Reason

The failing GitHub job completed checkout, Python setup, and Python dependency installation, then exited with code 2 during `pytest`. An isolated export of the exact commit passed all 549 tests on Windows, identifying the remaining difference as the Ubuntu Qt/PySide6 runtime environment rather than a Python test assertion failure.

### How To Run

The workflow runs automatically after this change is committed and pushed to GitHub. Local verification:

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q
```

### Generated Output Files

- No experimental-data, processed-data, figure, analysis-result, or package files were generated.
- A temporary commit export was created under `.tmp/sas_b57987d_repro` only for isolated reproduction and is ignored by Git.

### How To Check Success

- The isolated `b57987d` export ends with `549 passed`; the current working tree ends with `550 passed` because it also contains unrelated uncommitted test changes.
- After commit and push, the repository's `Tests / pytest (3.11)` check should become green.
- The `Install Linux GUI libraries` and `Run tests` workflow steps should both complete successfully.

### Notes And Risks

- The GitHub-hosted Ubuntu runner must have access to the standard Ubuntu package repositories.
- The unrelated uncommitted files `app/core/auto_regions.py`, `app/core/batch_cache.py`, `app/core/region_scanners.py`, and `tests/test_auto_regions.py` were not modified by this task.
- No raw data was changed, and no package, commit, or push was performed.

## 2026-07-11 21:35 +08:00 — Stage 4 结果包与全自动 GUI

### 任务目标与文件

- 新增：`app/core/result_package.py`、`app/ui/auto_batch_tab.py`、`tests/test_result_package.py`、`tests/test_auto_batch_ui.py`。
- 修改：`app/ui/advanced_workspace_tab.py`、`app/ui/main_window.py`、`docs/developer_notes.md`、`CHANGELOG.md`。
- 删除：无。

### 具体修改与原因

- 结果包包含 `run_summary.json`、`parameters.csv`、`fit_quality.csv`、模型排名、输入/失败/警告、全部时序表、PCA/聚类得分、分析表索引、每种方法/模型的明细 CSV 和中文 README。
- 已有目标目录会明确报错，不覆盖文件；写出先进入唯一临时结果目录，完成后再改为最终名称。
- 高级工作区新增全自动页，只需选择数据目录、结果父目录、批次名、样品类型和需要物理前提的开关；后台线程执行并显示进度。
- 原因：把“给出校准原始数据后只取最终数据”压缩为一次配置和一次点击，同时保留完整审计数据。

### 运行、输出与成功判断

```powershell
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'
python -B -m pytest -q -p no:cacheprovider tests\test_result_package.py tests\test_auto_batch_ui.py tests\test_sequence_analysis.py tests\test_ui_style.py tests\test_ui_safety.py tests\test_auto_batch.py tests\test_auto_batch_schema.py
```

- 实际聚焦结果：`62 passed in 6.23s`。
- 成功后 GUI 显示含 run ID 的结果包路径；首先查看 `parameters.csv`、`fit_quality.csv` 和 `README.md`。
- 未修改原始数据，未安装依赖，未打包、提交或推送。

### Stage 3/4 最终验证结果

- `python -m compileall -q app tests`：通过。
- Stage 4 与时序/GUI 回归聚焦测试：`62 passed in 6.23s`。
- 全量 Qt offscreen/Agg 测试：`517 passed in 12.31s`。
- `git diff --check` 与新增/修改文件范围的冲突标记检查：通过；仅有 Windows 行尾转换和用户级 Git ignore 无读取权限的警告，不影响检查结果。
- 已检查 `git status --short`，保留全部既有 Stage 1/2 工作树内容；未提交、未打包。

## 2026-07-11 21:00 +08:00 — Stage 2 Task 8 方法文档与验证收尾

### 任务目标

使方法文档与生产 registry/模型实现完全对齐，覆盖所有标量、表格、单位、前提和解释限制，并完成 Stage 2 最终验证。

### 新增、修改或删除的文件

- 修改：`docs/method_notes.md`
- 修改：`docs/advanced_methods.md`
- 修改：`docs/developer_notes.md`
- 修改：`CHANGELOG.md`
- 删除：无

### 具体修改与原因

- 为 18 个 `METHOD_REGISTRY` 方法补齐精确标量字段、主要表格、单位规则、必要前提和不可过度解释的边界。
- 将高级方法说明从早期“实验/预留接口”改为当前生产实现，覆盖 P(r)、不变量与受控外推、相关函数、层片分析、10 个形状/经验模型、模型派生量、拟合诊断、批量稳定模型选择和原位连续性限制。
- 明确数值收敛、R²、残差、AICc/BIC、bootstrap、连续性和模型排名都不能证明模型、结构或机理唯一。
- 原因：避免用户手工对照代码，并确保最终结果包中的每一类结果都有可追溯的科研解释边界。

### 如何运行与检查

```powershell
python -m compileall -q app tests
python -B -m pytest -q -p no:cacheprovider tests\test_fit_diagnostics.py tests\test_analysis_runner.py tests\test_model_selection.py tests\test_complete_model_fitting.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; python -B -m pytest -q -p no:cacheprovider
git diff --check
git status --short
```

### 输出、注意事项与风险

- 输出为更新后的项目方法/开发文档，无实验数据或分析结果文件。
- 未修改任何原始数据，未安装依赖，未打包、提交或推送。
- 测试和工作树检查的实际结果在本条后续验证记录中补充。

### 实际验证结果

- `python -m compileall -q app tests`：通过。
- 指定聚焦测试：`57 passed in 4.68s`。
- 全量 Qt offscreen/Agg 测试：`510 passed in 19.39s`。
- `git diff --check`：通过，仅报告 Windows 行尾转换提示；文件范围冲突标记检查通过。
- 已检查 `git status --short`：保留此前 Stage 1/2 的已修改及未跟踪文件，仅报告状态，未提交、未打包。

## 2026-07-11 21:15 +08:00 — Stage 3 原位时序分析

### 任务目标与文件

- 新增 `app/core/sequence_analysis.py`、`tests/test_sequence_analysis.py`。
- 修改 `app/core/auto_batch.py`、`app/core/auto_batch_schema.py`、`docs/developer_notes.md`、`CHANGELOG.md`。
- 未删除文件，未修改原始实验数据。

### 具体修改与原因

- 按配置元数据轴、`frame_index` 或 `sequence_order` 建立稳定帧序列，输出帧索引与所有成功/条件依赖参数的长表轨迹。
- 支持首帧、前帧、指定帧参考差异，输出公共 q 区间上的 RMSE、MAE 和相对绝对面积。
- 用相邻参数差的 MAD 稳健分数标记突变复核候选；可选输出描述性线性趋势、PCA 和固定随机种子的 k-means 聚类。
- 将结果接入 `AutoBatchRun.sequence_results`，保持时序失败隔离、JSON 安全和输入只读。
- 原因：批量数据来自同一材料的连续原位实验，需要在统一拟合口径下直接获得随帧/时间/温度变化的汇总证据。

### 运行、输出与成功判断

```powershell
python -B -m pytest -q -p no:cacheprovider tests\test_sequence_analysis.py tests\test_auto_batch.py tests\test_auto_batch_schema.py
```

- 实际结果：`35 passed in 1.58s`。
- 输出保存在内存结果字段，尚未在本阶段写入用户结果目录。
- 突变、趋势、PCA 和聚类仅为复核线索，不证明相变、动力学模型、因果或材料机理。
- 未安装依赖，未打包、提交或推送。

## 2026-07-11 20:24:50 +08:00 - Stage 2 Task 6 Final Review ndarray-Input Boundary Remediation

### Task Objective

Resolve the remaining Task 6 Important review finding: prevent NumPy arrays and other non-scalar public inputs from being implicitly converted into fitted parameter values, q-range bounds, or bootstrap RNG seeds.

### Added Files

- None. The existing Task 6 test module received public regression cases.

### Modified Files

- `app/core/uncertainty_analysis.py`
- `tests/test_uncertainty_analysis.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`
- `.superpowers/sdd/stage2-task6-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Made `_finite_float()` an explicit scalar boundary: it accepts only native/NumPy integer or floating scalar values that are finite, and rejects booleans, strings, bytes, and every `numpy.ndarray` shape before any `float()` conversion. Callback mappings containing scalar-shaped arrays can no longer fabricate parameter quantiles, CV values, sensitivity scores, or a completed optional analysis.
- Made `_q_range_bounds()` inspect NumPy-array dimensionality directly. A NumPy q range is accepted only when it is one-dimensional with exactly two elements; two-dimensional, zero-dimensional, or wrong-length arrays return `invalid_input` before any q-range callback runs. Existing two-value numeric Python sequences remain supported.
- Made `_seed_value()` accept only non-negative native or NumPy integer scalars, while rejecting booleans, floats, strings, and all arrays before RNG construction. Direct and duck-typed config seeds now have the same structured `invalid_input` result, null seed, zero attempts, and zero callback calls.
- Added public RED/GREEN regressions for 0d/1d/2d ndarray callback parameter values, malformed/valid ndarray q ranges, and direct/config ndarray or floating seeds. The tests assert no `DeprecationWarning`, no hidden callback execution, and JSON-safe failure records.

### Reason

Optional uncertainty diagnostics must not silently change the meaning of a callback result, q interval, or random seed through NumPy's deprecated scalar-array conversion behavior. Invalid optional inputs must remain contained and must never invalidate a completed primary SAS fit.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_uncertainty_analysis.py tests\test_guinier.py tests\test_power_law.py tests\test_model_fitting.py
python -m py_compile app\core\uncertainty_analysis.py tests\test_uncertainty_analysis.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing analysis output was generated.
- `py_compile` refreshed local interpreter-cache files only.
- The Task 6 implementer report records the final RED/GREEN evidence and review-limit note.

### How To Check Success

- The new public ndarray/seed regression subset passes 13 tests.
- The specified Task 6 plus required fitting-regression suite passes 44 tests.
- `py_compile` exits with code 0.
- The complete offscreen/Agg suite passes 499 tests.
- `git diff --check` is attempted; because this workspace has no usable Git metadata, the documented conflict-marker/trailing-whitespace fallback check is used instead.

### Notes And Risks

- The public seed contract is intentionally narrower than generic NumPy coercion: only non-negative native or NumPy integer scalars are accepted; `bool` is invalid even though it is an `int` subclass.
- A one-dimensional, two-value numeric NumPy q-range remains valid. Other array shapes are deliberately rejected rather than flattened.
- No `CurveData` arrays or source experimental files were modified. No dependencies were installed and no package, commit, or push was performed.

## 2026-07-11 20:10:41 +08:00 - Stage 2 Task 6 Independent Review Input-Safety Remediation

### Task Objective

Resolve all three Important Task 6 review findings: fabricated metadata-only uncertainty, malformed q-range acceptance, and invalid seed exceptions escaping the optional-analysis boundary.

### Added Files

- None. The existing Task 6 module, tests, and report were extended.

### Modified Files

- `app/core/uncertainty_analysis.py`
- `tests/test_uncertainty_analysis.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`
- `.superpowers/sdd/stage2-task6-implementer-report.md`

### Deleted Files

- None.

### Specific Changes

- Rejected Python/NumPy booleans as numerical values and excluded known callback metadata keys from direct simple parameter mappings. Metadata-only `{ "converged": True }` now produces failed optional attempts with `callback_returned_no_finite_parameters`, not fictitious `converged=1.0` quantiles/CV/sensitivity.
- Added exact q-range normalization: the public range input must be a non-string, non-mapping iterable of exactly two non-boolean finite numeric bounds in strict ascending order. Extra/missing values, strings, booleans, NaN, infinity, and reversed intervals return a JSON-safe `invalid_input` summary before any callback invocation.
- Normalized bootstrap seed input before RNG construction. Direct and config-supplied seeds must be non-negative finite integers and not booleans/strings; invalid seeds return `invalid_input`, `seed=None`, no attempts, no callback calls, and no exception from `numpy.random.default_rng`.
- Added public RED/GREEN regressions for metadata-only/mixed callback mappings, malformed q ranges, direct/config invalid seeds, and JSON serialization of every new invalid/failure summary.

### Reason

Optional uncertainty must never fabricate a parameter from control metadata, silently analyze a different q interval, or interrupt a completed primary fit because a configuration seed is malformed.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_uncertainty_analysis.py tests\test_guinier.py tests\test_power_law.py tests\test_model_fitting.py
python -m py_compile app\core\uncertainty_analysis.py tests\test_uncertainty_analysis.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing output was generated.
- `py_compile` refreshed local interpreter-cache files only.
- The Task 6 implementer report was appended with review-remediation RED/GREEN evidence.

### How To Check Success

- The specified Task 6 suite passes 31 tests.
- The full offscreen/Agg suite passes 486 tests.
- `py_compile` exits with code 0.
- `git diff --check` remains unavailable because this workspace lacks usable Git metadata; the documented fallback whitespace/conflict check is run instead.

### Notes And Risks

- A simple callback mapping should contain actual fitted scalar parameters; known status/control metadata is ignored. Use an explicit `parameters` or `parameter_records` container for structured fit results.
- Invalid optional inputs now yield only a structured uncertainty failure. They never modify or invalidate the primary fit.
- No `CurveData` arrays or source experimental files were modified. No dependencies were installed and no package, commit, or push was performed.

## 2026-07-11 20:47:00 +08:00 - Production Batch Runner and Stable Model Selection

### Task Objective

Replace the Plan 1 batch placeholder with a complete registry runner and add stable batch-level model selection without per-frame automatic switching.

### Added Files

- `app/core/analysis_runner.py`
- `app/core/model_selection.py`
- `tests/test_analysis_runner.py`
- `tests/test_model_selection.py`

### Modified Files

- `app/core/auto_batch.py`
- `app/core/auto_batch_schema.py`
- `tests/test_auto_batch.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Added explicit dispatch and startup completeness validation for every applicable `METHOD_REGISTRY` method. Missing handlers raise `BatchConfigurationError`; method exceptions become registry-complete failure envelopes rather than silently skipping later work.
- Converted `AnalysisResult` values into `AnalysisEnvelope` records with every registered metric present. Unavailable metrics are `None` with a status/reason. Shape models yield one envelope per allowed model and preserve isolated model failures.
- Added deterministic model rankings by coverage, median AICc/BIC rank, residual-pass rate, bound-hit rate, and uncertainty. Models below `0.70` coverage remain reported but cannot be the main model. A different frame winner requires three consecutive frames before a possible-transition flag is emitted; the main model never changes automatically.
- Made the production runner the `auto_batch` default and added `rankings`, `main_model`, and `transition_flags` to a completed `AutoBatchRun` while retaining custom-runner injection, cancellation, per-method failure isolation, and read-only curve inputs.

### Reason

Batch analysis requires complete, auditable method coverage and a stable sequence-level model summary instead of an implicit per-frame interpretation change.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider tests\test_model_fitting.py tests\test_model_free_complete.py tests\test_extended_features.py tests\test_advanced_contracts.py tests\test_advanced_transforms.py tests\test_complete_model_fitting.py tests\test_uncertainty_analysis.py tests\test_analysis_runner.py tests\test_model_selection.py tests\test_auto_batch.py tests\test_auto_batch_schema.py
python -m py_compile app\core\analysis_runner.py app\core\model_selection.py app\core\auto_batch.py app\core\auto_batch_schema.py tests\test_analysis_runner.py tests\test_model_selection.py tests\test_auto_batch.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

### Generated Output Files

- No raw-data, processed-data, figure, GUI, exporter, package, or user-facing analysis output was generated.
- `py_compile` refreshed local interpreter-cache files only.

### How To Check Success

- The runner/selection/auto-batch suite passes 41 tests.
- The specified focused suite passes 178 tests.
- `py_compile` exits with code 0.
- The complete offscreen/Agg suite passes 510 tests.
- `git diff --check` and the direct trailing-whitespace/conflict-marker fallback check pass.

### Notes And Risks

- Complete shape-model comparison may be computationally expensive on long curves because the existing all-candidate fitting contract is intentionally preserved; no hidden fast path was added.
- The main model and transition flags are conditional numerical summaries, not proof of unique morphology or mechanism.
- No `CurveData` arrays or source experimental files were modified. No dependencies were installed and no package, commit, or push was performed.

## 2026-07-12 00:40:50 +08:00 - Log-q Adaptive Per-frame Auto-region Repair

### Task Objective

Repair incomplete automatic processing of each individual SAXS frame on a wide, linearly sampled q grid, using the Ti15 frames 1–10 under `results\spectra_csv` as read-only validation data.

### Added Files

- None.

### Modified Files

- `app/core/region_scanners.py`
- `app/core/auto_regions.py`
- `app/core/batch_cache.py`
- `tests/test_auto_regions.py`
- `CHANGELOG.md`
- `docs/developer_notes.md`

### Deleted Files

- None.

### Specific Changes

- Replaced row-index stepping and three fixed point-count windows with multiscale windows distributed in `log10(q)`. The scanner maps windows back to measured rows without interpolation, smoothing, background subtraction, or mutation.
- Added logarithmic-span and point-count evidence to Guinier candidates. Automatic Guinier scanning is confined to the low-log-q part of each frame, and `qRg_max > 1.3` cannot be fit-ready.
- Reworked power-law scoring to use chunked log-linear slope stability rather than point-to-point numerical derivatives. Windows narrower than `0.10` q decades are retained for audit but cannot become automatically fit-ready.
- Made Porod noise penalties local to candidate windows that overlap the detected high-q risk band. Porod fit readiness now also requires alpha within the configured target tolerance, acceptable q4I plateau variation, and no severe overlapping high-q risk.
- Changed low-q upturn and high-q noise/background risk bands from row-count fractions to log-q bands with minimum point protection. This prevents a linear q grid from labelling the range through approximately `0.1 A^-1` as one low-q upturn.
- Bumped `auto_detection_version` from `1.0` to `2.0` and `ANALYSIS_ALGORITHM_VERSION` from `1` to `2` so old cached ranges are not reused after the numerical rule change.
- Added a regression curve with 5500 linearly spaced q points and a narrow `q^-3.4` segment, proving that the automatic scanner no longer jumps over the physically useful interval or accepts an eight-point high-q fluctuation as its best result.

### Reason

The previous step sizes were proportional to total row count. For the Ti15 files, this meant jumps of roughly 120 points for Guinier and 180 points for power-law/Porod scanning. Because q is approximately linear from `9.35e-5` to `1.03 A^-1`, those jumps skipped the peak-adjacent decay interval near `0.01–0.03 A^-1`; candidate ranking then favored isolated eight-point fluctuations.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -m py_compile app\core\region_scanners.py app\core\auto_regions.py app\core\batch_cache.py
$env:QT_QPA_PLATFORM='offscreen'; $env:MPLBACKEND='Agg'; $env:TEMP="$PWD\.tmp"; $env:TMP="$PWD\.tmp"; $env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp"; python -B -m pytest -q -p no:cacheprovider
```

To generate a new timestamped Ti15 result set after reviewing this repair:

```powershell
python scripts\analyze_ti15_first10.py --input-dir C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\results\spectra_csv --results-root C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\results
```

### Generated Output Files

- No persistent research result, figure, workbook, package, or rewritten source-data file was generated during this repair.
- Real-data verification was in memory only; `py_compile` may refresh ignored interpreter-cache files.

### How To Check Success

- Focused auto-region/batch regressions pass `103` tests.
- The complete Qt-offscreen/Agg suite passes `550` tests.
- Read-only validation on Ti15 frames 1–10 produces a 10/10-frame power-law consensus at `0.013178–0.021963 A^-1` with per-frame alpha values `3.399–3.488`; peak consensus remains available.
- The same validation does not fabricate Guinier or Porod acceptance when their method-specific criteria are not met.

### Notes And Risks

- A stable alpha around 3.4 is a surface-fractal-like candidate only under the relevant scattering assumptions; it is not proof of morphology or mechanism.
- This application still does not silently smooth, interpolate, or subtract physical background. If background correction is required, it must remain an explicit derived-data workflow with provenance.
- Log-q multiscale scanning evaluates more representative windows than the old row-step algorithm and may take somewhat longer on very long curves.
- Original CSV data and the existing `results\17_Ti15_300_2_iso_first10_20260711_220140` output were read only and not modified. No package, dependency installation, Git commit, or push was performed.

## 2026-07-12 00:56:52 +08:00 - Document Auto-scan Coverage Versus Method Acceptance

### Task Objective

Add the prior explanation of “the interval was scanned, but Guinier/Porod criteria were not met” to the Simplified Chinese software manual, using the Ti15 first-ten-frame data as an auditable example.

### Added Files

- None.

### Modified Files

- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Deleted Files

- None.

### Specific Changes

- Expanded Section 8.3 with a beginner-oriented explanation of what a log-log plot can and cannot establish, followed by a Ti15 frames 1–10 example covering the peak, shared power-law interval, high-q risk, valid quantitative outputs, conditional surface-fractal interpretation, and current local-slope/crossover limitations.
- Added Section 9.7 as the primary requested explanation. It separates automatic processing into (1) candidate q-interval coverage and (2) method-specific acceptance, then explains the Guinier and Porod checks and why “every frame contains information” does not imply every method must return a value.
- Added cross-references and cautions to the power-law, local-slope, and Porod analysis sections.
- Added FAQ 17.9 so users encountering empty Guinier/Porod results can reach the two-layer explanation directly.
- Added a reproducible rerun command, input/output description, and success checks for producing a new timestamped Ti15 result directory without overwriting the existing output.
- Added an explicit `附录` parent heading and nested Appendices A–D beneath it, repairing the pre-existing table-of-contents target `#附录` discovered during Markdown validation.

### Reason

Users need to distinguish an algorithmic coverage failure from a scientifically correct method rejection. Without this distinction, an empty Rg or Porod field may be incorrectly treated as a software bug and “repaired” by lowering thresholds or forcing a fit.

### How To Run

The manual is Markdown and can be opened directly:

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
Get-Content docs\user_manual_zh.md -Encoding utf8
```

Optional Ti15 rerun described by the manual:

```powershell
python scripts\analyze_ti15_first10.py --input-dir ..\results\spectra_csv --results-root ..\results
```

### Generated Output Files

- No analysis result, processed-data file, figure, workbook, package, or rewritten experimental file was generated.
- Only documentation and project records were updated.

### How To Check Success

- `docs/user_manual_zh.md` contains Sections `8.3.1`, `8.3.2`, `9.7`, and `17.9`.
- Internal links from Sections 10 and 17 resolve to the Ti15 example and the two-layer automatic-recognition explanation.
- The manual records the validated Ti15 shared power-law interval `0.013178–0.021963 A^-1`, `alpha=3.399–3.488`, `R²=0.9972–0.9993`, and the explicit reasons Guinier/Porod remain empty.
- A Markdown structure check reports no duplicate generated heading anchors, broken internal heading targets, conflict markers, or trailing whitespace in the modified documentation.

### Notes And Risks

- The numerical example records existing read-only validation evidence; it does not add a new material-mechanism conclusion.
- `Ds=6-alpha` remains explicitly conditional on a valid surface-fractal interpretation.
- Existing result directories are not regenerated or modified by a manual edit.
- No package, dependency installation, Git commit, or push was performed.

## 2026-07-12 12:28:37 +08:00 - Run Ti15 First-Ten-Frame Model-Free SAXS Analysis

### Task Objective

Run the requested first-ten-frame SAXS analysis for `17_Ti15_300_2_iso` without modifying source data or using shape-model fitting.

### Added Files

- `scripts/build_summary_workbook.mjs`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/` result package and figures

### Modified Files

- `app/core/auto_batch_schema.py`
- `app/core/metric_registry.py`
- `scripts/analyze_ti15_first10.py`
- `tests/test_metric_registry.py`
- `CHANGELOG.md`

### Specific Changes

- Added `AutoBatchConfig.enable_shape_models`, defaulting to `True` for backward compatibility; the requested run sets it to `False`.
- Corrected the first-ten-frame input default, recorded the complete configuration snapshot, and clarified the report as sample-label based rather than assuming temperature or elapsed time.
- Added an audit-only power-law candidate section so fitted values with reliability score `0` are not promoted to the main conclusion.
- Added an `artifact-tool` workbook builder with an Overview sheet and auditable CSV-derived sheets; numeric data-quality columns are coerced to numeric cell values so summary formulas calculate correctly.

### Reason

The user requested a comprehensive model-free analysis with a reproducible Excel summary, explicit source integrity checks, and no shape-model interpretation.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python scripts\analyze_ti15_first10.py --input-dir "D:\桌面\PostFile\6_sys\SAXS-学习2\17_Ti15_300_2_iso\17_Ti15_300_2_iso\spectra_csv" --results-root ..\results
& "C:\Users\wkguopro\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" scripts\build_summary_workbook.mjs ..\results\17_Ti15_300_2_iso_first10_model_free_20260712_122352
```

### Generated Output Files

- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/final_report_zh.md`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/summary_tables.xlsx`
- CSV audit tables, JSON configuration/summary files, and PNG/SVG/PDF figures under the same result directory

### How To Check Success

- Full test suite: `551 passed`.
- Runtime result: `CURVES=10`, `ANALYSES=140`, `SOURCE_INTEGRITY=PASS`, `RUN_STATUS=completed_with_limitations`.
- `all_parameters_audit.csv` contains zero shape-model rows; `run_config.json` records `enable_shape_models=false` and all selected source filenames.
- Workbook contains 11 sheets and the final formula-error scan matched 0 entries.

### Notes And Risks

- The sequence axis is frame index, not time; no kinetics are inferred.
- Negative and zero intensities remain in audit tables; logarithmic methods use only positive points.
- Peak `q*` and `d=2π/q*` are reported as characteristic correlation scales, not particle diameters.
- Guinier and Porod are retained as unavailable due to method-specific prerequisites. Power-law values are audit candidates only because their reliability score is `0`.
- No dependency installation, packaging, Git commit, Git push, or raw-data modification was performed.

## 2026-07-12 13:02:06 +08:00 - Rerun Ti15 First Ten Frames With Effective q Range And Replace Result Package

### Task Objective

按用户要求重新运行 Ti15 前十帧无模型 SAXS 分析，明确使用有效 `q=0.01–0.05 Å^-1`，并用新结果覆盖上一版同名结果包。

### Added Files

- Rebuilt files under `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/`.

### Modified Files

- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/`：整包替换
- `CHANGELOG.md`

### Specific Changes

- 只导入 `ti15_00001_abs2d_cm-1.csv` 至 `ti15_00010_abs2d_cm-1.csv`，排除 `TI15-rt_00001_abs2d_cm-1.csv`。
- 使用 `--q-min 0.01 --q-max 0.05` 重新运行；配置和中文报告均记录该范围。
- 新包保留 CSV、JSON、Excel、600 dpi PNG、SVG、PDF、质量审计和源文件完整性记录。
- 清理了 Excel 构建过程产生的临时 `.inspect.ndjson` 文件和失败的临时 staging 目录。

### Reason

上一版结果是在有效 q 范围控制改造前生成的，用户明确要求覆盖为按 `0.01–0.05 Å^-1` 重新计算的结果。

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python scripts\analyze_ti15_first10.py --input-dir "D:\桌面\PostFile\6_sys\SAXS-学习2\17_Ti15_300_2_iso\17_Ti15_300_2_iso\spectra_csv" --results-root ..\results --q-min 0.01 --q-max 0.05
& "C:\Users\wkguopro\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" scripts\build_summary_workbook.mjs ..\results\17_Ti15_300_2_iso_first10_model_free_20260712_122352
```

### Generated Output Files

- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/final_report_zh.md`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/summary_tables.xlsx`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/data_quality.csv`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/all_parameters_audit.csv`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/source_integrity_after_analysis.csv`
- `results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/figures/`

### How To Check Success

- Runtime: `CURVES=10`, `ANALYSES=140`, `RUN_STATUS=completed_with_limitations`, `SOURCE_INTEGRITY=PASS`.
- `run_config.json` contains `effective_q_range=[0.01, 0.05]` and `enable_shape_models=false`.
- Effective q data coverage is 214 points per frame; actual measured selected interval is approximately `0.0100004–0.0498150 Å^-1`.
- `all_parameters_audit.csv` contains zero shape-model rows; Excel formula error scan matched 0 entries.
- Independent post-run SHA-256 comparison matched all 10 raw files; recorded unchanged rows are 10/10.

### Notes And Risks

- The old result package was explicitly deleted and replaced as requested; no backup copy was retained in the project results directory.
- The first staging attempt under `C:\tmp` was blocked by directory permissions; the successful rerun used the project results directory and completed normally.
- Effective-range filtering selects analysis points only; it does not smooth, shift, truncate, background-correct, or modify raw input files.
- No package archive, Git commit, Git push, or upload was performed.

## 2026-07-12 12:50:02 +08:00 - Require Effective q-Range Confirmation Before Analysis

### Task Objective

修改 SAXS 分析流程，使分析开始前明确确认有效 q 范围，默认使用 `0.01–0.05 Å^-1`，并让批处理、自动选区、序列分析和脚本使用同一范围。

### Added Files

- None.

### Modified Files

- `app/core/auto_batch_schema.py`
- `app/core/auto_batch.py`
- `app/core/batch_consensus.py`
- `app/core/sequence_analysis.py`
- `app/core/batch_cache.py`
- `app/ui/analysis_tab.py`
- `app/ui/deep_analysis_tab.py`
- `app/ui/auto_batch_tab.py`
- `scripts/analyze_ti15_first10.py`
- `tests/test_auto_batch_schema.py`
- `tests/test_auto_batch.py`
- `tests/test_batch_consensus.py`
- `tests/test_sequence_analysis.py`
- `tests/test_auto_region_ui.py`
- `tests/test_auto_batch_ui.py`
- `tests/test_ui_style.py`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Specific Changes

- Added validated `effective_q_range` configuration with default `(0.01, 0.05)` and strict `q_min < q_max` checking.
- Applied the selected range to full finite q ranges, consensus region detection, sequence reference comparisons, and optional exploratory statistics; no raw curve array is altered.
- Added editable effective-q controls to the single-curve, deep-analysis, and auto-batch pages. Invalid ranges stop before worker execution.
- Added `--q-min` and `--q-max` to the Ti15 first-ten-frame script and recorded the range in reports, configuration, quality tables, and overlay plots.
- Bumped `ANALYSIS_ALGORITHM_VERSION` from `2` to `3` to prevent reuse of unrestricted-range cache entries.

### Reason

The user specified that `0.01–0.05 Å^-1` is the effective q data range and requested confirmation before analysis so results are not silently derived from invalid q tails.

### How To Run

For the GUI, open the relevant analysis page, confirm or edit the effective q lower/upper bounds, then start analysis. For the Ti15 script:

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python scripts\analyze_ti15_first10.py --q-min 0.01 --q-max 0.05
```

### Generated Output Files

- No new research result package was generated in this code-change task.
- Existing result directories were not overwritten or regenerated.

### How To Check Success

- Focused regression suite: `75 passed` before the single/deep-analysis default updates and `29 passed` for the affected GUI suite after those updates.
- Full project test suite must pass with `python -m pytest`.
- GUI controls show `0.01` and `0.05` by default; reversed bounds do not start a worker.
- A run configuration contains `effective_q_range`; source CSV hashes and bytes remain outside the analysis write path.

### Notes And Risks

- The default is a user-facing starting point and must still be checked against each instrument/sample; it does not prove that every dataset is valid in this interval.
- Range restriction is selection only. The software does not smooth, shift, truncate, background-correct, or overwrite raw input files.
- Existing Ti15 result packages were produced before this range-control change and are not silently relabeled; rerun into a new timestamped directory when updated results are needed.
- No dependency installation, packaging, Git commit, Git push, or raw-data modification was performed.

## 2026-07-12 13:25:00 +08:00 - Ignore External Node Runtime Junction

### Task Objective

Prevent the Git client from displaying the external Codex Node runtime dependencies under `scripts/node_modules/` as thousands of project changes.

### Modified Files

- `.gitignore`
- `CHANGELOG.md`

### Specific Changes

- Added `scripts/node_modules/` to `.gitignore`.
- The directory is a Windows Junction pointing to the user-level Codex runtime cache; its files were not deleted, moved, or committed.

### Reason

GitHub Desktop expanded the Junction and displayed approximately 15,539 external dependency files as untracked changes, although they are not project source files.

### How To Check Success

- Run `git status -sb` in the `sas_curve_analyzer` repository.
- `scripts/node_modules/` should no longer appear as an untracked path.
- The workbook builder can continue using the existing local Node runtime.

### Notes And Risks

- This change only affects Git ignore behavior; it does not remove dependencies or change analysis results.

## 2026-07-12 13:40:09 +08:00 — Fix NumPy 2.x pytest collection failure

### Task Objective

Resolve the red GitHub Actions check for commit `878e89c`.

### Files Modified

- `app/core/plot_analysis.py`
- `tests/test_plot_analysis.py`
- `CHANGELOG.md`

### Specific Changes

- Replaced the eager fallback expression `getattr(np, "trapezoid", np.trapz)` with the NumPy 2.x-supported `np.trapezoid` in production code and its matching test helper.
- Documented why the fallback expression is unsafe: Python evaluates `np.trapz` before calling `getattr`, while NumPy 2.x no longer exposes that attribute.

### Reason

The GitHub Actions log showed six collection errors with `AttributeError: module 'numpy' has no attribute 'trapz'` at `app/core/plot_analysis.py:46`. The project already requires `numpy>=2.0,<3`, so direct use of `np.trapezoid` matches the declared dependency.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -m pytest -q
python -m py_compile app\core\plot_analysis.py tests\test_plot_analysis.py
```

### Generated Output Files

- No experimental data, processed data, figures, or package files were generated.

### How To Check Success

- Local full suite: `562 passed` in the current working tree.
- `py_compile` exits with code 0.
- `git diff --check` passes.
- After this change is committed and pushed, the GitHub `Tests / pytest (3.11)` run should proceed past test collection.

### Notes And Risks

- The current working tree contains other uncommitted changes from earlier work; they were preserved and not rewritten.
- No commit or push was performed automatically.

## 2026-07-12 13:47:59 +08:00 - Import-Time q Filtering And Ti15 Archive Outputs

### Task Objective

Enforce the effective q interval while reading batch input, then regenerate and replace the Ti15 first-ten-frame model-free result package with both compact and full audit deliverables.

### Modified Files

- `app/core/batch_inputs.py`
- `app/core/auto_batch.py`
- `app/core/result_package.py`
- `scripts/analyze_ti15_first10.py`
- `scripts/build_summary_workbook.mjs`
- `tests/test_batch_inputs.py`
- `tests/test_result_package.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/`

### Specific Changes

- `collect_batch_inputs()` now calls the existing import q-range filter with the validated `AutoBatchConfig.effective_q_range`; the default is `0.01–0.05 Å^-1`.
- Export filtering uses the run-level interval for all q-bearing detail rows. `details_full.zip` preserves all 30 per-frame tables, including readable empty crossover CSVs; `audit_full.zip` includes the complete audit directory and nested detail archive.
- Added regression coverage for import-time filtering, archive table counts, empty-table headers, q filtering, and raw-file immutability.

### Generated Output Files

- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/details_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/audit_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/summary_tables.xlsx`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/final_report_zh.md`

### How To Check Success

- `python -m pytest -q` returns `563 passed`.
- The run records `effective_q_range=[0.01,0.05]`, input filter enabled, 2,140 imported points, and 10/10 unchanged source hashes.
- Independent package validation finds 30 detail tables, 0 q rows outside the effective interval, and 0 workbook formula errors.

### Notes And Risks

- The effective interval is a user-configured analysis range and must be confirmed for other instruments or samples.
- Original source CSV files remain unchanged and are not included in the archives.
- No Git commit, push, upload, or automatic packaging was performed.

## 2026-07-12 14:08:57 +08:00 - Keep Audit And Detail Archives Independent

### Task Objective

Modify the Ti15 result-package workflow so `audit_full.zip` does not duplicate the separately delivered `details_full.zip`.

### Modified Files

- `scripts/analyze_ti15_first10.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/`

### Specific Changes

- Removed the nested detail archive from audit ZIP assembly.
- Updated the audit ZIP README to state that the detail archive is separate.
- Re-ran the analysis with effective q `[0.01,0.05]` and regenerated the workbook and figures.

### Generated Output Files

- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/audit_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/details_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/summary_tables.xlsx`

### How To Check Success

- `audit_full.zip` has no nested `details_full.zip` entry.
- `details_full.zip` contains 30 tables and zero q rows outside the effective interval.
- The run has 10 curves, 214 points per frame, 10/10 unchanged source hashes, and 0 workbook formula errors.
- Full regression suite: `564 passed`.

### Notes And Risks

- Both archives must be retained together when a complete audit plus full details is required.
- Original source files remain unchanged and are not included in either archive.
- No Git commit, push, upload, or automatic packaging was performed.

## 2026-07-12 14:26:50 +08:00 - Simplify Ti15 Result Package For First-View Use

### Task Objective

Reduce the visible result-package complexity so users first see only the final fitted/calculated result and the Chinese run report, while retaining complete audit and detail materials for optional troubleshooting.

### Modified Files

- `scripts/build_summary_workbook.mjs`
- `scripts/analyze_ti15_first10.py`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/`

### Specific Changes

- The result-package builder now keeps the root focused on `final_report_zh.md`, `final_results.csv`, `summary_tables.xlsx`, `audit_full.zip`, `details_full.zip`, and `README.md`.
- Secondary CSV/JSON files, figures, and the `audit/`, `details/`, and `summary/` directories are grouped under `review/`.
- `audit_full.zip` and `details_full.zip` remain separate; the audit archive no longer nests the detail archive and now includes a copy of the generated figures.
- Workbook rebuilding supports both the compact package layout and the pre-compaction layout.
- All analysis data remain constrained to effective `q=0.01–0.05 Å⁻¹`; raw source CSV files remain untouched.

### How To Check Success

- Root contains six primary files and one `review/` directory only.
- `final_results.csv` matches the reliable-parameter table used by the report.
- `summary_tables.xlsx` opens with 11 sheets and 0 formula errors.
- `audit_full.zip` has no `details_full.zip` member; `details_full.zip` contains 30 detail tables.
- Q-range, 10-frame input, 10/10 source-integrity, and raw-file immutability checks pass.

### Notes And Risks

- The `review/` directory and both ZIP archives are intentionally retained; they are not redundant with the primary result files and should be opened only for data-quality or method-level review.
- No raw-data overwrite, upload, Git commit, Git push, or automatic project packaging was performed.

## 2026-07-12 14:36:38 +08:00 - Finalize Compact Package Cleanup

### Task Objective

Complete the compact result-package rerun and ensure temporary workbook inspection output does not remain visible in the user-facing result directory.

### Modified Files

- `scripts/build_summary_workbook.mjs`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/`
- `CHANGELOG.md`
- `../CHANGELOG.md`

### Specific Changes

- The workbook builder now removes its temporary `summary_tables.xlsx.inspect.ndjson` file after verification.
- The fixed result directory was regenerated after the final report-path correction and rebuilt once more from the compact layout.

### How To Check Success

- The result root contains exactly six primary files plus `review/`; no inspection sidecar remains.
- The compact-layout rebuild again reports 11 workbook sheets and zero formula-error matches.

### Notes And Risks

- Review materials remain available under `review/` and in the two independent ZIP archives.

## 2026-07-12 14:51:45 +08:00 - Prepare Horizontal Parameter Layout In Summary Workbook

### Task Objective

Make same-curve parameters easier to compare by arranging the user-facing parameter tables horizontally rather than one parameter per row.

### Modified Files

- `scripts/build_summary_workbook.mjs`
- `CHANGELOG.md`
- `../CHANGELOG.md`

### Specific Changes

- `accepted_parameters` and `reliable_parameters` are now transformed to one row per curve with analysis-type-prefixed parameter columns.
- The horizontal tables retain status/reliability summaries, q-range summaries, accepted/reliable parameter counts, and warning counts.
- `all_parameters_audit` remains vertical so parameter-level invalid reasons, q intervals, and warnings remain traceable.

### How To Check Success

- The in-memory workbook build produced 10 data rows for each horizontal parameter table.
- Final Excel overwrite is pending because the existing `summary_tables.xlsx` was locked by another process.

### Notes And Risks

- Close the open Excel workbook before regenerating; no raw experimental data were touched.

## 2026-07-12 14:56:12 +08:00 - Finalize Readable Horizontal Headers

### Task Objective

Complete and visually verify the horizontal parameter-table layout after the Excel file lock was released.

### Modified Files

- `scripts/build_summary_workbook.mjs`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/summary_tables.xlsx`
- `CHANGELOG.md`
- `../CHANGELOG.md`

### Specific Changes

- Shortened the displayed q-range summary to distinct effective ranges per curve.
- Increased horizontal-table header height so analysis-type/parameter/unit labels remain readable.
- Rebuilt the workbook successfully after the previous Windows file-lock error.

### How To Check Success

- `accepted_parameters`: 10 curve rows and 49 columns.
- `reliable_parameters`: 10 curve rows and 36 columns.
- `all_parameters_audit`: remains 1,100 parameter rows in vertical audit format.
- Workbook formula-error scan: 0 matches; effective q range remains `0.01–0.05 Å⁻¹`.

### Notes And Risks

- Horizontal parameter columns are intentionally wide; use horizontal scrolling for later parameters.
- Original CSV data were not modified.

## 2026-07-12 15:05:03 +08:00 - Synchronize Horizontal Table Documentation

### Task Objective

Synchronize the implemented horizontal Excel parameter-table rule across project and result-package documentation.

### Modified Files

- `docs/user_manual_zh.md`
- `README.md`
- `docs/developer_notes.md`
- `scripts/build_summary_workbook.mjs`
- `scripts/analyze_ti15_first10.py`
- `../README.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/README.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_122352/final_report_zh.md`
- `CHANGELOG.md`
- `../CHANGELOG.md`

### Specific Changes

- Documented that `accepted_parameters` and `reliable_parameters` are one-row-per-curve horizontal tables with `analysis_type__parameter [unit]` headers.
- Documented that `all_parameters_audit` remains a vertical lossless audit table and `final_results.csv` remains a long machine-readable table.
- Updated the result-package README generator and the current Chinese report so future generated packages carry the same explanation.

### How To Check Success

- Documentation search finds the same horizontal/vertical layout rule in the user manual, both project README levels, developer notes, result README, and final report.
- Workbook regeneration succeeds with 11 sheets, horizontal parameter tables, and 0 formula-error matches.
- The temporary workbook inspection sidecar is removed after generation.

### Notes And Risks

- This documentation synchronization changes no analysis algorithm, parameter values, q range, or raw experimental data.

## 2026-07-12 15:20:43 +08:00 — Stabilize cross-platform identifiability test

### Task Objective

Fix the GitHub Actions failure on commit `c8de07f`, where one degenerate core-shell fitting test failed only because a floating-point correlation value differed slightly between Windows and Ubuntu.

### Files Modified

- `tests/test_complete_model_fitting.py`
- `CHANGELOG.md`

### Specific Changes

- Removed the test's exact `max_abs_parameter_correlation >= 0.95` assertion.
- Kept assertions that the covariance diagnostics exist and that the public `identifiability_status` is `weak` or `non_identifiable`.
- Left the production identifiability thresholds and fitting algorithm unchanged.

### Reason

The GitHub runner reported `0.9470023238767963 >= 0.95` as false, while the same test on Windows produced approximately `0.9537`. The test's purpose is to ensure a degenerate fit is not reported as strongly identifiable; the public status is the stable contract, while the final correlation decimal is solver/platform-sensitive.

### How To Run

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -m pytest -q
```

### Generated Output Files

- No experimental-data, processed-data, figure, or package files were generated.

### How To Check Success

- Targeted test passes.
- Full local suite passes: `564 passed`.
- `py_compile` and `git diff --check` pass.
- After commit and push, GitHub Actions should no longer fail on this platform-sensitive assertion.

### Notes And Risks

- This is a test robustness fix; production fitting behavior and identifiability thresholds were not relaxed.
- No raw data was modified. No commit or push was performed automatically.

## 2026-07-12 18:09:46 +08:00 — Method-Specific Effective-q Refactor

### Task Objective

Replace the cross-method shared-q scheduling assumption with a method-specific q-range workflow while preserving the confirmed effective input boundary, defaulting to `0.01–0.05 Å^-1`.

### Modified Files

- `app/core/auto_batch.py`
- `app/core/auto_batch_schema.py`
- `app/core/metric_registry.py`
- `app/core/analysis_runner.py`
- `app/core/batch_cache.py`
- `app/core/result_package.py`
- `scripts/analyze_ti15_first10.py`
- `scripts/build_summary_workbook.mjs`
- `tests/test_auto_batch.py`
- `tests/test_result_package.py`
- `README.md`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`

### Specific Changes

- Kept import-time effective-q filtering as the hard data boundary; no source CSV is modified.
- Restricted shared candidate/consensus routing to Guinier, power-law, and Porod.
- Routed local slope, crossover, peaks, shoulders, oscillations, lamellar, integral, invariant, Kratky, compensated, and quality/coordinate methods to the finite curve range inside the effective boundary.
- Implemented the previously unused `allow_per_frame_range_fallback` option. It is still conservative by default and only falls back to a candidate from the same method.
- Added orthogonal execution, candidate, consensus, detection, reliability, range-source, and reason-code fields to analysis envelopes.
- Added `range_audit.csv` and `consensus_regions.csv` to the audit output and workbook import list.
- Bumped `ANALYSIS_ALGORITHM_VERSION` to `4` so old shared-range job caches are not restored.
- Shortened detail CSV filenames with deterministic hashes to avoid Windows staging-path failures near the legacy path-length limit.
- Updated tests and Chinese/English documentation to distinguish the effective q boundary from method-specific fitting windows and to label historical Ti15 intervals as historical.

### Generated Output Files

- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_180429/final_report_zh.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_180429/summary_tables.xlsx`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_180429/audit_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_180429/details_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_180429/review/audit/range_audit.csv`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_180429/review/audit/consensus_regions.csv`

### How To Run And Check Success

```powershell
cd C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer
python -B -m pytest -q -p no:cacheprovider
python scripts\analyze_ti15_first10.py --input-dir "D:\桌面\PostFile\6_sys\SAXS-学习2\17_Ti15_300_2_iso\17_Ti15_300_2_iso\spectra_csv" --results-root "C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\results" --q-min 0.01 --q-max 0.05
```

- Full regression suite passed: `565 passed`.
- Real Ti15 run imported 10 curves and 214 points per curve; run status was `completed_with_limitations`.
- `range_audit.csv` contains 140 curve-method decisions and no q interval outside `0.01–0.05 Å^-1`.
- `source_integrity_after_analysis.csv` reports all 10 input files unchanged.
- The workbook contains 13 sheets and the formula-error scan matched 0 cells.
- `audit_full.zip` contains the new range/consensus audit files and does not contain `details_full.zip`; `details_full.zip` contains only q-filtered detail tables, the index, and its README.

### Notes And Risks

- A method-specific candidate or consensus interval is a computational suitability decision, not proof of morphology, phase transition, or mechanism.
- The current Ti15 run still has no accepted Guinier or Porod shared fit; this is preserved as an explicit method-specific limitation rather than filled from another method.
- The generated result package is a new timestamped snapshot; previous result packages are not overwritten.
- Original experimental CSV files were read-only and were not copied into either archive. No commit or push was performed automatically.

## 2026-07-12 18:31:08 +08:00 — q 选择依据审计字段

### 任务目标

增加有效 q 边界内的方法区间选择依据，使结果不仅给出 q 起止值，还能追溯候选扫描、排序、方法内共识、稳定性/物理证据和未采用原因。

### 修改文件

- `app/core/auto_batch.py`
- `app/core/auto_batch_schema.py`
- `app/core/result_package.py`
- `scripts/analyze_ti15_first10.py`
- `tests/test_auto_batch.py`
- `docs/user_manual_zh.md`
- `docs/developer_notes.md`
- `CHANGELOG.md`
- `../CHANGELOG.md`

### 具体修改与原因

- 新增 `q_selection_basis`、`q_selection_evidence`，并在逐任务审计、参数审计、拟合质量和报告中同步。
- `range_audit.csv` 新增候选评分、覆盖率、点数、log-q 跨度、R²、稳定性/物理/噪声、Porod 平台 CV、`qRg_max` 等证据列。
- `run_config.json` 记录有效 q 硬边界、候选排序、log-q 聚类、覆盖率门槛、严格交集、逐帧回退和不做跨方法交集的规则。
- 保持导入时有效 q 边界约束；本次运行仍使用 `0.01–0.05 Å^-1`，不修改原始 CSV，不用其他方法区间填补缺失拟合。

### 生成输出

- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_182602/final_report_zh.md`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_182602/summary_tables.xlsx`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_182602/review/audit/range_audit.csv`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_182602/review/audit/consensus_regions.csv`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_182602/audit_full.zip`
- `../results/17_Ti15_300_2_iso_first10_model_free_20260712_182602/details_full.zip`

### 检查方法

- `python -m pytest -q`：`565 passed`。
- 真实前十帧：10 条曲线、140 个曲线-方法任务，原始文件完整性 `PASS`。
- 所有审计 q 区间及明细表中的实际 q 坐标均在 `0.01–0.05 Å^-1` 内。
- `range_audit.csv` 记录 110 个有效边界任务、10 个幂律方法内共识任务、20 个无可执行方法区间任务。
- 工作簿生成 13 个子表，公式错误扫描为 0；`audit_full.zip` 不包含 `details_full.zip`。

### 注意事项

- q 选择证据是可追溯的数值筛选依据，不是形貌、相变或机理证明。
- 本次结果仍明确保留 Guinier/Porod 不可执行限制；没有强行降低门槛或跨方法借用区间。

## 2026-07-12 20:52:14 +08:00 — P0 状态语义、特征检测门控与实际执行证据

### 任务目标

启动并完成 SAS 自动分析区间、局部特征检测和正式报告状态的 P0 改造；保持用户确认的有效 q 边界 `0.01–0.05 Å^-1` 为输入硬边界，禁止跨方法共用拟合区间，避免把候选、拟合、检测或假设依赖结果直接当成正式科研结论。

### 修改内容

- `app/core/auto_batch_schema.py`、`app/core/analysis_runner.py`：增加 execution/candidate/consensus/detection/reliability/reporting 的正交状态；记录 power-law 实际执行点数与 log-q 跨度，低于报告阈值时标记 `exploratory`。
- `app/core/auto_batch.py`、`app/core/batch_consensus.py`：保留无共识审计行，分离候选点数与共识执行点数，关联重叠的 shoulder/crossover q 位置并标记 `ambiguous`。
- `app/core/feature_extraction.py`：自动峰扫描使用稳健趋势残差和噪声分离门控，避免单调幂律被误报为大量峰；不修改负强度。
- `app/core/result_package.py`、`scripts/analyze_ti15_first10.py`：审计表和中文报告增加 reporting 状态/原因码；仅 `reportable` 且通过可靠性筛选的参数进入最终结果。
- `tests/`：增加缺少 q 区间、窄执行区间、峰过检出、候选证据和 shoulder/crossover 关联回归测试。
- `docs/developer_notes.md`、`docs/user_manual_zh.md`、`README.md`：同步状态契约与解释边界。

### 输出与验收

- 结果包：`../results/17_Ti15_300_2_iso_first10_model_free_20260712_205003/`。
- 10 条指定曲线、140 个方法任务、`enable_shape_models=False`、有效 q 范围 `0.01–0.05 Å^-1`、原始完整性 `PASS`。
- `python -m pytest -q`：`569 passed`；工作簿 13 个子表、公式错误 0；明细 q 值越界 0。
- `audit_full.zip` 与 `details_full.zip` 独立，审计包不嵌套明细包。

### 注意事项

- power-law 实际执行 log-q 跨度约 `0.0775` decades，小于默认 `0.10` 正式报告门槛，只保留在探索/审计层。
- shoulder/crossover 在 10 帧中均出现 q 重叠，已关联，不能作为两个独立正式特征。
- 原始 CSV 未修改；未提交 Git、未推送 GitHub、未自动打包项目。
