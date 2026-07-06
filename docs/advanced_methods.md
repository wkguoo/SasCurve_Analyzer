# 高级方法与边界说明

本文件对应阶段四。高级功能默认以“可选、可解释、可关闭、可追溯”的方式实现。

## Method Warnings

方法警告使用结构化对象记录：

- `warning_code`
- `severity`
- `message`
- `suggested_action`
- `related_analysis_id`

这些 warning 不是错误本身，而是提醒用户检查适用前提，避免把数学拟合或曲线特征过度解释为材料结构结论。

## P(r)

当前 `compute_pr` 是 experimental placeholder，不是成熟的间接傅里叶变换实现。

适用边界：

- 更适合孤立散射体或稀溶液体系。
- 连续多相材料、强相互作用体系、明显结构因子影响的曲线需要谨慎。
- `Dmax` 高度依赖 q 范围和正则化。

当前输出零值 `P(r)` 占位数组、`Dmax` 和 warning，用于后续接入成熟算法时保持统一接口。

## Correlation Function

`compute_correlation_function` 当前明确抛出 `NotImplementedError`。

相关函数分析常用于层状、准层状或两相结构，但通常需要低 q 和高 q 外推。自动提取长周期、界面厚度等参数必须有明确结构前提，不应对任意材料体系自动解释。

## Extrapolation

低 q 和高 q 外推接口存在，但默认 `disabled`。

可选方法名称预留：

- low q: `Guinier`、`constant`、`disabled`
- high q: `Porod q^-4`、`power-law`、`disabled`

启用外推时必须产生 warning。有限 q 不变量默认仍使用 measured q range。

## Porod And Invariant

Porod 平台和 invariant 都不应在缺少散射对比度、相组成、q 范围和外推假设时自动转化为绝对比表面积或体积分数。

