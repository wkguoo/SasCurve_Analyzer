# 一维 SAS 原位序列一键深度分析设计

## 1. 设计目标

在现有 `sas_curve_analyzer` 上增加一套低人工干预的批量自动分析系统。用户提供已完成二维积分、背景/空白处理、归一化和标定的一维 `q-I(q)` 文件，只需为整批数据设置一次样品类型和允许参与比较的候选模型，程序即完成：

1. 批量导入、自然排序、质量检查和可选 metadata 合并；
2. 为各分析方法建立批次共识 q 区间；
3. 对每条曲线运行全部适用的无模型、弱模型和条件性高级分析；
4. 对每条曲线拟合全部允许的候选模型并保存完整结果；
5. 选出整批统一主模型，使用相邻帧参数连续初始化，但不自动切换模型；
6. 分析参数随 frame、时间、温度、应变等变量的连续变化；
7. 自动生成一个主汇总 Excel 以及完整拟合数据、残差、图件和运行清单。

本设计中的“全部指标”是指用户提供的 `1D_SAS_curve_deep_analysis_general_enriched.md` 中列出的全部可量化指标，加上项目现有 10 个形状/经验模型的全部拟合参数和可直接派生的几何参数。解释示例和材料机理候选不作为自动结论。

## 2. 已确认的用户决策

- 仅覆盖当前项目的一维 SAXS/SANS/WAXS-SAXS 曲线，不扩展到 XRD、Raman、XPS 等其他表征技术。
- 输入是已完成实验校正和标定的一维 `q-I(q)` 文件；不处理二维探测器图像，不自动背景扣除或绝对强度标定。
- 每批只设置一次样品类型和允许模型，随后全自动处理。
- 输出以一个汇总 Excel 为主，同时自动保留逐曲线拟合数据、模型排名、质量控制信息和必要图件。
- 整批使用统一主模型；候选模型逐帧完整拟合并排名，但疑似结构转变只标记，不擅自切换主模型。
- 默认按文件名自然排序；存在可选 metadata 表时自动合并时间、温度、应变等实验变量。
- 各方法先建立批次共识 q 区间；覆盖不足或方法假设失效的帧保留空值和失败原因。
- 每条曲线、每种适用分析、每个允许候选模型均输出其可获得的全部参数、拟合统计、残差和有效性信息。

## 3. 范围与边界

### 3.1 包含

- `.csv`、`.txt`、`.dat` 一维曲线批量导入；必需 q、I 列，可选 error/sigma 列。
- 可选 metadata CSV/XLSX 合并。
- 数据质量、派生坐标、低/中/高 q、峰/肩峰/振荡、积分、P(r)、相关函数、模型拟合、序列和探索性统计指标。
- 现有 10 个模型：sphere、core-shell sphere、ellipsoid、cylinder、disk、Gaussian chain、DAB、mass fractal、surface fractal、lamellar peak stack。
- GUI 一键入口；核心逻辑与 GUI 分离，供测试和未来命令行入口复用。
- 非破坏性、可追溯、可部分成功的批处理。

### 3.2 不包含

- 二维探测器积分、几何校正、透过率/厚度/曝光归一化、背景或空白扣除、绝对强度标定。
- 自动修改、删除、移动、重命名或覆盖输入实验文件。
- 自动把统计拟合结果解释为确定材料结构或机理。
- 二维各向异性、真实三维结构重建、显微图像联合分析。
- 本次修改后的自动打包、Git push 或发布。

## 4. 用户工作流

1. 在 GUI 打开“一键自动分析”。
2. 选择包含一维曲线的输入文件夹。
3. 程序预览文件数量、排序、列识别、单位和可选 metadata 匹配结果。
4. 用户为整批设置一次：批次名称、样品类型、允许候选模型、q/I 单位；按需要填写绝对强度、对比度、体积分数、层状结构确认、P(r) 许可等条件。
5. 用户选择新的输出根目录或接受默认 `results`，点击“开始自动分析”。
6. GUI 显示当前帧、当前方法、成功/失败数量和进度；支持安全取消。
7. 完成后给出 `analysis_summary.xlsx` 路径、批次状态和失败数量。用户日常只需打开该 Excel；详细结果可按路径追溯。

## 5. 系统架构

### 5.1 `AutoBatchConfig`

保存并序列化整批唯一配置：

- 输入目录、输出目录、批次 ID；
- 样品类型、允许模型列表；
- q/I 单位、error 来源；
- metadata 文件与匹配列；
- 各方法开关和条件性高级分析前提；
- 自动区间、共识覆盖率、最少点数、可靠性阈值；
- bootstrap、区间敏感性、图件和逐点数据输出选项；
- 软件版本和配置版本。

配置随结果保存，不写入原始数据目录。

### 5.2 `BatchInputCollector`

- 扫描支持的曲线文件并自然排序；
- 复用现有导入、列推断和单位推断能力；
- 创建输入清单，记录文件名、路径、大小、修改时间和内容哈希；
- 合并可选 metadata；
- 单文件失败不终止整批。

### 5.3 `MetricRegistry`

使用显式注册表定义每个分析方法：

- 方法 ID、版本和适用样品类型；
- 所需输入与前提；
- 参数字段、单位和数据类型；
- 是否属于主汇总、条件表或逐点表；
- q 区间类型和最少点数；
- 可靠性检查、失败状态和图件类型。

注册表是“全部参数是否输出”的唯一验收基准。即使某字段因条件不足无数值，该字段仍必须出现，并带有状态和原因。

### 5.4 `BatchConsensusRegionResolver`

1. 对各帧复用现有自动区间检测，生成 Guinier、power-law、Porod、峰和风险区候选。
2. 按方法在 log-q 空间聚合候选区间，选择同时兼顾帧覆盖率、候选得分和点数的共识区间。
3. 默认 `consensus_min_coverage=0.70`，实际阈值写入配置和结果。
4. 每帧仍单独执行点数、正值域、qRg、平台稳定性等方法检查。
5. 默认不允许逐帧自动改区间；无法使用共识区间时记录 `missing_prerequisite` 或 `invalid`。
6. 若整批无法形成共识区间，该方法不输出伪结果，并在批次级质量表中说明原因。

### 5.5 `PerCurveAnalysisRunner`

根据注册表对一条曲线运行所有适用分析。每个方法独立捕获异常，并输出统一 `AnalysisEnvelope`：

- 身份、输入、q 区间和方法版本；
- 标量参数、表格结果和图件路径；
- 拟合质量、有效性检查和可靠性；
- 状态、警告、错误类型和失败原因。

### 5.6 `CandidateModelFitter`

- 每条曲线拟合配置允许的全部候选模型，不只拟合主模型。
- 第一帧使用模型默认初值和多起点策略；后续帧优先使用上一有效帧参数。
- 失败后的重试顺序为：上一有效帧初值、批次有效参数中位数、模型默认初值、多起点初值。
- 重试失败后保留空参数和 `fit_failed`，绝不复制上一帧结果。
- 每次拟合保存所有参数、不确定度、边界、协方差、相关矩阵、完整拟合曲线和逐点残差。

### 5.7 `BatchModelSelector`

批次主模型按以下信息综合选择：

- 有效拟合覆盖率；
- 中位 AICc/BIC 排名；
- 残差检查通过率；
- 参数触边率和参数不确定度；
- 相邻帧参数稳定性；
- 用户选择的样品类型和模型先验。

主模型必须在足够帧上有效；默认最低有效覆盖率为 70%。逐帧候选排名全部保留。若连续至少 3 帧出现主模型失效且另一候选稳定占优，仅标记 `possible_model_transition`，不自动更换主模型。

### 5.8 `SequenceAnalyzer`

- 按 `sequence_order` 和 metadata 自变量排序；
- 计算相对首帧和前一帧的差值、比值与参数变化；
- 生成参数趋势、二维热图、变化点和离群帧；
- 在 metadata 自变量存在且有效点数足够时计算起始点、峰值点、半程点、增长率和饱和值；
- Avrami/经验动力学拟合和 PCA/聚类标为 `exploratory`，保留完整拟合质量，不作为机理证明。

### 5.9 `ResultPackageWriter`

- 先写入临时结果目录；成功形成 Excel、manifest 和索引后，再形成正式时间戳目录。
- 取消或崩溃时保留明确标记的未完成目录和日志。
- 永不覆盖旧结果或输入文件。

### 5.10 GUI 控制器

- GUI 只负责批次设置、预览、启动、进度、取消和结果路径展示。
- 所有数值计算、模型拟合和导出逻辑位于 `app/core`。
- 分析在后台工作线程执行，GUI 保持响应；进度至少按“曲线 × 方法/模型”更新。

## 6. 统一输出契约

### 6.1 所有拟合型分析的共同字段

每条“曲线 × 方法 × 模型”均保存：

- `curve_id`、`curve_name`、`frame_index`、`sequence_order`、`analysis_id`、`analysis_type`、`model_name`；
- `q_start`、`q_end`、转换坐标、输入点数、拟合点数、排除点数、逐点排除原因；
- error 来源、是否加权、权重公式；
- 每个参数的名称、估计值、单位、初值、下界、上界、标准误、95% 置信区间、是否触边；
- 参数协方差矩阵和相关矩阵；
- 协方差条件数、最大绝对参数相关系数和 `identifiability_status`，用于标记参数非唯一或高度耦合；
- 收敛状态、自由度、RSS/WRSS、RMSE、MAE、R²、adjusted R²、χ²、reduced χ²、AIC、AICc、BIC；
- q、observed、fitted、residual、standardized residual、sigma、weight、included、exclusion_reason 逐点表；
- 方法假设、有效性检查、`reliability_score`、`reliability_label`、warnings、失败原因；
- 软件版本、配置版本、时间戳、拟合图/残差图/CSV/JSON 路径和候选排名。

对不适用于某条曲线的统计量，不使用 0、-1 或上一帧值代替；字段保留、值为空，并给出明确状态。

### 6.2 状态枚举

- `success`：数值有效且通过方法检查；
- `assumption_dependent`：计算完成，但依赖额外结构或实验假设；
- `not_applicable`：样品类型或方法范围不适用；
- `missing_prerequisite`：缺少绝对强度、对比度、误差、metadata 等前提；
- `fit_failed`：优化或数值计算失败；
- `invalid`：数值产生但未通过有效性检查；
- `cancelled`：用户取消后未执行或未完成。

可靠性继续使用项目现有 `high`、`medium`、`low`、`assumption_dependent`、`invalid` 标签。

## 7. 方法级参数注册表

### 7.1 数据质量、尺度窗口和派生坐标

- q_min、q_max、d_max、d_min、点数；
- I_min、I_max、动态范围；
- NaN、Inf、负强度、零强度、重复 q 数；
- q 单调性；error 缺失、NaN、负值和零值数；
- log 可用点数和排除点数；
- q 网格一致性、共同 q 范围、q/I 单位一致性；
- 输入文件哈希和 metadata 匹配状态。
- 逐输入行保留 q、I、error，并输出 q2、ln_q、log10_q、inv_q、d_2pi_over_q、qRg、qD、qR；
- 输出 ln_I、log10_I、qI、q2I、q3I、q4I、q_alpha_I、local_slope、I_over_ref、I_minus_ref；
- 每个有数学定义域限制的派生列都附带对应 `valid_*` 标记，原输入行和顺序不因无效变换而删除；
- 显示归一化分别支持 max、q_ref、积分面积、invariant、低/中/高 q 区间均值，并记录归一化方法和参数；纵向 offset 只保存为绘图元数据，不写回曲线数值。

### 7.2 Guinier

- Rg、I(0)、线性斜率、截距；
- Rg、I(0)、斜率和截距的标准误及 95% 置信区间；
- q_start、q_end、qminRg、qmaxRg；
- R²、χ²、reduced χ²、RMSE 和残差评分；
- 输入、拟合和排除点数及原因；
- 是否加权、候选区排名、qRg 有效性检查；
- 拟合曲线、逐点残差、拟合图和残差图。

### 7.3 Power-law、分形、局部斜率和 crossover

- alpha、前因子 A、斜率、截距及不确定度；
- 区间、点数、R²、χ²、残差和区间敏感性；
- 逐 q 的 alpha(q)；
- 每个斜率平台的 q_start、q_end、alpha_mean、alpha_std、点数和稳定度；
- crossover_q、crossover_d、前后斜率差和置信度；
- 质量分形/表面分形候选维数及其适用性检查；
- 跨峰、肩峰或噪声区风险。

### 7.4 峰、肩峰和振荡

- 每个 peak_id 的 q_star、d_star、原始 I、基线、净峰高、面积；
- FWHM、HWHM、不对称度、prominence、SNR、经验相关长度；
- 峰是否完整、边界截断和不确定度；
- 肩峰 q、d、曲率指标和置信度；
- 极大/极小位置、振荡周期、振荡衰减和系统移动趋势。

### 7.5 Porod

- 高 q 幂律 alpha、斜率、截距及不确定度；
- Porod K 和 relative K；
- q4I 平台均值、标准差、CV、q_start、q_end 和点数；
- 高 q 噪声评分、Porod-like 有效性检查；
- 条件满足时输出界面面积相关量、公式、对比度和两相/绝对强度前提。

### 7.6 Kratky 和补偿图

- Kratky q_peak、d_peak、q2I_peak、FWHM、面积和峰完整性；
- 归一化 Kratky 使用的 Rg 和 I(0)；
- 任意 alpha 的 q^alpha I 平台均值、标准差、CV、区间和成立评分。

### 7.7 Invariant 和积分

- Q_measured、Q_low、Q_mid、Q_high；
- integral_I、integral_qI、integral_q2I、integral_q4I；
- 各指定区间的平均值、中位数和斜率；
- q2I 主贡献峰和累计贡献 10%、50%、90% 对应 q；
- 积分方法、区间和负强度影响；
- 低/高 q 外推量、外推占比和方法；
- 条件满足时输出 Q_total 和体积分数估计及其前提。

### 7.8 P(r)

- Dmax 输入值和最终值、regularization、r_points；
- Rg_pr、P(r) 峰位、峰高、多峰数、长尾评分、负值比例和平滑度；
- I(q) 回算 RMSE/χ²；
- Dmax 和正则化敏感性；
- P(r) 表、回算曲线、假设和有效性检查。

### 7.9 相关函数和层状分析

- 一维/三维相关函数表；
- long_period、correlation_length、hard_phase_thickness、soft_phase_thickness、interface_thickness 和局部相比例指标；
- 层状峰级次、q0、d0；
- 低/高 q 外推方法、区间和贡献；
- 两相、层状/准层状和 Porod 区前提检查。

### 7.10 原位序列和探索性统计

- I(q_ref,t)；相对首帧和前一帧的差值、比值；
- 保存相对用户指定参考帧的差值和比值，并记录 q 网格是否原生一致、是否使用插值、公共 q 范围和插值方法；
- 对 max、q_ref、积分面积、invariant、低/中/高 q 区间均值等每种显示归一化，计算并保存归一化形状距离及其有效 q 范围；
- 每个标量参数的绝对变化、相对变化、趋势斜率、变化点和离群帧；
- 起始位置、峰值位置、半程位置、增长率和饱和值；
- q-time/q-temperature 热图；
- 可选 Avrami/经验动力学参数及全部拟合质量；
- PCA scores/loadings、解释方差；聚类标签和距离。

## 8. 模型参数注册表

所有模型还必须输出第 6.1 节的共同拟合字段。

| 模型 | 原始拟合参数 | 直接派生参数 |
|---|---|---|
| sphere | radius, scale, background | diameter, geometric_Rg, volume |
| core_shell_sphere | core_radius, shell_thickness, core_contrast, shell_contrast, scale, background | total_radius, core_diameter, total_diameter, core_volume, total_volume |
| ellipsoid | equatorial_radius, polar_radius, scale, background | axis_ratio, equivalent_radius, volume |
| cylinder | radius, length, scale, background | diameter, aspect_ratio, volume |
| disk | radius, thickness, scale, background | diameter, aspect_ratio, volume |
| gaussian_chain | Rg, scale, background | 无额外几何换算 |
| dab | correlation_length, scale, background | 无额外结构结论 |
| mass_fractal | dimension, cutoff_length, scale, background | cutoff 对应尺度 |
| surface_fractal | surface_dimension, scale, background | Porod_exponent = 6 - surface_dimension |
| lamellar_peak_stack | q0, width, amplitude, decay, background | d0 = 2pi/q0, Gaussian_FWHM, visible_peak_orders |

派生几何量仅表示模型内部数学换算，必须标注模型依赖，不作为结构唯一证明。

## 9. Excel 与结果目录

正式目录：

```text
results/<batch_id>_<YYYYMMDD_HHMMSS>/
  analysis_summary.xlsx
  manifest.json
  run_log.md
  tables/
    curve_metrics_long.csv
    analysis_parameters.csv
    fit_quality.csv
    model_parameters.csv
    model_ranking.csv
    peaks_oscillations.csv
    integrals.csv
    sequence_trends.csv
    qc_failures.csv
  fits/<frame>/<analysis_or_model>/
    fit_points.csv
    residuals.csv
    covariance.csv
    correlation.csv
    result.json
    fit.png
    residuals.png
  figures/
    sequence_heatmap.png
    parameter_trends.png
    fit_qc/
```

Excel 工作表：

1. `00_ReadMe`：批次说明、状态、主模型、输入和输出路径；
2. `01_Frame_Summary`：每帧一行的高频标量和主模型参数；
3. `02_Metrics_Long`：全部方法标量指标的权威长表；
4. `03_Analysis_Parameters`：方法参数值、单位、误差、区间和状态；
5. `04_Fit_Quality`：每次拟合的完整质量统计；
6. `05_Model_Parameters`：每帧、每候选模型、每参数一行；
7. `06_Parameter_Covariance`：协方差/相关矩阵索引；
8. `07_Model_Ranking`：逐帧和批次级模型排名；
9. `08_Peaks_Oscillations`：多峰、肩峰和振荡长表；
10. `09_Integrals`：总积分、分段积分和贡献区；
11. `10_Sequence_Trends`：连续参数和动力学指标；
12. `11_Uncertainty`：bootstrap 和区间敏感性；
13. `12_Advanced_Conditional`：P(r)、相关函数、绝对定量等条件性结果；
14. `13_QC_Failures`：文件、方法、模型级失败和原因；
15. `14_Metadata`：原始及合并后的实验变量；
16. `15_Run_Config`：完整运行配置和软件版本。

数值和单位分列。主表用于 Excel/Origin 作图，权威长表用于保证全部参数不丢失。逐点拟合和残差可能超过 Excel 行数限制，因此完整数据写入 CSV，Excel 保存路径索引和摘要统计。

## 10. 失败处理与数据安全

- 单文件失败不终止整批，批次状态为 `partial_success`。
- 单方法或单模型失败只影响对应组合，其余分析继续。
- 输入文件只读；运行前后可用哈希验证未改变。
- 所有结果写入新目录；重跑生成新时间戳目录。
- 取消发生在当前原子分析完成后；未执行项目标为 `cancelled`。
- 临时目录只有在 Excel、manifest 和索引形成后才转为正式结果；崩溃记录保留为未完成目录。
- 不对负强度加常数，不自动平滑替代原始数据，不自动背景扣除，不用前一帧结果填补失败帧。

## 11. 测试与验收

### 11.1 注册表完整性

- 每种方法的所有注册字段均能在结果架构和 Excel/CSV 中找到。
- 所有状态下字段保持存在；失败时值为空且原因非空。
- 10 个模型的原始参数、派生参数、误差、边界、协方差和质量字段完整。

### 11.2 数值测试

- 用已知参数的合成曲线验证 10 个模型的前向回算曲线在规定容差内；对可辨识参数验证参数恢复，对存在尺度/对比度耦合的参数验证协方差、相关性和 `identifiability_status` 能正确标记非唯一性。
- 验证 Guinier、power-law、Porod、峰、积分、P(r) 和相关函数的公式和单位。
- 覆盖有/无 error、加权/非加权、负强度、重复 q、NaN、不同 q 网格和窄 q 范围。
- 验证 bootstrap、区间敏感性、AICc/BIC 和残差统计。

### 11.3 批量与连续性测试

- 自然排序和 metadata 匹配正确；
- 批次共识区间在相邻帧保持一致；
- 上一帧初值只用于初始化，不替代拟合结果；
- 单帧、单方法或单模型失败不终止整批；
- 主模型固定，疑似模型转变只标记；
- 差值、比值、趋势、变化点、热图和探索性统计可追溯。

### 11.4 输出契约测试

- 16 个工作表存在并包含规定列；
- 所有 CSV、JSON 和图件路径有效；
- Excel 数值列保持数值类型，单位不混入数值文本；
- 超过 Excel 行数的数据完整保存在 CSV，索引无断链；
- manifest 可追溯输入、配置、分析、版本和输出。

### 11.5 安全与 GUI 测试

- 运行前后输入文件哈希相同；
- 旧结果不被覆盖；
- GUI 分析期间保持响应，可取消并报告状态；
- offscreen GUI、完整 pytest、compileall 和 diff whitespace 检查全部通过后才交付。

## 12. 分层实施顺序

由于该功能覆盖自动编排、数值分析、模型筛选、序列分析和复合导出，实施分为四个可独立验证的层，但最终由一个按钮统一调用：

1. 指标注册表、统一结果架构、批次编排、共识区间和失败隔离；
2. 全部逐曲线指标、10 模型完整拟合、模型筛选、不确定度和逐点结果；
3. 原位序列、差值/比值、热图、动力学、变化点、PCA/聚类；
4. Excel/CSV/JSON/图件结果包、GUI 一键入口、全量回归和安全验证。

每层必须通过相应测试后再进入下一层；不以部分功能完成代替整个目标完成。

## 13. 验收完成标准

用户对一批已校准一维曲线执行一次批次设置并点击开始后，无需逐帧手动操作，程序生成完整结果包。结果包必须满足：

- 所有文档指标均在注册表、输出或明确的条件性空值中有对应项；
- 每条曲线的全部适用方法和全部允许模型都有完整参数、质量、残差和状态；
- 原位序列顺序和主模型保持一致，可识别但不擅自解释异常变化；
- 一个 Excel 即可查看每帧核心结果，并可追溯到全部详细数据；
- 原始文件未改变，旧结果未覆盖；
- 全量自动测试和输出契约检查通过。
