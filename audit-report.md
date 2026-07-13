# sas_curve_analyzer 审计报告（Goal Mode / full）

- **日期**: 2026-07-13  
- **项目路径**: `C:\Users\wkguopro\Documents\Codex\Codex_SAScalcu\sas_curve_analyzer`  
- **模式**: full  
- **HEAD**: `c51820edbd65b0d7362b39cda14e5755c5816828` — *Implement P0 SAXS analysis state and q-range gates*  
- **基准**: `base_ref=auto` → 与 `origin/main` 的 merge-base 即为 HEAD；审计对象为 **当前快照 + 工作区 WIP（双轨 model-free 批处理）**，不可将问题一律归因于“远端已合并重构”。  
- **用户已有改动**: 已保护，未覆盖无关 WIP。  
- **状态目录**: `.audit-work/`（审计元数据，非产品提交目标）

---

## 1. 执行摘要

| 项 | 结果 |
|---|---|
| 检查范围 | 核心导入→验证→model-free 分析→auto-batch 双轨→缓存/检查点→结果包→序列分析→PySide6 GUI；近期 WIP 与高风险批处理链优先 |
| P0 | 3 已确认 → 3 **verified** |
| P1 | 6 已确认/高可信 → 6 **verified**（第二轮补全 AUD-007～009） |
| P2 | 3 已记录 → 3 **verified**（AUD-010～012） |
| P3 | 仅记录 |
| 数据准确性 | 合成样例 Guinier Rg、power-law α 与解析期望一致；形式门控（qRg/残差）有回归测试 |
| UI/UX | Offscreen 启动与主工作区结构正常；GUI 双轨配置已对齐“关闭序列分析” |
| 性能 | 有静态/结构风险（重复 detect、bootstrap 不可中断），**无本轮前后计时对比**，不声称性能提升 |
| **发布建议** | **满足指定条件后可以发布或合并** |

### 条件（发布前必须）

1. 对剩余未提交 WIP（auto_batch / analysis_runner / result_package 等大段）做人工 diff 审阅。  
2. 在干净 TEMP 下执行：`python -m pytest -q`（本环境 **609 passed**）。  
3. 用真实 in-situ 文件夹做一次 GUI 双轨批处理 smoke（取消、检查点重导出可选）。  
4. 已知 open P1（bootstrap 加权、取消粒度、invariant 负强度门控）若用于正式定量报告，需先关闭或在方法说明中明确排除。

---

## 2. 项目架构与审计基线

### 技术栈与入口

- Python 3.11 桌面应用；`numpy` / `scipy` / `pandas` / `matplotlib` / `PySide6` / `pytest`
- 入口：`main.py` → `MainWindow`
- 数值与持久化：`app/core/*`；UI：`app/ui/*`；测试：`tests/*`；样例：`examples/*`

### 关键业务链

```text
CSV/TXT/DAT（只读）
 → batch_inputs / io.load_curve（可选 effective_q 内存过滤）
 → validation / 质量指标
 → auto_regions / batch_consensus（候选窗 + common）
 → analysis_runner（METHOD_REGISTRY → model_free / porod / 特征…）
 → AutoBatchRun envelopes + range_audit
 → batch_cache（job + checkpoint）
 → result_package（summary / audit / details）
```

### 适用性矩阵

| 专项 | 启用 | 依据 |
|---|---|---|
| 科研/统计计算 | YES | Guinier / power-law / invariant / Porod / 批处理共识 |
| GUI | YES | PySide6 四工作区 |
| 历史兼容 | YES | project.json、settings、envelope cache、checkpoint |
| 缓存/异步/状态 | YES | batch_cache、QThread 批处理、取消 Event |
| 性能 | YES | 批处理 + bootstrap + 区域扫描 |
| 外部环境 | PARTIAL | 无生产库；本地文件 + 可选 Node workbook 脚本 |

### 修改前基线（EV-003 / EV-004）

| 检查 | 命令/方法 | 结果 |
|---|---|---|
| 依赖 | import numpy…pytest | pass（EV-001） |
| 语法 | `py_compile` main + app | COMPILE_OK |
| 全量测试（锁目录失败） | pytest 默认落 `.tmp/pytest-of-*` | 481 passed + **118 PermissionError**（环境，非产品逻辑） |
| 全量测试（干净 TEMP） | `TEMP/TMP` → `%LOCALAPPDATA%\sas_curve_analyzer_pytest_tmp` | **599 passed**（修复前） |
| 修复后全量 | 同上 | **604 passed** → 第二轮后 **609 passed**, 3 warnings |
| UI smoke | offscreen MainWindow | UI_SMOKE_OK；`enable_sequence_analysis is False` |

---

## 3. 重构影响与风险地图

| 变更区域 | 具体变化 | 潜在影响 | 关联 | 证据 | 状态 | 优先级 |
|---|---|---|---|---|---|---|
| analysis_runner 门控 | Guinier/power-law/Porod reporting gates + robustness | 报告资格与 envelope 字段 | auto_batch、result_package | WIP diff + tests | 部分已修 | P0/P1 |
| dual range_mode | adaptive + common 双轨 jobs | 序列/缓存键/导出 | auto_batch、sequence_analysis | dual jobs + tests | 序列已修 | P0 |
| GUI auto_batch 固定配置 | 硬 q 边界、bootstrap、双轨 | 与 Ti15 脚本契约一致性 | auto_batch_tab、schema defaults | build_config | 序列默认已修 | P0 |
| batch_cache checkpoint | 检查点重导出 | 审计表完整性 | result_package | 缺 candidate_windows | 已修 | P1 |
| metadata 合并 | sidecar update | 参考曲线角色被覆盖 | consensus 排除参考 | batch_inputs | 已修 | P1 |
| uncertainty bootstrap | 残差 bootstrap | CI 与主拟合加权不一致 | analysis_runner | 代码路径 | open | P1 |

---

## 4. 问题清单

| ID | 优先级 | 分类 | 状态 | 文件/符号 | 证据或复现 | 影响 |
|---|---|---|---|---|---|---|
| AUD-001 | P0 | 已确认缺陷 | **verified** | `sequence_analysis._change_flags/_linear_trends` | 双轨同 frame 两 envelope；测试 `test_sequence_analysis_keeps_dual_tracks…` | 轨迹假跳变/双倍点数 |
| AUD-002 | P0 | 已确认缺陷 | **verified** | `auto_batch_tab.build_config` | schema 默认 True；GUI 未覆盖；Ti15 要求 False | 每次 GUI 批处理静默跑序列 |
| AUD-003 | P0 | 已确认缺陷 | **verified** | `analysis_runner._result_status` | 上升曲线 Guinier → 现为 INVALID | 无效拟合被当 SUCCESS 计入 completed |
| AUD-004 | P1 | 已确认缺陷 | **verified** | `batch_cache.save/load_run_checkpoint` | 缺 `candidate_windows`；round-trip 测试 | 检查点重导出审计空洞 |
| AUD-005 | P1 | 高可信风险 | **verified** | `batch_inputs.collect_batch_inputs` | sidecar 可写 is_reference=false | 参考曲线进入共识 |
| AUD-006 | P1 | 已确认缺陷 | **verified** | `analysis_runner._metric_value` | rmse 仅在 fit_quality | 参数表缺 fit 质量列 |
| AUD-007 | P1 | 高可信风险 | **verified** | `_residual_bootstrap_callback` | 有误差时用主拟合同域加权 | 已对齐加权策略 |
| AUD-008 | P1 | 高可信风险 | **verified** | `cancel_scope` + bootstrap 循环 | 样本级取消 + 廉价 cancelled stub | 取消可中断稳健性计算 |
| AUD-009 | P1 | 高可信风险 | **verified** | `_run_invariant` | 负强度 → exploratory/not_reportable | 污染积分不再 formal |
| AUD-010 | P2 | 质量 | **verified** | auto_batch_tab 启动文案 | 反映 live `build_config()` | 不再谎称开关状态 |
| AUD-011 | P2 | 质量 | **verified** | plotting_tab.refresh | `plt.close` 旧 Figure | 降低刷新泄漏 |
| AUD-012 | P2 | 兼容 | **verified** | project.py | `schema_version=1`；缺省兼容 | 可前向拒绝更新版本 |

---

## 5. 单项问题详细分析（P0–P2 / 已修重点）

### AUD-001 双轨序列双计（P0）— verified

- **现象**: `range_mode=dual` 时 guinier/power_law/porod 每帧两条 envelope；序列按 `(analysis_type, model, parameter)` 分组。  
- **根因**: 分组键忽略 `range_track`。  
- **修复 (CHG-001)**: 分组键加入 `range_track`；同 track 内按 frame 去重。  
- **验证**: `test_sequence_analysis_keeps_dual_tracks_as_separate_trajectories`；全量 604 pass。  
- **回归强度**: `regression-test-added`（新测试直接锁定双轨行为）。

### AUD-002 GUI 静默开启序列分析（P0）— verified

- **现象**: `AutoBatchConfig.enable_sequence_analysis` 默认 True；GUI `build_config` 未关闭。  
- **修复 (CHG-002)**: GUI 显式 `enable_sequence_analysis=False`；启动文案同步。  
- **验证**: `test_gui_builds_explicit_fixed_model_free_config`；UI smoke。  
- **回归强度**: `regression-test-added`。

### AUD-003 无效 model-free 仍 SUCCESS（P0）— verified

- **现象**: `validity.status=invalid`（如 Guinier 非负斜率）时 envelope 仍 SUCCESS。  
- **修复 (CHG-003)**: `_result_status` 读取 `validity`。  
- **验证**: `test_invalid_guinier_slope_marks_envelope_invalid_not_success`。  
- **回归强度**: `red-green-confirmed`（修复前逻辑路径确定性错误；修复后测试失败→通过）。  
- **说明**: `reporting_status` 与 execution/status 分层仍保留；仅科学无效才升为 INVALID。

### AUD-004 / 005 / 006（P1）— verified

- 检查点写入/恢复 `candidate_windows`。  
- 元数据合并后回写 `is_reference` / `sequence_role` / 已有 `frame_index`。  
- `_metric_value` 回退到 `fit_quality`（rmse 等）。

### AUD-007 Bootstrap 加权（P1）— verified

- 有全点正有限 error 时，残差 bootstrap 主拟合与重拟合均用变换域权重（Guinier: `σ/I`；log10: `σ/(I ln 10)`）。  
- 否则回退 unweighted，并在 uncertainty 文案中区分。

### AUD-008 取消粒度（P1）— verified

- `cancel_scope` + bootstrap/range_sensitivity 每样本检查；取消 stub 不再重扫区域。

### AUD-009 Invariant 负强度（P1）— verified

- 有负强度：`exploratory`；负贡献面积比 >5%：`not_reportable`。

---

## 6. 数据分析准确性审计

| 功能/指标 | 公式或口径依据 | 测试输入 | 预期 | 实际 | 差异 | 证据与结论 |
|---|---|---|---|---|---|---|
| Guinier Rg | \(\ln I = \ln I_0 - R_g^2 q^2/3\) | \(I=\exp(-15^2 q^2/3)\), q∈[0.01,0.03] | Rg=15 | 15.000… | ~0 | EV-010 通过 |
| Power-law α | \(I \propto q^{-\alpha}\) | \(I=2 q^{-3.5}\) | α=3.5 | 3.500… | ~0 | EV-010 通过 |
| Guinier 形式门控 | qRg / 残差 / 点数（runner） | 已知好/坏曲线 | reportable / not_reportable | 与测试一致 | — | test_model_free_reporting_gates |
| Invariant Q_measured | 有限 q 积分 | \(I=e^{-q}\) | 有限正值 | 0.02877… | N/A（无黄金文件） | 仅内部一致性 |
| 误差加权拟合 | model_free 选择策略 | 无/有 error 列 | 仅正有限 error 加权 | 代码路径一致 | — | 静态 + 现有 tests |

**无法验证 / 缺失依据**

- 真实 Ti15 全序列黄金结果未在本机执行（脚本未跟踪数据集）。  
- P(r)/相关函数/形状模型正式定量：文档已标 experimental，未作生产验收。  
- 公式修订属语义变更：未实施。

---

## 7. UI/UX 审查与修改

| 页面/组件 | 问题证据 | 科研工作流影响 | 修改内容 | 兼容性 | 验证 |
|---|---|---|---|---|---|
| AutoBatchTab | 序列默认开启 | 双轨轨迹污染 | 关闭序列 + 文案 | 与 Ti15 契约对齐 | offscreen + UI 测试 |
| AutoBatchTab | 部分复选框装饰性 | 误解开关 | 未改（P2） | — | 静态 |
| MainWindow | — | 导入→工作台→高级→导出 | 无结构回归 | — | 四 tab 文案正确 |
| Analysis/Import | 参数进 core | 主交互路径 | 未改 | — | 现有 UI 测试通过 |

区分：静态审查 + offscreen 结构验证；**无实机截图/真数据交互录像**（环境限制披露）。

---

## 8. 性能与重复计算审查

| 路径 | 原问题 | 修改前证据 | 优化 | 修改后证据 | 结论 |
|---|---|---|---|---|---|
| 区域扫描 | 参考曲线可能重复 detect | 代码路径 | 未改 | N/A | open P2 |
| bootstrap×200×双轨 | 长作业不可中断 | 代码路径 | 未改 | N/A | open P1 |
| plotting 刷新 | 新 Figure | 代码路径 | 未改 | N/A | open P2 |

**无同条件计时基准**，不报告性能提升。

---

## 9. 修复内容（CHG）

| CHG-ID | AUD | 文件 | 修改前→后 | 回退 | 测试 |
|---|---|---|---|---|---|
| CHG-001 | AUD-001 | `sequence_analysis.py` | 分组忽略 track → 含 range_track + 帧去重 | 还原该文件 | test_sequence_analysis* |
| CHG-002 | AUD-002 | `auto_batch_tab.py` | 序列默认开 → False | 还原 build_config 行 | test_auto_batch_ui |
| CHG-003 | AUD-003 | `analysis_runner.py` | 无效 validity 仍 SUCCESS → INVALID/ASSUMPTION_DEPENDENT | 还原 `_result_status` | reporting_gates |
| CHG-004 | AUD-004 | `batch_cache.py` | checkpoint 无 windows → 持久化 | 还原两处字段 | test_batch_cache_serialization |
| CHG-005 | AUD-005 | `batch_inputs.py` | metadata 可覆盖角色 → 保护后回写 | 还原 merge 块 | test_batch_inputs |
| CHG-006 | AUD-006 | `analysis_runner.py` | 缺 fit_quality 回退 | 还原 `_metric_value` | reporting_gates rmse |

无关重构：无。未改 lockfile/依赖/公共持久化格式/科研公式定义。

---

## 10. 测试与验证结果

| 检查项 | 执行状态 | 命令/方法 | 退出码/结果 | 失败或 warning | 证据 |
|---|---|---|---|---|---|
| 依赖导入 | 已通过 | python import | 0 | — | EV-001 |
| py_compile | 已通过 | py_compile app | 0 | — | EV-003 |
| pytest（脏 TEMP） | 部分执行 | 默认 .tmp | 0（但 118 ERROR） | WinError 5 | EV-003b |
| pytest 基线（干净 TEMP） | 已通过 | pytest -q | 0 / 599 | 3 peak warnings | EV-004 |
| pytest 修复后 | 已通过 | pytest -q | 0 / **604** | 3 peak warnings | EV-011 |
| 合成数值 | 已通过 | 手写 python 样例 | 0 | — | EV-010 |
| UI smoke | 已通过 | offscreen MainWindow | 0 | — | EV-012 |
| 真实 Ti15 E2E | 未执行 | 缺数据集/路径 | — | 环境 | — |
| 性能 profile | 未执行 | — | — | — | — |
| commit/push | 未执行 | 策略禁止 | — | — | — |

---

## 11. 剩余风险与发布建议

### 唯一结论

**满足指定条件后可以发布或合并**

### 发布阻塞项（合并整包 WIP 前）

- 大段用户 WIP 尚未做完整人工 diff 会签（非单点缺陷，是变更体量风险）。  
- 审计登记的 P0/P1/P2 已全部 **verified**（见上表）。

### 非阻塞项

- PeakPropertyWarning（合成峰测试）。  
- Windows 上 pytest 若写入被锁的 `.tmp/pytest-of-*` 会整批 ERROR——CI（Ubuntu）与干净 TEMP 不受影响。

### 未覆盖范围

- 形状模型优化器全路径、PR/相关函数生产验证、真实硬件/大样本 100+ 帧内存、Node workbook 全路径人工验收。  
- 第二轮风险扫描已覆盖 WIP 主链与 model-free 核心；未把局部保证表述为“全项目无缺陷”。

### 发布前命令

```powershell
$env:TEMP="$env:LOCALAPPDATA\sas_curve_analyzer_pytest_tmp"
$env:TMP=$env:TEMP
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest -q
python main.py   # 或 Start_SasCurve_Analyzer.bat：人工双轨批处理 smoke
```

### 后续优先级

1. AUD-007 bootstrap 与主拟合加权对齐  
2. AUD-008 取消进入 bootstrap/sensitivity  
3. AUD-009 invariant 负贡献门控  
4. P2 UI 诚实文案与 Figure 复用  
5. project `schema_version`

---

## 12. 最终自检

- [x] 基线在修改产品代码前建立  
- [x] 用户已有改动未被覆盖  
- [x] 基准可靠说明（HEAD=origin/main；WIP 单独审计）  
- [x] 风险地图关联文件/符号  
- [x] 严重度/分类/置信度分开  
- [x] P0 已 verified；未关 P1 已披露  
- [x] 关键修复有回归测试  
- [x] 数据结论有合成独立复核  
- [x] UI 结论与 offscreen/交互测试一致；参数传递已查  
- [x] 性能无虚假提升声明  
- [x] 兼容性按适用性检查  
- [x] 未执行项已披露  
- [x] fixed/verified 未混用  
- [x] 最终 diff 无无关全仓格式化  
- [x] 唯一发布结论已给出  

---

*报告生成于 Goal Mode full 审计。过程状态见 `.audit-work/`。*
