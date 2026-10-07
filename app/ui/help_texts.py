"""Plain-language help for the application's controls and choices."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QLineEdit,
    QMenu,
    QMessageBox,
    QScrollBar,
    QSplitter,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QWhatsThis,
    QWidget,
)

from app.ui.style import apply_help


FIELD_HELP: dict[str, dict[str, str]] = {'ImportTab': {'q_column': '填写文件中曲线横坐标 q 的列名，例如 q；q 越小通常对应越大的结构。自动识别后仍可修改，导入时按此列读取。',
               'intensity_column': '填写散射强度的列名，例如 I；它是曲线纵坐标。请与文件表头一致，导入后按此列生成强度数据。',
               'error_column': '填写文件中测量误差的列名，例如 sigma；误差表示强度可能上下浮动的大小。没有这一列就留空，导入后可用上下短线显示误差。',
               'q_unit': '填写文件的横坐标单位：A^-1 是倒数埃，nm^-1 是倒数纳米；一埃等于 0.1 纳米，两种单位的数值相差 10 倍。',
               'intensity_unit': '填写曲线强度的单位，例如 cm^-1（每厘米）；这项说明会随曲线保存和导出。这里只登记单位，强度需事先完成校准。',
               'limit_q_range': '勾选后只导入下面两项所指定的横坐标范围；取消勾选则读取全部范围。原始文件会保留。',
               'import_q_min': '输入要导入的横坐标最小值，单位与文件一致，须小于上限。勾选范围限制后，只读取不小于此值的数据点。',
               'import_q_max': '输入要导入的横坐标最大值，单位与文件一致，须大于下限。勾选范围限制后，只读取不大于此值的数据点。',
               'log': '查看导入、单位转换的结果或失败原因，可选中文字复制。这里是只读记录；修改导入设置后需重新执行相应操作。',
               'preview_output': '查看文件前几行、列识别和无效值等检查结果，可选中文字复制。修改列名或范围后点击预览重新检查，预览不会导入曲线。'},
 'AnalysisTab': {'analysis_type': '选择要从曲线中查看或计算的内容；下拉选项会说明具体作用。确认横坐标范围后点击运行，结果显示在下方。',
                 'q_min': '输入本次分析的曲线横坐标最小值，按当前曲线单位填写，须小于上限；运行时只使用该范围内的点。',
                 'q_max': '输入本次分析的曲线横坐标最大值，按当前曲线单位填写，须大于下限；运行时只使用该范围内的点。',
                 'output': '查看本次数据检查、计算结果和注意事项；选中文字可复制。先核对所用范围及警告，再解释数值。',
                 'auto_region_table': '点击一行查看推荐范围，再把范围填入分析框或运行推荐方法。评分帮助挑选范围，不能证明样品结构；修改表中文字不会改变分析参数。',
                 'auto_region_detail': '查看所选范围为何被推荐、包含多少数据以及有哪些问题；选中文字可复制，便于决定是否使用这一段曲线。'},
 'PlottingTab': {'plot_type': '选择曲线的显示方式，选中后立即重绘；不同选项会换算横坐标或强度，帮助查看峰形和变化趋势。',
                 'show_error': '勾选后在数据点旁显示上下短线，表示测量强度可能浮动的大小。需要文件中有误差列；取消勾选后隐藏短线，保留误差数据。',
                 'show_d_axis': '勾选后在适用的图上方增加长度刻度，用横坐标换算可能对应的结构距离；它不是直接测出的颗粒大小。',
                 'annotate_peaks': '勾选后在原始强度图中标出检测到的第一个峰，并显示该位置换算出的结构距离；取消勾选后隐藏标注。',
                 'figure_preset': '选择导出图像的分辨率、字号和线宽组合，导出时生效。适合屏幕、组会或论文初稿；实际文件格式仍由旁边的格式框决定。',
                 'figure_format': '选择保存图片的格式：PNG 是由像素组成的图片；SVG 和 PDF 的线条放大后仍清晰。点击导出后按此格式保存。',
                 'x_min': '填写图中横坐标的最小值，留空让软件自动确定；按回车或刷新图形后生效。若图上坐标已换算，请按图上数值填写。',
                 'x_max': '填写图中横坐标的最大值，须大于最小值；留空自动确定，按回车或刷新图形后生效。若坐标已换算，请按图上数值填写。',
                 'y_min': '填写图中纵坐标的最小值，留空自动确定；按回车或刷新图形后生效。请按当前图上数值填写，例如强度或换算后的强度。',
                 'y_max': '填写图中纵坐标的最大值，须大于最小值；留空自动确定，按回车或刷新图形后生效，只改变显示范围。',
                 'messages': '查看绘图警告、坐标范围错误或图像导出路径，可选中文字复制。输入范围有误时会说明原因；这里是只读信息区。',
                 'canvas': '把鼠标移到图内，下方会显示所在位置的数值；用显示方式和范围设置查看不同部分，用导出按钮保存图片。'},
 'DeepAnalysisTab': {'q_min': '输入本次深度分析的曲线横坐标最小值，按当前曲线单位填写，须小于上限；运行时只使用该范围内的点。',
                     'q_max': '输入本次深度分析的曲线横坐标最大值，按当前曲线单位填写，须大于下限；运行时只使用该范围内的点。',
                     'sample_type': '按已知样品选择类型；不确定就选 '
                                    'unknown。选择会决定是否计算内部两点距离分布、结构随距离的关联等，不会自动认定样品结构。',
                     'shape_model': '选择要尝试拟合的形状或结构模型；none '
                                    '表示不做形状模型拟合。运行后得到该假设下的参数、拟合质量和限制，不能仅凭拟合确认结构。',
                     'dmax': '填写要计算的最大结构距离，用于内部两点距离分布和相关函数的距离上限；须为正数。横坐标单位为 Å⁻¹时用 Å，为 nm⁻¹时用 nm。',
                     'regularization': '填写非负数，控制计算出的距离分布有多平滑。数值越大，起伏越少；可比较几个数值，看主要特征是否稳定。',
                     'contrast': '填写两种区域的散射长度密度差，即产生散射的能力差异，并勾选使用；单位须与强度和长度一致。用于体积分数等估计，软件不自动换算其单位。',
                     'volume_fraction': '填写某种材料占样品总体积的比例，0–1，例如 0.2 表示 '
                                        '20%。当前版本将它记入界面分析结果，不把它作为形状拟合的起始值。',
                     'use_contrast': '勾选后使用上方填写的散射长度密度差，即两种区域产生散射的能力差异，参与体积分数等估计；未勾选按未提供处理，数值须非零且单位一致。',
                     'absolute_intensity': '只有强度已按标准换算成带物理单位的数值时才勾选；勾选不会替你校准数据。它会影响哪些材料参数可以估计。',
                     'fit_background': '勾选后，形状拟合会同时估计曲线中近似不变的背景强度；取消后将该背景设为零。只在选择形状模型时使用。',
                     'output': '查看各项计算结果、参数和警告，可选中文字复制。内部两点距离分布、测量范围外的强度估计及模型拟合受输入假设影响，请结合每项说明判断。'},
 'AutoBatchTab': {'input_dir': '填写或选择存放已校准一维曲线的文件夹，再开始分析；程序读取其中可识别的数据文件，逐个记录成功或失败，不修改原始文件。',
                  'output_dir': '填写或选择结果父目录；开始分析后在其中创建本次结果包和计算缓存。完成信息会显示结果包路径，可据此打开导出的表和报告。',
                  'batch_id': '填写非空批次名称，建议使用样品或实验序列名；开始后用于结果包和计算缓存命名，帮助区分不同分析批次。',
                  'sample_type': '按已知样品选择类型，不确定就选未知/通用；它决定可运行的方法，例如重复层状结构分析及结构随距离的关联，不会自动认定样品结构。',
                  'effective_q_min': '填写批量分析的 q 下限，单位 Å⁻¹且小于上限；只分析有效区间。q '
                                     '是曲线横坐标，越小通常对应越大的结构；nm⁻¹数值需除以 10。',
                  'effective_q_max': '填写批量分析的 q 上限，单位 Å⁻¹且大于下限；只分析有效区间。q '
                                     '是曲线横坐标，越小通常对应越大的结构；nm⁻¹数值需除以 10。',
                  'enable_pr': '勾选后，为适用样品计算 P(r)，即散射体内部两点距离的分布，结果写入结果包。该计算依赖最大结构距离和有限测量范围等假设。',
                  'enable_correlation': '勾选后，为两相或层片样品计算结构随距离的关联，结果写入结果包。两相是两种散射能力不同的区域，层片是重复层状结构；需选择对应类型。',
                  'enable_kinetics': '勾选后，按测量顺序或已知时间等坐标，画出合格参数的直线变化趋势；用于描述参数如何变化，不说明变化的原因。',
                  'enable_statistics': '勾选后输出探索性主成分分析和聚类：前者概括主要变化，后者比较曲线相似性。结果写入结果包，分组不自动代表相变或因果关系。',
                  'output': '查看批量分析进度、完成状态、失败数量及结果包路径，可选中文字复制。完成时请按状态和方法限制检查结果，取消后只保存已完成部分。'},
 'BatchTab': {'group_name': '填写曲线组名称，例如样品或序列名；建组时作为组名，平均时用于新曲线命名。建组前先选择所需曲线或序列表行。',
              'curve_list': '点击可分别选中或取消多条曲线，再建组或平均；平均至少选两条。单位显示在名称后；q 是曲线横坐标，越小通常对应越大的结构。',
              'curve_a': '选择比较基准曲线 A，再选不同的 B；比较时计算 B−A、B/A 或 (B−A)/A。结果会单独记录，原曲线保持不变。',
              'curve_b': '选择要与基准 A 比较的曲线 B，两者必须不同；比较时 B 位于差值或比值的分子。所选方式决定输出的是差值、比值还是相对差异。',
              'comparison_type': '选择 B 相对于 A 的比较方式，再点击比较；必要时按共同范围插值。结果单独保存，除法中无法计算的点会附带警告。',
              'sequence_table': '点击选中测量记录，按住 Ctrl 可多选，再按表中顺序建组；表内显示测量序号、数据点数、横坐标范围和注意事项，只能查看。',
              'output': '查看建组、平均或 A/B 比较的结果及失败原因，可选中文字复制。结果中的标识和警告用于核对本次操作，不能在这里修改曲线。'},
 'RecordsTab': {'source_type': '选择要标记的对象类别，右侧随之列出对应对象；再选具体对象并标记为正式记录，便于报告追踪。图像类别是预留入口，尚无可标记对象。',
                'source_selector': '选择要纳入正式记录的具体曲线、分析或比较结果，再点击标记；只选择不会写入记录。没有可选对象时，需先导入或生成相应结果。',
                'formal_list': '点选一项后可取消其正式记录标记；列表显示供报告追踪的对象。取消标记不删除原曲线或结果，操作会写入历史记录。',
                'output': '查看操作历史以及正式记录的来源和标识，可选中文字复制。刷新后与当前项目同步；这里只显示记录，不编辑或重新运行分析。'},
 'AdvancedTab': {'transform_type': '选择对当前曲线应用的数学变换，再运行查看变换名称、单位、点数和警告。q '
                                   '是曲线横坐标，越小通常对应越大的结构；原曲线保持不变。',
                 'output': '查看所选变换的单位、点数或方法警告，可选中文字复制。当前变换只显示摘要，不在此处绘图或导出完整变换数组。'},
 'SettingsDialog': {'q_unit': '选择默认导入 q 单位，保存后填入导入页；q 是曲线横坐标，越小通常对应越大的结构。Å⁻¹和 nm⁻¹须与文件一致，1 Å⁻¹=10 '
                              'nm⁻¹。',
                    'figure_format': '选择默认图像格式并保存，设置会记入配置文件。当前绘图页的实际导出格式仍由该页下拉框决定，请导出前核对。',
                    'show_error': '勾选并保存后，图中默认显示测量误差的上下短线，表示强度可能浮动的大小；文件没有误差列时不显示。',
                    'show_warnings': '选择并保存方法警告显示偏好；当前版本仅记录此设置，各分析输出仍会显示已有警告。取消勾选不会隐藏当前结果中的方法限制。',
                    'export_dir': '填写默认导出目录并保存；之后导出对话框从该位置开始选路径。保存设置不导出文件，批量自动分析的结果位置仍由其输入框决定。',
                    'log_level': '选择并保存日志级别偏好：INFO 为一般信息，WARNING 为警告，ERROR '
                                 '为错误。当前版本仅保存此设置，界面结果文本不按它过滤。',
                    'allow_slight_negative': '勾选并保存后，幅度和数量都低于下面限值的负强度只列为一般信息。原始数值会保留；需要正数的计算仍不能使用这些点。',
                    'slight_negative_abs_ratio': '填写负强度幅度的比例上限：最负值的大小除以正强度中位数（排序后中间的值）；没有正值时除以最大强度绝对值。保存后与下方比例共同判断。',
                    'slight_negative_fraction': '填写允许负值点占有效强度点的比例，0–1，例如 0.05 表示 '
                                                '5%。保存后与上面的幅度限值一起决定哪些负值只列为一般信息。',
                    'current_settings_view': '查看已生效的设置、配置文件路径及计算公式摘要，可选中文字复制。编辑输入框后需保存，再刷新核对；这里不直接修改设置。'},
 'CheckTab': {'output': '查看当前曲线的数值、重复值、误差列及负强度等检查结果，可选中文字复制。检查只报告问题，不自动修改数据；无警告不等于方法一定适用。'},
 'TemplatesTab': {'output': '查看模板加载、保存或应用结果，可选中文字复制。应用会对项目全部曲线运行模板，结果数量和状态显示在此；这里不编辑模板内容。'},
 'ExportTab': {'output': '查看导出是否完成、目标路径或失败原因，可选中文字复制。导出成功后按路径查找文件；这里不编辑曲线或已导出的文件。'},
 'ModelCatalogDialog': {'catalog_text': '查看绘图及分析方法的公式、输入、输出和适用条件，可选中文字复制。遇到不熟悉的方法时先核对该说明；这里是只读目录。'},
 'MainWindow': {'curve_list': '点选一条曲线后，检查、绘图、分析和导出都使用它；可先核对曲线名和单位。q 是曲线横坐标，越小通常对应越大的结构。'}}
OPTION_HELP: dict[str, dict[str, str]] = {'AnalysisTab.analysis_type': {'linear': '检查原始强度、负值和无法计算的点，显示检查结果；适合先了解这一段曲线的数据是否完整。',
                               'semilog': '把强度取对数，压缩数值跨度，检查其随横坐标的变化；只使用正强度，显示可用点数和变化范围。',
                               'loglog': '在横纵坐标都压缩成对数后，对近似直线的一段拟合；得到强度随横坐标增大而下降的快慢，需自行核对所选范围。',
                               'guinier': '对小横坐标处近似直线的一段拟合，估计结构中的散射位置离中心有多分散，即回转半径；需核对结果中的条件和警告。',
                               'kratky': '把强度乘以横坐标平方，计算所得曲线的峰位置、宽度和变化趋势，帮助比较样品；这些数值不能单独确定形状。',
                               'porod': '把强度乘以横坐标四次方，检查大横坐标处是否趋于平坦；用于查看材料交界处的散射特征，这里只输出曲线指标。',
                               'invariant': '计算横坐标平方乘强度在所选范围内的总面积，概括这一段的散射量；测量范围外没有计入。',
                               'local_slope': '计算曲线各处强度下降的快慢及其变化，帮助寻找变化规律不同的部分；需要正数，测量起伏会影响结果。'},
 'PlottingTab.plot_type': {'linear': '显示原始横坐标和强度，适合先看峰、背景及负值；可同时显示测量误差的上下短线和峰位置。',
                           'semilog': '对强度取对数，压缩纵坐标数值跨度，便于观察强度下降的趋势；零和负强度无法显示。',
                           'loglog': '横坐标和强度都取对数，压缩两轴数值跨度；强度按一定倍数衰减的部分会接近直线，零和负数无法显示。',
                           'guinier': '横坐标取平方，纵坐标显示强度对数；小横坐标处若接近直线，可进一步估计散射位置离中心的分散程度。',
                           'kratky': '纵坐标为原始强度乘横坐标平方，便于比较峰形和结构紧密程度相关的曲线变化；单凭图形不能确定形状。',
                           'porod': '纵坐标为强度乘横坐标四次方，检查大横坐标处是否趋于平坦，帮助分析材料交界处的特征。',
                           'invariant': '显示横坐标平方乘强度的曲线；对它求面积可以概括散射总量，选择这个图形本身不会计算面积。',
                           'local_slope': '显示曲线不同位置强度下降的快慢，帮助观察变化规律；原始测量中的起伏也会反映在图中。'},
 'PlottingTab.figure_preset': {'screen': '适合屏幕查看，导出时使用较小的图片文件、10 号字和较细线条。文件格式由旁边下拉框决定。',
                               'presentation': '适合汇报投影，导出时使用 12 号字和较粗线条，便于远处阅读。文件格式由旁边下拉框决定。',
                               'draft_publication': '适合论文初稿，导出时使用较高清晰度和 10 '
                                                    '号字；正式投稿前仍需按期刊要求核对尺寸和字号。'},
 'PlottingTab.figure_format': {'png': 'PNG 是像素图，适合预览和幻灯片；放大后可能出现像素。导出清晰度受所选预设分辨率影响，实际文件使用 .png 后缀。',
                               'svg': 'SVG 保存可缩放的矢量线条和文字，适合后续图形编辑；导出后可用支持 SVG 的工具打开，实际文件使用 .svg '
                                      '后缀。',
                               'pdf': 'PDF 保存矢量线条和页面，适合阅读、打印及排版；导出后可用 PDF 阅读器查看，实际文件使用 .pdf 后缀。'},
 'SettingsDialog.q_unit': {'A^-1': '表示 Å⁻¹，即埃的倒数；1 Å=0.1 nm，1 Å⁻¹=10 nm⁻¹。按文件实际单位选择，保存后作为导入页的默认单位。',
                           'nm^-1': '表示 nm⁻¹，即纳米的倒数；1 nm⁻¹=0.1 Å⁻¹。按文件实际单位选择，保存后作为导入页的默认单位。'},
 'SettingsDialog.figure_format': {'png': 'PNG 是像素图，适合屏幕预览和幻灯片；保存后记录为默认格式。当前绘图页仍需在其格式框中确认实际导出格式。',
                                  'svg': 'SVG 是可缩放矢量图，适合后续编辑线条和文字；保存后记录为默认格式。当前绘图页实际格式仍由该页格式框决定。',
                                  'pdf': 'PDF 适合阅读、打印和排版，并保留矢量线条；保存后记录为默认格式。当前绘图页实际格式仍由该页格式框决定。'},
 'SettingsDialog.log_level': {'INFO': '一般信息级别，通常包含进度、警告和错误；保存后记录此偏好。当前版本没有用它过滤界面输出，结果文本仍完整显示。',
                              'WARNING': '警告级别，通常用于只关注警告和错误；保存后记录此偏好。当前版本没有用它过滤界面输出，结果文本仍完整显示。',
                              'ERROR': '错误级别，通常用于只关注执行失败；保存后记录此偏好。当前版本没有用它过滤界面输出，结果文本仍完整显示。'},
 'DeepAnalysisTab.sample_type': {'unknown': '不确定样品类型就选它；运行通用分析及内部两点距离分布，不按两相或层片条件计算相关函数，不会自动认定结构。',
                                 'particle': '已知颗粒样品时选它；运行包括内部两点距离分布在内的分析。具体形状须另外选模型，选择类型不证明颗粒形状。',
                                 'polymer': '已知聚合物样品时选它；运行内部两点距离分布等分析。要尝试链模型需另选 '
                                            'gaussian_chain，即随机曲折的理想链。',
                                 'two_phase': '已知存在两种散射能力不同的区域时选两相；计算结构随距离的关联，不计算颗粒内部两点距离分布。',
                                 'lamellar': '已知重复层状结构时选层片；检查重复距离及结构随距离的关联。选择不会证明样品存在层片，仍需复核峰和警告。',
                                 'fractal': '要检验一定尺度内近似自相似的结构时选分形；检查强度衰减指数，不计算颗粒内部两点距离分布。'},
 'AutoBatchTab.sample_type': {'unknown': '不确定样品类型就选未知/通用；执行通用方法。勾选 P(r) 后可计算内部两点距离分布，不会自动认定结构。',
                              'particle': '已知颗粒样品时选它；采用颗粒适用方法，勾选 P(r) 后计算内部两点距离分布。选择不证明具体形状或粒径。',
                              'polymer': '已知聚合物样品时选它；采用相应方法，勾选 P(r) 后计算内部两点距离分布。仍需结合样品条件解释结果。',
                              'two_phase': '已知两种散射能力不同的区域共存时选两相；勾选相关函数后计算结构随距离的关联，仍需复核结果条件。',
                              'lamellar': '已知重复层状结构时选层片；检查重复距离，勾选相关函数后计算结构随距离的关联，仍需复核峰和警告。'},
 'DeepAnalysisTab.shape_model': {'none': '不进行形状模型拟合，仍运行样品类型适用的其他深度分析；适合先检查数据、区间和方法条件，再决定尝试哪些结构模型。',
                                 'sphere': '假设颗粒都是同样大小的球，估计半径、强度比例及可选背景；拟合良好也需结合已知样品判断形状。',
                                 'core_shell_sphere': '假设颗粒有球形内核和外壳，估计内核半径、外壳厚度及两者散射能力的差别；这些数值会相互影响。',
                                 'ellipsoid': '假设颗粒是拉长或压扁的球，即椭球，且朝向随机；拟合长短方向的半径，尺寸取决于这一形状假设。',
                                 'cylinder': '假设颗粒是朝向随机的圆柱，估计半径和长度；请检查测量范围是否足以区分这两个尺寸。',
                                 'disk': '用很短的圆柱代表薄圆盘，估计半径和厚度；所得尺寸取决于圆盘形状和随机朝向的假设。',
                                 'gaussian_chain': '假设聚合物链随机曲折且符合理想链统计规律，拟合链段围绕中心的距离尺度；用于检验该链结构假设。',
                                 'dab': '假设两种散射能力不同的材料在样品中随机分布，估计密度变化随距离减弱的快慢；它不直接给出颗粒半径。',
                                 'mass_fractal': '假设结构在一定大小范围内放大后仍相似，估计质量随结构大小增长的快慢和这种规律终止的距离。',
                                 'surface_fractal': '假设材料交界处的粗糙形状在一定大小范围内相似，估计粗糙程度；需要选择强度下降规律较稳定的一段。',
                                 'lamellar_peak_stack': '假设重复层状结构产生一组等倍数位置的峰，每个峰呈钟形；估计峰的位置、宽度和层间重复距离。'},
 'BatchTab.comparison_type': {'difference': '计算 B−A，正值表示 B '
                                            '的强度更大，负值表示更小；输出保留强度单位。曲线先在共同范围对齐，原始数据保持不变。',
                              'ratio': '计算 B/A：1 表示相同，大于 1 表示 B 强度更大，输出无单位。A 为零或接近零时排除相应点并给出警告。',
                              'relative_difference': '计算 (B−A)/A：0 表示相同，0.1 表示 B 高 10%，输出无单位。A '
                                                     '为零或接近零时排除相应点并给出警告。'},
 'RecordsTab.source_type': {'curve': '列出已导入或生成的曲线供选择；选中具体曲线再标记后，其来源和完整范围会纳入正式记录，便于报告追踪。',
                            'analysis_result': '列出已生成的分析结果供选择；选中具体结果再标记后，记录其分析类型和标识，便于报告追踪，标记不重新计算。',
                            'comparison_result': '列出已完成的曲线比较结果供选择；选中具体结果再标记后，纳入正式记录供报告追踪，原始曲线保持不变。',
                            'figure': '图像正式记录入口目前预留，选择后只显示占位项，没有可标记的图像；需要图像文件时请使用绘图页的图像导出功能。'},
 'AdvancedTab.transform_type': {'q_to_size': '把原始横坐标换算成结构距离，数值越小对应距离越大；埃或纳米取决于原始单位，所得距离不等于直接测得的粒径。',
                                'q_squared': '对原始横坐标求平方，查看换算后的单位、点数和注意事项；可用于检查小横坐标区域的强度变化。',
                                'lnI': '对正强度取自然对数，压缩数值跨度，查看换算摘要；零和负数无法换算，会在结果中排除，原始数据保留。',
                                'log10I': '对正强度取十进对数，压缩数值跨度，查看换算摘要；零和负数无法换算，原始数据保留。',
                                'qI': '逐点把横坐标乘以强度，显示换算后的单位和点数，便于观察重新放大不同部分后曲线的变化。',
                                'q2I': '逐点把横坐标平方乘以强度，显示换算摘要，可用于观察峰形或准备计算散射总量；这里不会求面积。',
                                'q3I': '逐点把横坐标三次方乘以强度，显示换算后的单位和点数；大横坐标部分会被更明显地放大。',
                                'q4I': '逐点把横坐标四次方乘以强度，显示换算摘要；可用于检查大横坐标处是否趋于平坦，这里只显示计算摘要。',
                                'normalized_I': '每个强度除以当前曲线的最大强度，得到无单位的相对值；适合比较曲线形状，最大值为零时无法计算并给出警告。'}}
ACTION_HELP: dict[str, str] = {'设置': '打开设置窗口，选择以后导入和导出时使用的默认单位、图像格式、误差显示方式和保存位置。',
 '新建项目': '开始一个空项目；当前项目有未保存更改时，会先询问是否保存，再清空当前项目。',
 '打开项目...': '选择含 project.json 的项目文件夹；这个文件保存程序设置和数据清单，打开后恢复曲线与记录。',
 '保存项目': '保存当前曲线、分析结果和操作记录，便于以后接着使用；首次保存时需要选择项目文件夹。',
 '另存为项目...': '选择另一个项目文件夹，保存当前曲线、分析结果和操作记录，便于以后重新打开。',
 '保存': '先保存当前项目的曲线、分析结果和记录，再继续新建项目、打开另一个项目或关闭窗口。',
 '不保存': '放弃当前项目尚未保存的更改，然后继续新建项目、打开另一个项目或关闭窗口。',
 '取消': '请求停止后续批量分析；正在计算的部分结束后停止，已完成结果会保存，并注明分析未完成。',
 'Save default settings JSON': '把本窗口设置写入 JSON 设置文件（保存程序设置），供下次启动使用，并更新当前导入单位和误差显示。',
 'Refresh current settings view': '重新显示已保存并生效的设置、文件位置和读取情况；修改输入框后，需要先保存才能在此看到新值。',
 'View calculation models and formulas': '查看各分析方法的公式、所需数据、计算结果和适用条件，帮助判断当前曲线是否适合该方法。',
 'Close': '关闭方法与公式目录，返回设置窗口。',
 '选择数据文件': '选择带横坐标和强度列的表格或文本文件；软件会尝试识别列名并显示预览，确认后再点击导入。',
 '导入曲线': '先确认文件、横坐标和强度列、单位与曲线横坐标范围；点击后读取数据，将曲线及来源加入项目。',
 '预览/诊断当前文件': '先选择文件；按当前列名、单位与曲线横坐标范围显示前几行数据，并列出重复值、缺失值等问题。',
 '批量导入曲线文件': '选择多个曲线文件，按文件名中的数字顺序读取；按当前曲线横坐标范围加入项目，并列出读取失败的文件。',
 '当前曲线 q 转为 nm^-1': '先在左侧选择曲线；将横坐标单位换为倒数纳米（nm⁻¹），换算数值后新增一条曲线，保留原曲线。',
 '当前曲线 q 转为 A^-1': '先在左侧选择曲线；将横坐标单位换为倒数埃（Å⁻¹），换算数值后新增一条曲线，保留原曲线。',
 '检查当前曲线': '先选择曲线；检查横坐标、强度、误差（测量值的不确定程度）、重复点和无法用于计算的数值。',
 'Plot current curve': '先选择曲线；按当前图类型、显示选项及横纵坐标范围重新绘图，便于查看当前曲线的形状。',
 'Use this view for analysis': '将当前图对应的分析方法填入分析区域；核对曲线横坐标范围后，再点击运行曲线分析。',
 'Export current figure': '先绘制曲线；选择文件位置，按已选的清晰度、尺寸和文件格式保存当前显示的图。',
 'Auto range': '清空横纵坐标的范围输入，重新绘图，让软件根据曲线数据自动确定适合显示的范围。',
 'Full q': '先选择曲线；把绘图横坐标范围设为全部可用数据点所在的范围，便于查看完整曲线。',
 'Low q': '先选择曲线；显示按横坐标从小到大排列后，前约三分之一的数据点，不按范围跨度平均分段。',
 'Mid q': '先选择曲线；显示按横坐标从小到大排列后，中间约三分之一的数据点，不按范围跨度平均分段。',
 'High q': '先选择曲线；显示按横坐标从小到大排列后，后约三分之一的数据点，不按范围跨度平均分段。',
 'Display range': '展开或收起显示范围设置；展开后可填写横纵坐标上下限，或选择低、中、高横坐标部分。',
 'Figure export': '展开或收起图像保存设置；选择清晰度、尺寸和格式后，再点击导出当前图，选择保存位置。',
 '运行曲线分析': '先选择曲线和分析方法，确认曲线横坐标范围；软件检查数据能否计算后，运行所选方法并保存结果与操作记录。',
 '使用当前曲线 q 范围': '先选择曲线；把完整曲线横坐标范围填入本页输入框，再根据所选方法检查是否需要缩小范围。',
 '检查当前 q 范围': '检查所选曲线横坐标范围内的点数和数值，提示所选方法能否计算；需要正强度的方法会检查强度是否大于零。',
 '使用曲线绘图区域 x 范围换算为 q': '先绘制曲线；把图上横坐标范围换算回曲线原有横坐标，取其中有数据的部分，填入分析框。',
 '查看对应图': '把绘图区域切换为当前分析方法对应的图，重新显示曲线，便于检查准备分析的部分。',
 '自动识别 q 区间': '展开或收起区间查找工具；确认曲线横坐标范围后，点击识别区间，查看推荐范围和注意事项。',
 '识别区间': '先选择曲线并确认曲线横坐标范围；查找可能适合分析的部分，显示推荐范围与评分，再由你核对。',
 '使用当前曲线完整 q 范围': '先选择曲线；把完整曲线横坐标范围填入分析框，随后可查找适合分析的部分或运行分析。',
 '将该区间填入 q_min/q_max': '先在推荐区间表中选一行；把该行的曲线横坐标范围填入分析输入框，供随后运行分析使用。',
 '使用该区间拟合/计算': '先选推荐区间并检查输入框范围；运行推荐方法并保存结果。输入框与推荐范围不同时，可能使用输入框范围。',
 '导出候选区表': '先识别区间；选择保存位置，把当前推荐区间及其评分保存为 CSV 表格文件（Excel 可打开）。',
 '刷新曲线列表': '重新显示项目里已有的曲线，更新曲线 A、B 的选项及测量顺序表，便于选用刚导入或新增的曲线。',
 '刷新序列表': '根据当前曲线和来源重新显示测量顺序、测量序号、曲线横坐标范围、数据点数和注意事项。',
 '按序列顺序选择全部': '在测量顺序表和曲线列表中选中全部曲线，随后可按表中顺序建组或生成平均曲线。',
 '从选中行建组': '先在测量顺序表中选行并填写组名；按表中顺序把这些曲线记录为一组，便于一起管理。',
 '导出序列索引 CSV': '选择保存位置，把曲线测量顺序、测量序号、横坐标范围和注意事项保存为 CSV 表格文件（Excel 可打开）。',
 '将选中曲线建组': '先在曲线列表中选择多条曲线并填写组名；将它们记录为一组，保留顺序，便于一起管理。',
 '平均选中曲线': '先选至少两条可用于重复测量平均的曲线；换算到相同横坐标取值后求平均，新增平均曲线并保留原曲线。',
 '比较曲线 A/B': '先选择不同的曲线 A、B 和比较方式；换算到相同横坐标取值后，计算强度差、强度比或强度差占 A 的比例。',
 '选择数据文件夹': '选择存放曲线数据的文件夹，供后续批量读取；确认分析设置后，再点击开始全自动分析并导出。',
 '选择结果位置': '选择存放结果的上级文件夹；开始分析后，软件会在里面新增本次分析的结果文件夹。',
 '开始全自动分析并导出': '先确认数据和结果位置、批次名、样品类型及曲线横坐标范围；后台计算并保存结果，显示哪些完成、哪些失败。',
 '一键深度分析': '先确认曲线横坐标范围、样品类型和模型设置；运行多项分析，其中部分结果通过假定样品形状或估计测量范围外的强度得到。',
 '运行高级变换': '先选择曲线和换算方式；显示换算后的单位、点数及注意事项，供查看，原曲线保留，结果只在本页显示。',
 'P(r) experimental 预留接口': '用深度分析估计样品内部距离分布；这个入口尚未启用。距离分布指样品内部两点之间不同距离出现的程度。',
 '相关函数分析': '用深度分析估计样品内部不同距离处的密度变化是否相近；这个独立入口尚未启用，需要选择适合的样品类型。',
 '显示方法边界 warning 示例': '查看示例，了解不同计算方法在数据不足或适用条件不满足时会提示什么；这些是教学示例，需要另行检查当前曲线。',
 '标记为正式记录': '先选择已有曲线、分析结果或比较结果；把该对象加入正式记录列表，便于后续报告引用，仍需自行核对结论。',
 '取消选中正式记录': '先在正式记录列表选中一项；取消该项正式标记，并留下操作记录，来源曲线和分析结果仍保留。',
 '刷新记录': '重新显示当前项目的操作历史、正式记录和可选择的来源对象，便于查看刚完成的操作。',
 '保存默认模板': '选择位置，将当前模板保存为 JSON 模板文件（保存程序设置）；加载过模板后保存该模板，不是当前分析框内容。',
 '加载模板': '选择 JSON 模板文件（保存程序设置），读入分析范围和方法选项，随后可应用到项目全部曲线。',
 '应用模板到全部曲线': '先导入曲线，确认模板中的曲线横坐标范围和启用方法；依次分析全部曲线，保存结果与操作记录。',
 '导出当前曲线 CSV': '先选择曲线和文件夹；把横坐标、强度及已有误差保存为 CSV 表格文件（Excel 可打开），同名文件会询问是否覆盖。',
 '导出 feature_table.csv': '选择文件夹，把项目曲线信息及已有分析结果汇总为 CSV 表格文件（Excel 可打开），便于逐条比较。',
 '导出 Origin 长表': '选择文件夹，把全部曲线逐点保存为表格，每行一个数据点，附使用说明，便于用 Origin 绘图软件分组绘图。',
 '导出 Origin 矩阵表': '全部曲线的横坐标取值须一致；选择文件夹，保存共用横坐标列、每条曲线各占一列的表格，供 Origin 绘图软件使用。',
 '导出当前曲线转换数据 CSV...': '先选择曲线和文件夹；把原数据及横坐标平方等换算结果保存为 CSV 表格文件（Excel 可打开），方便后续绘图。',
 '刷新曲线图': '先选择曲线；按当前图类型、显示选项及横纵坐标范围重新绘图，便于查看当前曲线的形状。',
 '用于当前分析': '将当前图对应的分析方法填入分析区域；核对曲线横坐标范围后，再点击运行曲线分析。',
 '导出当前图像': '先绘制曲线；选择文件位置，按已选的清晰度、尺寸和文件格式保存当前显示的图。',
 '自动范围': '清空横纵坐标的范围输入，重新绘图，让软件根据曲线数据自动确定适合显示的范围。',
 '完整 q': '先选择曲线；把绘图横坐标范围设为全部可用数据点所在的范围，便于查看完整曲线。',
 '低 q': '先选择曲线；显示按横坐标从小到大排列后，前约三分之一的数据点，不按范围跨度平均分段。',
 '中 q': '先选择曲线；显示按横坐标从小到大排列后，中间约三分之一的数据点，不按范围跨度平均分段。',
 '高 q': '先选择曲线；显示按横坐标从小到大排列后，后约三分之一的数据点，不按范围跨度平均分段。',
 '显示范围': '展开或收起显示范围设置；展开后可填写横纵坐标上下限，或选择低、中、高横坐标部分。',
 '图像导出': '展开或收起图像保存设置；选择清晰度、尺寸和格式后，再点击导出当前图，选择保存位置。',
 '保存并应用设置': '把本窗口设置写入 JSON 设置文件（保存程序设置），供下次启动使用，并更新当前导入单位和误差显示。',
 '刷新设置摘要': '重新显示已保存并生效的设置、文件位置和读取情况；修改输入框后，需要先保存才能在此看到新值。',
 '查看计算模型与公式': '查看各分析方法的公式、所需数据、计算结果和适用条件，帮助判断当前曲线是否适合该方法。',
 '关闭': '关闭方法与公式目录，返回设置窗口。',
 '项目': '点击选择新建、打开或保存项目；项目文件可以保留曲线、分析结果和操作记录，便于以后继续使用。'}
TAB_HELP: dict[str, str] = {'数据导入': '选择有横坐标和强度列的一维曲线文件，确认单位与读取范围，导入项目后检查重复点、缺失值等问题。',
 '导入数据': '先选择文件，确认横坐标列、强度列、单位与曲线横坐标范围，查看前几行数据后再导入。',
 '文件预览与诊断': '查看哪些列将作为横坐标和强度、前几行数据及发现的问题；修改读取设置后点击预览，更新显示。',
 '操作日志': '查看文件读取、曲线导入、批量导入和单位换算的过程，了解哪些操作已完成，哪些文件读取失败。',
 '数据检查': '选择已导入曲线，检查横坐标、强度、误差（测量值的不确定程度）、重复点和无法计算的数值。',
 '曲线工作台': '左侧查看曲线图，右侧选择方法并分析；图中横坐标可经过换算，分析输入框使用曲线原有横坐标范围。',
 '高级功能': '按需要选择曲线换算、同时运行多项分析、曲线分组比较，或从文件夹读取全部曲线后计算并保存结果。',
 '高级方法': '选择曲线换算方式，查看换算结果和方法注意事项示例；样品内部距离分布等分析需使用深度分析入口。',
 '深度分析': '根据曲线横坐标范围、样品类型和假定形状运行多项分析；部分结果会估计测量范围外的强度，需核对假设。',
 '批量比较': '查看测量顺序、把曲线建成组、生成平均曲线或比较两条曲线；计算前会换算到相同横坐标取值。',
 '全自动批量分析': '选择曲线文件夹和保存位置，后台运行适合的分析并保存结果；完成后查看每项计算是否成功及其适用条件。',
 '项目与输出': '查看操作历史和已标记的正式记录，保存曲线与分析表，或保存、加载模板并用于全部曲线。',
 '历史与正式记录': '查看操作历史，把已有曲线、分析或比较结果标记为后续报告引用的正式记录；手动添加图像的入口尚未启用。',
 '导出报告': '保存曲线、分析结果汇总和换算数据的表格，也可保存供 Origin 绘图软件使用的表格，便于后续整理报告。',
 '分析模板': '保存或加载 JSON 模板文件（保存程序设置），确认其中的曲线横坐标范围与方法后，应用到项目全部曲线。'}

OBJECT_HELP = {
    "curveSearch": "输入曲线名称的一部分，左侧只显示匹配的曲线；清空后重新显示全部曲线。",
    "curveCount": "这里显示当前列表中的曲线数量；搜索时可以查看匹配了多少条曲线。",
    "curveSummary": "这里显示当前选中曲线的点数、横坐标范围和单位，便于确认接下来处理哪条曲线。",
    "sidebarImportButton": "打开数据导入页；在该页选择曲线文件、检查列名，再导入项目。",
    "sidebarPlotButton": "打开曲线绘图区域，查看左侧选中曲线的图形。",
    "plotOptionsToggle": "点击展开或收起图中横纵坐标的显示范围设置；收起后仍使用已填写的范围。",
    "plotExportToggle": "点击展开或收起图片导出设置；展开后可选择图片用途、格式并保存当前图形。",
    "autoRegionToggle": "点击展开或收起区间识别工具；展开后可寻找曲线上适合分析的部分。",
    "rangeOptionsToggle": "点击展开或收起图中横纵坐标的显示范围设置；收起后仍使用已填写的范围。",
    "figureExportToggle": "点击展开或收起图片导出设置；展开后可选择图片用途、格式并保存当前图形。",
    "plotCoordinateReadout": "把鼠标移到曲线图内，这里会显示鼠标位置的横坐标和纵坐标数值。",
}

INTERNAL_BUTTON_HELP = {
    "ScrollLeftButton": "点击显示左边被隐藏的分页标签，然后选择要打开的页面。",
    "ScrollRightButton": "点击显示右边被隐藏的分页标签，然后选择要打开的页面。",
    "qt_menubar_ext_button": "点击查看窗口宽度不足时被隐藏的菜单。",
    "qt_tableview_cornerbutton": "点击选中表格中允许选择的全部行；可选行数取决于该表格的选择方式。",
    "qt_clear_button": "点击清空这个输入框中的文字，随后可重新输入。",
}

TABLE_HEADER_HELP = {
    "类型": "该行建议使用的分析方法；点击这一行可查看理由。",
    "q 范围": "该区间在原始曲线横坐标上的起止值，单位与曲线一致。",
    "d 范围": "由横坐标换算出的长度范围，帮助估计这一段曲线对应的结构尺度。",
    "点数": "这一段曲线中可以用于分析的数据点数量。",
    "评分": "程序按曲线表现给出的区间推荐分数；分数高不代表结构已被证实。",
    "等级": "程序对这一候选区间的可用程度判断；结合警告决定是否采用。",
    "推荐操作": "程序建议对这一段曲线使用的计算方法；选中该行后可运行。",
    "警告": "采用该区间前需要检查的问题，选中这一行可查看说明。",
    "sequence_order": "按文件序列信息排列后的位置，便于按测量顺序选取曲线。",
    "project_order": "这条曲线在项目中的原有位置。",
    "curve_id": "程序用来区分曲线的编号；名称相同时仍可据此分辨。",
    "curve_name": "这条曲线的名称。",
    "source_file": "导入这条曲线时使用的文件路径，便于查找原始文件。",
    "source_stem": "原始文件去掉扩展名后的名称。",
    "series_id": "这条曲线所属的一组连续测量的编号。",
    "frame_label": "这次测量的标签；一帧表示一次记录下来的测量。",
    "frame_index": "这次测量在连续测量中的序号。",
    "q_unit": "曲线横坐标的单位，用来解释范围数值和结构尺度。",
    "intensity_unit": "曲线纵坐标，即散射强度的单位。",
    "point_count": "这条曲线包含的数据点数量。",
    "q_min": "这条曲线横坐标的最小值，单位见横坐标单位列。",
    "q_max": "这条曲线横坐标的最大值，单位见横坐标单位列。",
    "warnings": "这条曲线需要检查的问题；提示不会自动删除数据。",
}

EDIT_ACTION_HELP = {
    "Undo": "撤销刚才对文字的修改。",
    "Redo": "重新应用刚才撤销的文字修改。",
    "Cut": "将选中的文字移到剪贴板，可粘贴到其他位置。",
    "Copy": "将选中的文字复制到剪贴板，可粘贴到其他位置。",
    "Paste": "将剪贴板中的文字放到当前输入位置。",
    "Delete": "删除当前选中的文字。",
    "Select All": "选中这个区域中的全部文字，随后可复制。",
    "Clear": "清空这个输入框中的文字，随后可重新输入。",
}


def _action_key(text: str) -> str:
    return " ".join(text.split("\t")[0].replace("&", "").replace("…", "...").strip().split())


def _set_help(widget: QWidget, text: str) -> None:
    apply_help(widget, tooltip=text, status_tip=text, duration_ms=12000)
    if isinstance(widget, QAbstractItemView):
        apply_help(widget.viewport(), tooltip=text, status_tip=text, duration_ms=12000)
    elif isinstance(widget, QAbstractSpinBox):
        # The text editor receives focus and hover events inside a spin box.
        apply_help(widget.lineEdit(), tooltip=text, status_tip=text, duration_ms=12000)


def _choice_help(combo: QComboBox, index: int) -> str:
    choices = combo.property("plainHelpChoices") or {}
    key = str(combo.itemData(index)) if combo.itemData(index) is not None else combo.itemText(index)
    return choices.get(key) or choices.get(combo.itemText(index)) or combo.property("plainHelpBase") or ""


_CHOICE_DETAIL_ROLE = Qt.UserRole + 78
_GENERATED_HELP_ROLE = Qt.UserRole + 79


def _update_choices(combo: QComboBox) -> None:
    for index in range(combo.count()):
        text = _choice_help(combo, index)
        choices = combo.property("plainHelpChoices") or {}
        key = str(combo.itemData(index)) if combo.itemData(index) is not None else combo.itemText(index)
        defined_choice = key in choices or combo.itemText(index) in choices
        current = combo.itemData(index, Qt.ToolTipRole)
        generated = combo.itemData(index, _GENERATED_HELP_ROLE)
        if not defined_choice and current and current != generated:
            combo.setItemData(index, current, _CHOICE_DETAIL_ROLE)
        detail = combo.itemData(index, _CHOICE_DETAIL_ROLE) if not defined_choice else None
        if detail and detail != text:
            text = f"{text}\n对象编号和来源：\n{detail}"
        if combo.itemData(index, Qt.ToolTipRole) != text:
            combo.setItemData(index, text, _GENERATED_HELP_ROLE)
            combo.setItemData(index, text, Qt.ToolTipRole)
    base = combo.property("plainHelpBase") or ""
    choice = combo.itemData(combo.currentIndex(), Qt.ToolTipRole) if combo.currentIndex() >= 0 else ""
    if choice and choice.startswith(base):
        text = choice
    elif choice:
        text = f"{base}\n当前选项：{choice}"
    else:
        text = base
    _set_help(combo, text)


def _configure_combo(combo: QComboBox, text: str, choices: dict[str, str]) -> None:
    combo.setProperty("plainHelpBase", text)
    combo.setProperty("plainHelpChoices", choices)
    if not combo.property("plainHelpConnected"):
        combo.currentIndexChanged.connect(lambda _index: _update_choices(combo))
        # Refresh after later data-source lists are rebuilt, without changing selection.
        combo.model().rowsInserted.connect(lambda *_args: _update_choices(combo))
        combo.model().dataChanged.connect(
            lambda _first, _last, roles: _update_choices(combo)
            if not roles or any(role in roles for role in (Qt.DisplayRole, Qt.UserRole, Qt.ToolTipRole)) else None
        )
        combo.setProperty("plainHelpConnected", True)
    _update_choices(combo)


def refresh_ui_help(root: QWidget) -> None:
    """Apply help to the current widget tree, including a newly opened dialog."""
    widgets = [root, *root.findChildren(QWidget)]
    for owner in widgets:
        class_name = type(owner).__name__
        for attribute, text in FIELD_HELP.get(class_name, {}).items():
            control = getattr(owner, attribute, None)
            if not isinstance(control, QWidget):
                continue
            if isinstance(control, QComboBox):
                choices = OPTION_HELP.get(f"{class_name}.{attribute}", OPTION_HELP.get(attribute, {}))
                _configure_combo(control, text, choices)
            else:
                _set_help(control, text)

    for widget in widgets:
        text = OBJECT_HELP.get(widget.objectName())
        if isinstance(widget, QAbstractButton):
            text = text or INTERNAL_BUTTON_HELP.get(widget.objectName()) or ACTION_HELP.get(_action_key(widget.text()))
            if not text and isinstance(widget.parentWidget(), QLineEdit) and widget.parentWidget().isClearButtonEnabled():
                text = "点击清空这个输入框中的文字，随后可重新输入。"
        if text:
            _set_help(widget, text)
        if isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                text = TAB_HELP.get(widget.tabText(index))
                if text:
                    widget.setTabToolTip(index, text)
                    widget.setTabWhatsThis(index, text)
        elif isinstance(widget, QTableWidget):
            for column in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(column)
                if item is not None and item.text() in TABLE_HEADER_HELP:
                    item.setToolTip(TABLE_HEADER_HELP[item.text()])
            _set_help(widget.horizontalHeader(), widget.toolTip())
        elif isinstance(widget, QSplitter):
            for index in range(1, widget.count()):
                _set_help(widget.handle(index), "按住这条分隔线左右或上下拖动，调整两侧区域的大小。")
        elif isinstance(widget, QScrollBar):
            _set_help(widget, "拖动滑块或点击两端箭头，查看这个区域中被遮住的内容。")
        elif isinstance(widget, QGroupBox) and widget.isCheckable():
            _set_help(widget, "勾选后启用这组设置，取消勾选后停用；已填写的值会保留。")

    for action in root.findChildren(QAction):
        text = ACTION_HELP.get(_action_key(action.text())) or EDIT_ACTION_HELP.get(_action_key(action.text()))
        if not action.text() and action.shortcut().toString() == "Ctrl+F":
            text = "按 Ctrl+F 跳到曲线搜索框，输入名称或单位可缩小左侧曲线列表。"
        elif action.objectName() == "_q_qlineeditclearaction":
            text = "点击清空这个输入框中的文字，随后可重新输入。"
        if text:
            action.setToolTip(text)
            action.setStatusTip(text)
            action.setWhatsThis(text)
    for menu in root.findChildren(QMenu):
        menu.setToolTipsVisible(True)
    if isinstance(root, QMenu):
        root.setToolTipsVisible(True)
    if isinstance(root, QMessageBox):
        _configure_message_box(root)
    elif isinstance(root, QFileDialog):
        _configure_file_dialog(root)


def _configure_message_box(dialog: QMessageBox) -> None:
    for button in dialog.buttons():
        key = _action_key(button.text())
        if key in {"保存", "Save"}:
            text = "先保存当前项目，再继续刚才的操作；首次保存时需要选择项目文件夹。"
        elif key in {"不保存", "Discard", "Don't Save"}:
            text = "放弃当前项目尚未保存的更改，继续刚才的操作；这些更改将无法从项目文件恢复。"
        elif dialog.buttonRole(button) == QMessageBox.RejectRole:
            text = "取消这次操作并返回原界面，保留当前项目内容。"
        elif dialog.standardButton(button) == QMessageBox.No:
            text = "拒绝弹窗中说明的写入操作，保留已有文件。"
        elif dialog.standardButton(button) == QMessageBox.Yes:
            text = "确认弹窗中说明的写入操作；请先核对目标文件或文件夹。"
        else:
            text = "关闭这条提示，返回原界面。"
        _set_help(button, text)


def _configure_file_dialog(dialog: QFileDialog) -> None:
    for button in dialog.findChildren(QAbstractButton):
        name = button.objectName()
        key = _action_key(button.text()).lower()
        text = {
            "backButton": "返回刚才浏览过的文件夹。",
            "forwardButton": "回到刚才从中返回的文件夹。",
            "toParentButton": "打开当前文件夹的上一级文件夹。",
            "newFolderButton": "在当前位置新建一个文件夹。",
            "listModeButton": "将文件显示为简洁的名称列表。",
            "detailModeButton": "显示文件名称、大小和修改时间等信息。",
        }.get(name)
        if key in {"cancel", "取消"}:
            text = "关闭文件选择窗口，取消这次选择。"
        elif key in {"open", "打开", "choose", "选择", "save", "保存"}:
            text = "确认当前文件或文件夹，继续刚才的导入、加载或保存操作。"
        if text:
            _set_help(button, text)
    for edit in dialog.findChildren(QLineEdit):
        _set_help(edit, "输入或选择文件、文件夹的名称或路径，再点击确认按钮。")
    for combo in dialog.findChildren(QComboBox):
        _set_help(combo, "展开列表选择文件位置或文件类型，文件列表会随选择更新。")
    for view in dialog.findChildren(QAbstractItemView):
        _set_help(view, "点击选中文件或文件夹；双击文件夹可进入，确认后用于刚才的操作。")


class _HelpController(QObject):
    def __init__(self, root: QWidget) -> None:
        super().__init__(root)
        self.root = root

    def _belongs_to_root(self, widget: QWidget) -> bool:
        if not isValid(self.root) or not isValid(widget):
            return False
        # QWidget.isAncestorOf excludes dialogs that have their own native window.
        parent: QObject | None = widget
        while parent is not None:
            if parent is self.root:
                return True
            parent = parent.parent()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if event_type == QEvent.Show:
            if watched is not self.root and not isinstance(watched, (QDialog, QMenu)):
                return False
        elif event_type == QEvent.KeyPress:
            if event.key() != Qt.Key_F1:
                return False
        else:
            return False
        if not isinstance(watched, QWidget) or not self._belongs_to_root(watched):
            return False
        if event_type == QEvent.Show:
            refresh_ui_help(watched)
        else:
            target = watched
            while target is not None and self._belongs_to_root(target):
                if isinstance(target, QTabBar):
                    text = target.tabWhatsThis(target.currentIndex()) or target.tabToolTip(target.currentIndex())
                else:
                    text = target.whatsThis() or target.toolTip()
                if text:
                    QWhatsThis.showText(target.mapToGlobal(target.rect().bottomLeft()), text, target)
                    return True
                target = target.parentWidget()
        return False


def install_ui_help(root: QWidget) -> None:
    """Install hover, status and F1 help for this window and its dialogs."""
    refresh_ui_help(root)
    if not getattr(root, "_plain_help_controller", None):
        controller = _HelpController(root)
        root._plain_help_controller = controller
        QApplication.instance().installEventFilter(controller)
