# Agent 无人值守的一维 SAS 批处理

输入是已归约、已校准的一维 q–I 曲线，可带 error/sigma 列。原始探测器图片需要先完成二维积分、背景/透射率/厚度校正；本入口不会把这些步骤假定为已验证的科学事实。

## 直接执行

在项目根目录运行；Windows 可把 `python` 换成 `py -3.11`。

```powershell
python -m pip install -r requirements-headless.txt
python -m app.cli methods
python -m app.cli discover --input "D:\SAS\input" --config examples/agent_study.json
python -m app.cli run --input "D:\SAS\input" --output "D:\SAS\derived\run_001" --config examples/agent_study.json
```

`discover` 只读，输出 JSON 分组清单。`run` 的 stdout 是最终状态 JSON，stderr 是逐任务 JSONL 进度；`--quiet` 可以关闭进度。运行不导入 PySide6，不创建 UI。Agent 应检查退出码和 `study.json`，然后读取每个样品的质量审计和演化表再组织科研解释。

建议给 Agent 的指令：

> 对这个已校准的一维 SAS 文件夹执行无人值守处理。先识别样品与帧顺序，检查单位和元数据；用独立样品运行导出全部分析、演化、作图数据及图片包。将结果写入新的输入目录之外的路径。检查退出码、失败文件、方法适用条件、reporting_status 和哈希；保留无效帧和缺失参数，不把空值变成零，不从拟合排序推出唯一结构或机理。报告实际完成内容和限制。

## 样品与帧身份

最稳妥的输入布局是每个样品/方向一个目录，例如 `Ti15_LD/frame_0001.csv` 和 `Ti15_TD/frame_0001.csv`。默认递归扫描 `.csv/.txt/.dat`，按自然顺序读取；目录身份使用相对路径，因此同名文件不会覆盖。一个样品散落在多个目录时，用元数据显式合并；不同加载方向应视为独立序列。

平铺目录可以使用 `Ti15_LD_00001_abs2d.csv`、`Ti15_TD_00001_abs2d.csv` 等明确帧标记。样品名中的数字不作为帧号。无法判断的平铺文件会报错，避免悄悄合并不同样品。

复杂文件名在 JSON 配置里设置正则，例如：

```json
{
  "schema_version": 1,
  "sample_regex": "(?P<sample>.+)_f(?P<frame>\\d+)",
  "analysis": {"enable_shape_models": false}
}
```

`sample_regex` 对完整文件 stem 匹配，必须有 `sample` 和 `frame` 两个命名组，frame 为非负整数。显式元数据优先于正则。每个样品在区间共识、拟合、主模型、参照曲线与演化分析之前完成隔离。

## 时间、温度、应变等元数据

侧表使用 CSV。例如：

```csv
source_file,sample_id,frame_index,time_s,temperature_C,strain
Ti15_LD/frame_0001.csv,Ti15_LD,1,0,25,0
Ti15_LD/frame_0002.csv,Ti15_LD,2,2,25,0.01
Ti15_TD/frame_0001.csv,Ti15_TD,1,0,25,0
```

配置：

```json
{
  "grouping": "metadata",
  "analysis": {
    "metadata_path": "metadata.csv",
    "sequence_axis": "time_s",
    "enable_shape_models": false
  },
  "samples": {
    "Ti15_LD": {"allow_per_frame_range_fallback": true}
  }
}
```

metadata_path 相对配置文件解释。source_file 优先使用相对输入根目录的路径；只有 basename 唯一时才允许省略目录。重复或歧义匹配会报错。元数据不能覆盖程序维护的原始路径、单位、哈希和处理记录。每个样品都可覆盖 analysis 设置；未知字段和不存在的样品名会报错。

不提供物理轴时使用帧号/读取顺序，并记录所选轴；它们不能自动解释为秒。显式轴缺失、非有限或重复时保留原始诊断，不据此拟合动力学。`enable_kinetics` 只产生描述性线性趋势，不能识别真实动力学机制。

## q 范围、单位与自动分析

批处理统一 q 为 `A^-1`，`nm^-1` 在范围裁剪之前数值换算，原始单位与换算系数保留在溯源中。q_unit_override 是原始数值单位的声明；它不是仅改标签的转换。强度单位不作暗中换算，单一样品内不兼容强度单位会阻止跨曲线比较。

未指定 effective_q_range 时，CLI 从成功导入帧选择共有的有限、正 q 实测范围，保障测量范围积分可比；无共有范围会留下失败记录。JSON 中可以显式设置 `"effective_q_range": [0.005, 0.2]`，数值始终是 `A^-1`。这个范围是数据边界；Guinier、幂律、Porod 会各自检测候选和共识窗口，局部特征独立检测。启用 allow_per_frame_range_fallback 后，无法形成共识时可使用本帧同方法窗口，并在 range_audit 中标明；此时参数演化的窗口变化需要复核。

未提供误差时可以运行，但采用不加权拟合并保留限制。NaN、非法 q、零/负强度、重复 q 和无效误差会留下诊断；对数表达不加常数修正负值。缺失/无效参数用 null 或空 CSV 单元格表达。

## 交付与恢复

输出目录必须与输入树分离，且首次运行目标必须不存在。顶层 `sample_index.csv` 和 `study.json` 列出样品状态、包路径、失败和输入/输出哈希。每个样品包含完整分析信封、源数据、转换/实际作图数据、质量审计、演化表、图片、数据包和图片包；图片索引记录坐标和文件映射。完整原始输入副本与所选 q 范围的派生曲线分别保留，原始文件不修改。

演化图同时保留通过质量门槛的参数和明确标注的探索性候选。探索性图使用空心点与标题提示，参数仍保留原 reporting_status；坏帧、受限参数保持断点，重复局部特征用不连线的点显示，不暗示已建立峰身份连续追踪。

```powershell
python -m app.cli run --input "D:\SAS\input" --output "D:\SAS\derived\run_001" --config examples/agent_study.json --resume
python -m app.cli run --input "D:\SAS\input" --output "D:\SAS\derived\run_001" --config examples/agent_study.json --resume --retry-failed
```

恢复要求输入内容、配置、元数据与算法版本指纹一致，且已完成包的每个输出哈希通过验证。中断任务可复用既有逐方法计算缓存。失败重试写入新的样品包目录，不覆盖旧证据；未完整发布的隐藏 staging 目录保留供调查。Ctrl+C 请求安全取消，当前不可中断的数值调用结束后停止后续任务。

退出码：`0` 完成或有方法限制；`2` 部分成功/失败；`3` 配置、身份、路径或恢复完整性错误；`130` 取消。完成仅表示计算与导出链条完成，科学接受仍需检验假设、测量条件与独立表征。

## 表达和方法覆盖

| 表达/分析 | 导出与适用条件 |
| --- | --- |
| q–I、semi-log、log-log | 全序列分页概览；精确坐标/误差 CSV；有限值与对数条件筛选 |
| Guinier | 自动区间、Rg/I0、拟合点/残差、qRg 与质量门槛 |
| Kratky、Porod、测量范围不变量、局部斜率 | 转换源数据、概览图、描述参数；不变量只代表所选实测范围 |
| 归一化 Kratky | 仅在可靠且可报告的正 Rg/I0 可用时生成，缺少前提时有明确记录 |
| 峰、肩、交叉区、振荡、积分 | 特征与区间诊断；2π/q 是特征长度，不能自动解释为粒子直径 |
| 形状/经验模型 | 显式 enable_shape_models 和 allowed_models；各模型参数、拟合点/残差、排序依赖假设 |
| P(r) | 显式 enable_pr 与 pr_dmax（批处理单位 A），可设 pr_regularization 和 pr_r_points（10–1000）；缺少 Dmax 时跳过，不自动假装为用户提供的约束；实验性结果/回拟合，不宣称唯一形貌 |
| 相关函数/层状结构 | sample_type 为 two_phase/lamellar 并显式 enable_correlation；实验性有限范围估计 |
| 粒径分布 f(R)/N(R)/V(R) | 当前没有通过验证的分布反演器；不从 Rg 或单分散球拟合编造分布 |
| 二维 SAXS、方位角与扇区积分 | 在本工具上游处理，再将不同方向的一维曲线作为独立样品输入 |
| 体积分数、数密度、绝对界面面积 | 不因拟合成功自动生成；需要绝对标定、对比度、外推与模型适用性 |

归一化 Kratky 定义为 `(qRg)^2 I(q)/I0` 对 `qRg`，参考 [SASBDB 方法说明](https://www.sasbdb.org/help/)。有限范围不变量与绝对定量的边界参考 [SasView 不变量说明](https://www.sasview.org/docs/user/qtgui/Perspectives/Invariant/invariant_help.html)。分享对话作为需求来源见 [SAXS 作图形式比较](https://chatgpt.com/share/6abd0b2c-0ad4-83e8-a7e5-aa60c845fc89)；其中的一般性解释不是本软件科学验证的证据。
