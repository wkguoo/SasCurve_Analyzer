# 一维 SAXS 导入与误差列

批量导入支持 `mean_intensity`、`I_abs_cm_inv`、`I_abs_cm^-1` 和现有 I 列名。q 单位仍由列名或显式配置确定；强度列名标注 cm⁻¹不构成独立的绝对标定证据。

`std_intensity` 表示帧间标准差。与 `mean_intensity` 或 `n_frames` 同时出现的 std 列也采用该含义；单独的 `std` 含义不明。它们保留在 `curve.metadata.non_measurement_error`，不填入用于拟合和误差传播的 `curve.error`。普通 error、sigma、sigma_I、dI 等按其声明作为点对点误差。未知第三列不会自动被选为误差列。

导入预览显示 `uncertainty_kind` 和相应警告。若数据提供者明确确认 std 是点对点测量误差，可在 `load_curve(..., error_column='std', metadata={'uncertainty_kind': 'measurement'})` 中声明；不能为了得到统计量而更改声明。

结果包的 `summary/run_summary.json` 保存样品、序列、采集时间、处理分支、来源哈希及单位转换等已提供的元数据。没有提供的信息不会推测补齐。完整非实测误差列在 `details/input_uncertainties/`，索引为 `audit/input_uncertainties_index.csv`，每行包含转换后的 q、q 单位、数值、列名和含义。

参数、拟合质量及方法表索引同时携带曲线 q 单位、强度单位、误差含义和处理分支；索引中的方法窗口因此可以直接解释，不必从文件名猜单位。没有曲线上下文的历史记录不会补造单位。

这些表可以从现有检查点重新导出，无需重新拟合。只有新导入的曲线才自动分类；旧检查点不会被追溯重分类。导入 q 窗过滤后，保留列与曲线点逐行对应。负强度仍保存，由具体方法判断能否使用。

本次修复未增加模型、改变算法选窗或声称通过一维曲线确定唯一结构。
