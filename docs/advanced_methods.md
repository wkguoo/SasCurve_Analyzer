# 高级分析方法、模型与解释边界

本文描述当前生产实现。高级分析统一通过 `AnalysisEnvelope` 输出状态、q 区间、参数、拟合质量、详细表、有效性检查、可靠性、假设、警告和产物路径。状态包括 `success`、`assumption_dependent`、`not_applicable`、`missing_prerequisite`、`fit_failed`、`invalid` 和 `cancelled`。

q 和长度分别沿用输入 q 单位及其倒数长度单位，强度沿用输入单位。未绝对标定时，强度、尺度因子、积分和派生量都是相对量。任何数值输出、较高 R²、较低残差或排名第一的模型，都不能证明模型唯一或证明材料机理。

## P(r) 间接反演

`pr` 使用有限 q 区间的正则化反演，输出 `Dmax`、`Rg_pr`、`peak_r`、`peak_height`、`peak_count`、`tail_score`、`negative_fraction`、`smoothness`、`backfit_rmse`，以及有有效误差列时的 `backfit_chi_square`。

- `pr_distribution`：r、P(r) 和反演明细；r 为长度，P(r) 幅值依赖归一化约定。
- `pr_backfit`：输入 I(q)、回算曲线和残差，单位沿用强度。

前提是足够宽且可靠的正 q 数据、合理背景、可辩护的 `Dmax` 和正则化设置，并显式启用 `enable_pr`。有限 q、噪声、背景和正则化都会改变结果；P(r) 不能自动等同于真实粒径分布。

## 散射不变量

`invariant` 输出 `Q_measured`、`Q_low`、`Q_mid`、`Q_high`、`Q_total` 和条件满足时的 `volume_fraction`，并提供 `invariant_integrand` 表。`Q = ∫q²I(q)dq` 的单位为强度乘 q³。

`Q_measured` 仅是实测有限 q 范围。低/高 q 外推只有在显式选择、拟合有效且假设被记录时才计入；失败时不会静默补值。相体积分数还需要绝对标定、散射对比度和适用的两相假设，缺少前提时必须为空或标记为条件依赖。

## 相关函数与层片分析

`correlation` 已实现有限 q 相关函数变换，输出 `long_period`、`correlation_length`、`hard_phase_thickness`、`soft_phase_thickness`、`interface_thickness`、`phase_fraction_indicator` 和相关函数采样表。它需要 `enable_correlation` 及明确的两相/层片语境。有限 q 截断、背景和外推会影响振荡；缺少可辨识特征或材料前提时，厚度和相分数相关字段允许为空。

`lamellar` 输出 `q0`、`d0 = 2π/q0`、`peak_orders` 和峰/级次明细。仅在层片语境下解释；近整数级次只表示与周期结构相容，不证明相结构唯一。

## 形状与经验模型完整清单

模型共同输出参数值、标准误、95% 置信区间、边界命中、`AICc`、`BIC`、排名，以及 `parameter_records`、`fit_table` 和 `residual_rows`。有有效误差列时才进行加权拟合和具有统计含义的 χ² 评价。

| 模型 | 拟合参数 | 单位与派生量 | 主要限制 |
| --- | --- | --- | --- |
| `sphere` | radius, scale, background | radius 为长度；diameter, geometric_Rg, volume | 近球形、对比度和多分散性假设 |
| `core_shell_sphere` | core_radius, shell_thickness, core_contrast, shell_contrast, scale, background | 半径/壳厚为长度；total_radius, core_diameter, total_diameter | 核壳对比度和尺寸可高度相关 |
| `ellipsoid` | equatorial_radius, polar_radius, scale, background | 半径为长度；axis_ratio, volume | 轴交换和有限 q 可产生近似等价解 |
| `cylinder` | radius, length, scale, background | 几何量为长度；diameter, aspect_ratio, volume | 取向、长度分布和端面假设 |
| `disk` | radius, thickness, scale, background | 几何量为长度；diameter, aspect_ratio, volume | 取向和厚度分布影响参数 |
| `gaussian_chain` | Rg, scale, background | Rg 为长度 | 仅在高斯链统计适用区间解释 |
| `dab` | correlation_length, scale, background | correlation_length 为长度 | 经验两相相关模型，不唯一对应形貌 |
| `mass_fractal` | dimension, cutoff_length, scale, background | dimension 无量纲；cutoff_length 为长度 | 需稳定分形区间和物理可接受维数 |
| `surface_fractal` | surface_dimension, scale, background | 维数无量纲；派生 Porod_exponent | 需可辩护的斜率区间和界面假设 |
| `lamellar_peak_stack` | q0, width, amplitude, decay, background | q0/width 为 q；派生 d0, Gaussian_FWHM | 经验峰列模型，展宽来源不唯一 |

`scale`、`background`、`amplitude`、对比度和 prefactor 的严格量纲依输入强度及模型归一化，未绝对标定时不赋予绝对物理含义。体积为长度³；直径、Rg、周期和相关长度为长度。

拟合采用边界约束和多起点策略，并记录初值、上下界、边界命中、残差和不确定度。AICc/BIC 只能在同一数据、同一 q 区间和一致误差处理下比较。参数相关、区间敏感、边界命中或 bootstrap 不稳定时必须降低可靠性。

## 批量模型选择与原位连续序列

生产 runner 对注册方法使用稳定标识和统一信封。批量选择保存每条曲线的候选排名、固定的 `main_model` 和 `transition_flags`。同一材料的连续原位序列优先保持模型口径一致，再比较参数演化；不会因单帧 AICc 小幅变化而无提示切换主模型。

模型排名只是候选集、当前 q 区间和误差假设下的相对证据；候选集外可能存在更合理模型。时间连续性也不能替代物理验证，转变标记不自动等同于相变。

## 稳健性、警告与追溯

范围敏感性、bootstrap、残差、有效/排除点数、加权状态、边界命中和可靠性标签共同用于判断稳健性。结构化警告字段为 `warning_code`、`severity`、`message`、`suggested_action`、`related_analysis_id`，随结果包保存。

插件必须返回标准 `AnalysisResult`，不得修改输入曲线，并测试成功、缺少前提、失败和边界情形。导出结果应保留曲线标识、方法/模型版本、q 区间、单位、假设、警告、拟合质量及详细表，以便复算和审计。
