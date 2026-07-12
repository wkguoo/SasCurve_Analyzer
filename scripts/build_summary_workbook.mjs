import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = path.resolve(process.argv[2] || "");
if (!outputDir) {
  throw new Error("Usage: node build_summary_workbook.mjs <result-directory>");
}

const previewDir = path.join(
  path.dirname(outputDir),
  ".sax_summary_previews",
  path.basename(outputDir),
);

const csvSources = [
  ["input_manifest", ["input_manifest_original.csv", "summary/input_manifest.csv"]],
  ["source_integrity", ["source_integrity_after_analysis.csv"]],
  ["data_quality", ["data_quality.csv"]],
  ["accepted_parameters", ["accepted_parameters.csv"]],
  ["reliable_parameters", ["reliable_parameters.csv"]],
  ["all_parameters_audit", ["all_parameters_audit.csv", "audit/parameters.csv"]],
  ["fit_quality", ["fit_quality.csv", "audit/fit_quality.csv"]],
  ["sequence_frames", ["sequence_frame_table.csv", "summary/sequence_frame_table.csv", "audit/sequence_frame_table.csv"]],
  ["sequence_parameters", ["sequence_parameter_trajectories.csv", "audit/sequence_parameter_trajectories.csv"]],
  ["warnings", ["warnings.csv", "audit/warnings.csv"]],
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

const workbook = await Workbook.fromCSV("placeholder\n", { sheetName: "Overview" });
const overview = workbook.worksheets.getItem("Overview");
const imported = [];

for (const [sheetName, candidates] of csvSources) {
  const sourcePath = await firstExisting(candidates);
  if (!sourcePath) continue;
  const csvText = (await fs.readFile(sourcePath, "utf8")).replace(/^\uFEFF/, "");
  await workbook.fromCSV(csvText, { sheetName });
  const sheet = workbook.worksheets.getItem(sheetName);
  const rowCount = csvText.trim().split(/\r?\n/).length;
  if (sheetName === "data_quality" && rowCount > 1) {
    coerceNumericColumns(sheet, ["F", "G", "H", "I", "J", "K", "M", "N", "O", "P", "Q"], 2, rowCount);
  }
  styleImportedSheet(sheet);
  imported.push({ sheetName, sourcePath });
}

overview.showGridLines = false;
overview.getRange("A1:H1").merge();
overview.getRange("A1").values = [["17_Ti15_300_2_iso SAXS 前十帧无模型分析汇总"]];
overview.getRange("A1:H1").format = {
  fill: "#17365D",
  font: { bold: true, color: "#FFFFFF" },
};

overview.getRange("A3:B3").values = [["分析信息", "内容"]];
overview.getRange("A3:B3").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
overview.getRange("A4:A10").values = [
  ["分析对象"],
  ["参考文件"],
  ["模型拟合"],
  ["q 单位"],
  ["强度单位"],
  ["结果目录"],
  ["原始数据处理"],
];
overview.getRange("B4:B10").values = [
  ["ti15_00001–ti15_00010"],
  ["TI15-rt_00001 已排除"],
  ["已关闭，仅无模型分析"],
  ["Å⁻¹"],
  ["cm⁻¹"],
  [outputDir],
  ["只读；不平滑、不平移、不截断、不扣背景"],
];

overview.getRange("A12:B12").values = [["质量与范围指标", "值"]];
overview.getRange("A12:B12").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
overview.getRange("A13:A19").values = [
  ["导入曲线数"],
  ["每帧点数最小值"],
  ["每帧点数最大值"],
  ["q 最小值 (Å⁻¹)"],
  ["q 最大值 (Å⁻¹)"],
  ["负强度点总数"],
  ["零强度点总数"],
];
overview.getRange("B13:B19").formulas = [
  ["=COUNTA('data_quality'!A2:A11)"],
  ["=MIN('data_quality'!F2:F11)"],
  ["=MAX('data_quality'!F2:F11)"],
  ["=MIN('data_quality'!N2:N11)"],
  ["=MAX('data_quality'!O2:O11)"],
  ["=SUM('data_quality'!I2:I11)"],
  ["=SUM('data_quality'!J2:J11)"],
];

overview.getRange("A21:H21").merge();
overview.getRange("A21").values = [[
  "注意：accepted/reliable 参数仍需结合 q 区间、状态、warning 和样品背景复核；拟合结果不等于形貌或机理证明。",
]];
overview.getRange("A21:H21").format = {
  fill: "#FFF2CC",
  font: { color: "#7F6000" },
  wrapText: true,
};
overview.getRange("A3:B19").format.borders = {
  insideHorizontal: { style: "thin", color: "#D9E2F3" },
  outside: { style: "thin", color: "#9FBAD0" },
};
overview.getRange("A1:H21").format.autofitColumns();
overview.getRange("A1:H21").format.autofitRows();
overview.getRange("A1:H21").format.columnWidth = 18;
overview.getRange("A1:A21").format.columnWidth = 24;
overview.getRange("B4:B10").format.columnWidth = 42;
overview.getRange("B12:B19").format.columnWidth = 20;
overview.freezePanes.freezeRows(3);

await fs.mkdir(previewDir, { recursive: true });
const sheetNames = ["Overview", ...imported.map((item) => item.sheetName)];
for (const sheetName of sheetNames) {
  const preview = await workbook.render({
    sheetName,
    range: sheetName === "Overview" ? "A1:H21" : "A1:H20",
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
  range: "A12:B19",
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
console.log(`XLSX=${outputPath}`);
console.log(`PREVIEWS=${previewDir}`);
