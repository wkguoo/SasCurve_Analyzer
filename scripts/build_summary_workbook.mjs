import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const cliArgs = process.argv.slice(2);
const compactAfterExport = cliArgs.includes("--compact");
const positionalArgs = cliArgs.filter((value) => !value.startsWith("--"));
if (!positionalArgs[0]) {
  throw new Error("Usage: node build_summary_workbook.mjs <result-directory> [--compact]");
}
const outputDir = path.resolve(positionalArgs[0] || "");

const previewDir = path.join(
  path.dirname(outputDir),
  ".sax_summary_previews",
  path.basename(outputDir),
);

const csvSources = [
  ["input_manifest", ["audit/input_manifest_original.csv", "summary/input_manifest.csv", "input_manifest_original.csv", "review/input_manifest_original.csv", "review/summary/input_manifest.csv", "review/audit/input_manifest.csv"]],
  ["source_integrity", ["audit/source_integrity_after_analysis.csv", "source_integrity_after_analysis.csv", "review/source_integrity_after_analysis.csv"]],
  ["data_quality", ["summary/data_quality.csv", "data_quality.csv", "review/data_quality.csv"]],
  ["accepted_parameters", ["summary/accepted_parameters.csv", "accepted_parameters.csv", "review/accepted_parameters.csv"]],
  ["reliable_parameters", ["final_results.csv", "reliable_parameters.csv", "review/reliable_parameters.csv", "review/summary/reliable_parameters.csv"]],
  ["adaptive_parameters", ["audit/workbook_sources/adaptive_parameters_workbook.csv", "adaptive_parameters_workbook.csv"]],
  ["common_parameters", ["audit/workbook_sources/common_parameters_workbook.csv", "common_parameters_workbook.csv"]],
  ["fit_quality", ["audit/workbook_sources/analysis_inventory_workbook.csv", "analysis_inventory_workbook.csv", "audit/fit_quality.csv", "fit_quality.csv", "review/audit/fit_quality.csv"]],
  ["candidate_windows", ["audit/workbook_sources/candidate_windows_workbook.csv", "candidate_windows_workbook.csv", "audit/candidate_windows.csv", "candidate_windows.csv", "review/audit/candidate_windows.csv"]],
  ["range_audit", ["audit/range_audit.csv", "range_audit.csv", "review/audit/range_audit.csv"]],
  ["consensus_regions", ["audit/consensus_regions.csv", "consensus_regions.csv", "review/audit/consensus_regions.csv"]],
  ["sequence_frames", ["sequence_frame_table.csv", "summary/sequence_frame_table.csv", "audit/sequence_frame_table.csv", "review/summary/sequence_frame_table.csv", "review/audit/sequence_frame_table.csv"]],
  ["sequence_parameters", ["sequence_parameter_trajectories.csv", "audit/sequence_parameter_trajectories.csv", "review/audit/sequence_parameter_trajectories.csv"]],
  ["missing_frames", ["summary/missing_frames.csv", "missing_frames.csv", "review/missing_frames.csv"]],
  ["rt_reference", ["summary/room_temperature_reference.csv", "room_temperature_reference.csv", "review/room_temperature_reference.csv"]],
  ["dual_track_differences", ["summary/dual_track_differences.csv", "dual_track_differences.csv", "audit/dual_track_differences.csv"]],
  ["robustness", ["summary/robustness.csv", "robustness.csv", "audit/robustness.csv"]],
  ["warnings", ["warnings.csv", "audit/warnings.csv", "review/audit/warnings.csv"]],
];

async function firstExisting(candidates) {
  for (const candidate of candidates) {
    const fullPath = path.join(outputDir, candidate);
    try {
      await fs.access(fullPath);
      return fullPath;
    } catch {
      // Try the next supported result-package location.
    }
  }
  return null;
}

async function exists(candidate) {
  try {
    await fs.access(candidate);
    return true;
  } catch {
    return false;
  }
}

async function moveIntoReview(name, reviewDir) {
  const source = path.join(outputDir, name);
  if (!(await exists(source))) return;
  const destination = path.join(reviewDir, name);
  if (await exists(destination)) {
    throw new Error(`Refusing to overwrite existing review item: ${destination}`);
  }
  await fs.rename(source, destination);
}

async function compactResultPackage() {
  const finalResults = path.join(outputDir, "final_results.csv");
  const reliable = path.join(outputDir, "reliable_parameters.csv");
  if (!(await exists(finalResults)) && (await exists(reliable))) {
    await fs.rename(reliable, finalResults);
  }

  const reviewDir = path.join(outputDir, "review");
  await fs.mkdir(reviewDir, { recursive: true });
  for (const name of [
    "audit",
    "details",
    "figures",
    "summary",
    "accepted_parameters.csv",
    "all_parameters_audit.csv",
    "data_quality.csv",
    "input_manifest_original.csv",
    "reliable_parameters.csv",
    "run_config.json",
    "source_integrity_after_analysis.csv",
  ]) {
    await moveIntoReview(name, reviewDir);
  }

  const readme = `# Ti15 SAXS 结果包

## 首次查看

1. \`final_report_zh.md\`：中文运行报告、最终结论边界和方法状态。
2. \`final_results.csv\`：通过可靠性筛选、用于结果总结的最终参数表。
3. \`summary_tables.xlsx\`：最终汇总工作簿。

其中，\`accepted_parameters\` 和 \`reliable_parameters\` 按每条曲线一行横向展示，参数列名采用
\`analysis_type__parameter [unit]\`；\`all_parameters_audit\` 保留逐参数竖向审计格式。

## 需要复查时再打开

- \`audit_full.zip\`：独立完整审计包；不包含 \`details_full.zip\`。
- \`details_full.zip\`：独立完整逐帧明细包。
- \`review/\`：未放在主目录的质量、审计、序列、图件和运行配置文件。

本结果包只分析指定的前 10 帧，所有纳入计算的数据均限制在有效 q 范围
\`0.01–0.5 Å⁻¹\` 内。原始 CSV 未修改、未复制进压缩包，也未进行平滑、平移、强度截断或背景扣除。
`;
  await fs.writeFile(path.join(outputDir, "README.md"), readme, "utf8");
}

function styleImportedSheet(sheet) {
  sheet.showGridLines = false;
  const used = sheet.getUsedRange();
  if (!used) return;
  const header = used.getRow(0);
  header.format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    borders: { bottom: { style: "medium", color: "#1F4E78" } },
  };
  used.format.autofitColumns();
  sheet.freezePanes.freezeRows(1);
}

function coerceNumericColumns(sheet, columns, firstDataRow, lastDataRow) {
  for (const column of columns) {
    const range = sheet.getRange(`${column}${firstDataRow}:${column}${lastDataRow}`);
    range.values = range.values.map(([value]) => {
      if (value === null || value === "") return [null];
      const numeric = Number(value);
      return [Number.isFinite(numeric) ? numeric : value];
    });
  }
}

function asText(value) {
  return value === null || value === undefined ? "" : String(value).trim();
}

function asNumberOrText(value) {
  const text = asText(value);
  if (!text) return null;
  const numeric = Number(text);
  return Number.isFinite(numeric) ? numeric : value;
}

function shortNumber(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toPrecision(6) : asText(value);
}

function asBoolean(value) {
  return [true, "true", "True", 1, "1"].includes(value);
}

function buildWideParameterMatrix(sheet) {
  const used = sheet.getUsedRange();
  const rows = used?.values || [];
  if (rows.length < 2) return null;
  const headers = rows[0].map(asText);
  const column = Object.fromEntries(headers.map((header, index) => [header, index]));
  const required = ["frame", "curve_name", "analysis_type", "parameter", "value"];
  if (required.some((name) => column[name] === undefined)) return null;

  const groups = new Map();
  const parameters = new Map();
  for (const row of rows.slice(1)) {
    const frame = asText(row[column.frame]);
    const curveName = asText(row[column.curve_name]);
    if (!frame && !curveName) continue;
    const analysisType = asText(row[column.analysis_type]) || "unknown";
    const parameter = asText(row[column.parameter]) || "unnamed";
    const unitRole = column.unit_role === undefined ? "" : asText(row[column.unit_role]);
    const parameterKey = `${analysisType}__${parameter}`;
    const existingParameter = parameters.get(parameterKey);
    if (!existingParameter) {
      parameters.set(parameterKey, {
        key: parameterKey,
        analysisType,
        parameter,
        display: unitRole ? `${parameterKey} [${unitRole}]` : parameterKey,
      });
    } else if (!existingParameter.display.includes("[") && unitRole) {
      existingParameter.display = `${parameterKey} [${unitRole}]`;
    }

    const groupKey = `${frame}\u0000${curveName}`;
    if (!groups.has(groupKey)) {
      groups.set(groupKey, {
        frame,
        curveName,
        values: new Map(),
        statuses: new Set(),
        reliabilityLabels: new Set(),
        qRanges: new Set(),
        acceptedCount: 0,
        reliableCount: 0,
        warningCount: 0,
      });
    }
    const group = groups.get(groupKey);

    const value = asText(row[column.value])
      ? row[column.value]
      : column.numeric_value === undefined
        ? null
        : row[column.numeric_value];
    if (value !== null && value !== undefined && asText(value)) {
      if (!group.values.has(parameterKey)) {
        group.values.set(parameterKey, asNumberOrText(value));
      } else {
        const previous = group.values.get(parameterKey);
        group.values.set(parameterKey, `${asText(previous)} | ${asText(value)}`);
      }
    }

    const status = asText(row[column.analysis_status]);
    if (status) group.statuses.add(status);
    const reliabilityLabel = asText(row[column.reliability_label]);
    if (reliabilityLabel) group.reliabilityLabels.add(reliabilityLabel);
    const qStart = column["q_start_A^-1"] === undefined ? "" : asText(row[column["q_start_A^-1"]]);
    const qEnd = column["q_end_A^-1"] === undefined ? "" : asText(row[column["q_end_A^-1"]]);
    if (qStart && qEnd) {
      group.qRanges.add(`${shortNumber(qStart)}–${shortNumber(qEnd)} Å⁻¹`);
    }
    if (asText(row[column.warnings])) group.warningCount += 1;
    if (column.accepted !== undefined && asBoolean(row[column.accepted])) group.acceptedCount += 1;
    if (column.reliable_for_reporting !== undefined && asBoolean(row[column.reliable_for_reporting])) {
      group.reliableCount += 1;
    }
  }

  const parameterList = [...parameters.values()].sort(
    (left, right) => left.analysisType.localeCompare(right.analysisType) || left.parameter.localeCompare(right.parameter),
  );
  const outputHeaders = [
    "frame",
    "curve_name",
    "status_summary",
    "reliability_summary",
    "q_ranges",
    "accepted_parameter_count",
    "reliable_parameter_count",
    "warning_count",
    "parameter_count",
    ...parameterList.map((item) => item.display),
  ];
  const output = [outputHeaders];
  const sortedGroups = [...groups.values()].sort((left, right) => {
    const frameDifference = Number(left.frame) - Number(right.frame);
    return Number.isFinite(frameDifference) && frameDifference !== 0
      ? frameDifference
      : left.frame.localeCompare(right.frame);
  });
  for (const group of sortedGroups) {
    output.push([
      asNumberOrText(group.frame),
      group.curveName,
      [...group.statuses].join(" | "),
      [...group.reliabilityLabels].join(" | "),
      [...group.qRanges].join("; "),
      group.acceptedCount,
      group.reliableCount,
      group.warningCount,
      group.values.size,
      ...parameterList.map((item) => group.values.get(item.key) ?? null),
    ]);
  }
  return output;
}

function styleWideParameterSheet(sheet, matrix) {
  sheet.showGridLines = false;
  const used = sheet.getUsedRange();
  if (!used) return;
  used.getRow(0).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    borders: { bottom: { style: "medium", color: "#1F4E78" } },
  };
  const headers = matrix[0].map(asText);
  for (let index = 0; index < headers.length; index += 1) {
    let width = Math.min(Math.max(headers[index].length * 1.05, 14), 24);
    if (headers[index] === "curve_name") width = 30;
    if (headers[index] === "q_ranges") width = 42;
    if (headers[index].includes("summary")) width = 22;
    sheet.getRangeByIndexes(0, index, matrix.length, 1).format.columnWidth = width;
  }
  sheet.getRangeByIndexes(0, 0, 1, matrix[0].length).format.rowHeight = 36;
  sheet.freezePanes.freezeRows(1);
}

function pivotParameterSheet(sheet) {
  const matrix = buildWideParameterMatrix(sheet);
  if (!matrix) return;
  sheet.getUsedRange().clear({ applyTo: "all" });
  sheet.getRangeByIndexes(0, 0, matrix.length, matrix[0].length).values = matrix;
  styleWideParameterSheet(sheet, matrix);
}

const workbook = await Workbook.fromCSV("placeholder\n", { sheetName: "Overview" });
const overview = workbook.worksheets.getItem("Overview");
const imported = [];

for (const [sheetName, candidates] of csvSources) {
  const sourcePath = await firstExisting(candidates);
  if (!sourcePath) continue;
  const csvText = (await fs.readFile(sourcePath, "utf8")).replace(/^\uFEFF/, "");
  if (!csvText.trim()) continue;
  await workbook.fromCSV(csvText, { sheetName });
  const sheet = workbook.worksheets.getItem(sheetName);
  const rowCount = csvText.trim().split(/\r?\n/).length;
  if (sheetName === "data_quality" && rowCount > 1) {
    coerceNumericColumns(sheet, ["F", "G", "H", "I", "J", "K", "M", "N", "O", "P", "Q", "R", "S", "U", "V"], 2, rowCount);
  }
  styleImportedSheet(sheet);
  imported.push({ sheetName, sourcePath, rowCount });
}

for (const sheetName of ["accepted_parameters", "reliable_parameters"]) {
  if (imported.some((item) => item.sheetName === sheetName)) {
    pivotParameterSheet(workbook.worksheets.getItem(sheetName));
  }
}

overview.showGridLines = false;
overview.getRange("A1:H1").merge();
overview.getRange("A1").values = [["17_Ti15_300_2_iso SAXS 模型免费双轨分析汇总"]];
overview.getRange("A1:H1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF" },
};

overview.getRange("A3:B3").values = [["分析信息", "内容"]];
overview.getRange("A3:B3").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
let effectiveQText = "0.01–0.5 Å⁻¹";
let analysisObjectText = "Ti15 原位序列（真实帧号）";
let referenceText = "室温曲线独立对比，不参与公共区间共识";
try {
  const configPath = await firstExisting(["run_config.json", "review/run_config.json"]);
  if (!configPath) throw new Error("run_config.json not found");
  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  const range = config.effective_q_range;
  if (Array.isArray(range) && range.length === 2) {
    effectiveQText = `${Number(range[0]).toPrecision(6)}–${Number(range[1]).toPrecision(6)} Å⁻¹`;
  }
  const selection = config.input_selection || {};
  const selectedCount = Number(selection.selected_series_count);
  const limit = Number(selection.limit);
  if (Number.isFinite(selectedCount)) {
    analysisObjectText = limit === 0
      ? `完整原位序列（${selectedCount} 帧，保留真实帧号缺口）`
      : `试运行：前 ${selectedCount} 个原位帧（真实帧号）`;
  }
  const referenceCount = Number(selection.reference_count);
  if (Number.isFinite(referenceCount)) {
    referenceText = `${referenceCount} 条室温曲线独立对比，不参与公共区间共识`;
  }
} catch {
  // Keep the documented default when a legacy package has no run_config.json.
}
overview.getRange("A4:A11").values = [
  ["分析对象"],
  ["参考文件"],
  ["模型拟合"],
  ["有效 q 范围"],
  ["q 单位"],
  ["强度单位"],
  ["结果目录"],
  ["原始数据处理"],
];
overview.getRange("B4:B11").values = [
  [analysisObjectText],
  [referenceText],
  ["已关闭，仅无模型分析"],
  [effectiveQText],
  ["Å⁻¹"],
  ["cm⁻¹"],
  [outputDir],
  ["只读；不平滑、不平移、不截断、不扣背景"],
];

overview.getRange("A13:B13").values = [["有效 q 范围质量指标", "值"]];
overview.getRange("A13:B13").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
overview.getRange("A14:A20").values = [
  ["导入曲线数"],
  ["有效 q 点数最小值"],
  ["有效 q 点数最大值"],
  ["实际 q 最小值 (Å⁻¹)"],
  ["实际 q 最大值 (Å⁻¹)"],
  ["负强度点总数"],
  ["零强度点总数"],
];
const dataQualityImport = imported.find((item) => item.sheetName === "data_quality");
if (dataQualityImport && dataQualityImport.rowCount > 1) {
  const lastDataQualityRow = dataQualityImport.rowCount;
  overview.getRange("B14:B20").formulas = [
    [`=COUNTA('data_quality'!A2:A${lastDataQualityRow})`],
    [`=MIN('data_quality'!F2:F${lastDataQualityRow})`],
    [`=MAX('data_quality'!F2:F${lastDataQualityRow})`],
    [`=MIN('data_quality'!N2:N${lastDataQualityRow})`],
    [`=MAX('data_quality'!O2:O${lastDataQualityRow})`],
    [`=SUM('data_quality'!I2:I${lastDataQualityRow})`],
    [`=SUM('data_quality'!J2:J${lastDataQualityRow})`],
  ];
} else {
  overview.getRange("B14:B20").values = Array.from(
    { length: 7 },
    () => ["未提供 data_quality.csv"],
  );
}

overview.getRange("A22:H22").merge();
overview.getRange("A22").values = [[
  "注意：accepted_parameters/reliable_parameters 已按曲线横向展开；all_parameters_audit 保留逐参数竖向审计格式。所有分析表按用户有效 q 范围导出，参数仍需结合状态、warning 和样品背景复核。",
]];
overview.getRange("A22:H22").format = {
  fill: "#FFF2CC",
  font: { color: "#7F6000" },
  wrapText: true,
};
overview.getRange("A3:B20").format.borders = {
  insideHorizontal: { style: "thin", color: "#D9E2F3" },
  outside: { style: "thin", color: "#9FBAD0" },
};
overview.getRange("A1:H22").format.autofitColumns();
overview.getRange("A1:H22").format.autofitRows();
overview.getRange("A1:H22").format.columnWidth = 18;
overview.getRange("A1:A22").format.columnWidth = 24;
overview.getRange("B4:B11").format.columnWidth = 42;
overview.getRange("B13:B20").format.columnWidth = 20;
overview.freezePanes.freezeRows(3);

await fs.mkdir(previewDir, { recursive: true });
const sheetNames = ["Overview", ...imported.map((item) => item.sheetName)];
for (const sheetName of sheetNames) {
  const preview = await workbook.render({
    sheetName,
    range: sheetName === "Overview" ? "A1:H22" : "A1:H20",
    scale: 1,
    format: "png",
  });
  const previewPath = path.join(previewDir, `${sheetName}.png`);
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
}

const inspection = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 3000,
});
console.log(`WORKBOOK_SHEETS=${inspection.ndjson.replace(/\s+/g, " ").slice(0, 2800)}`);

const overviewCheck = await workbook.inspect({
  kind: "table",
  sheetId: "Overview",
  range: "A13:B20",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 3,
  maxChars: 3000,
});
console.log(`OVERVIEW_CHECK=${overviewCheck.ndjson.replace(/\s+/g, " ").slice(0, 2800)}`);

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(`FORMULA_ERRORS=${formulaErrors.ndjson.replace(/\s+/g, " ").slice(0, 1000)}`);

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "summary_tables.xlsx");
await xlsx.save(outputPath);
await fs.mkdir(path.join(outputDir, "audit"), { recursive: true });
await fs.writeFile(
  path.join(outputDir, "audit", "workbook_validation.json"),
  JSON.stringify(
    {
      workbook: outputPath,
      rendered_sheet_count: sheetNames.length,
      rendered_sheets: sheetNames,
      preview_directory: previewDir,
      overview_inspection: overviewCheck.ndjson,
      formula_error_scan: formulaErrors.ndjson,
    },
    null,
    2,
  ),
  "utf8",
);
if (compactAfterExport) {
  await compactResultPackage();
}
await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
console.log(`XLSX=${outputPath}`);
console.log(`PREVIEWS=${previewDir}`);
console.log(`COMPACT_PACKAGE=${compactAfterExport ? outputDir : "disabled"}`);
