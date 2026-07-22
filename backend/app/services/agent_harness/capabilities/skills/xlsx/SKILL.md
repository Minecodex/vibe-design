---
name: xlsx
display_name_zh: 表格工作簿
description: "Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file; add columns, formulas, formatting, charts, or cleaned data; create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger especially when the user references a spreadsheet file by name or path and wants something done to it or produced from it. Do NOT trigger when the primary deliverable is a Word document, HTML report, standalone Python script, database pipeline, or Google Sheets API integration, even if tabular data is involved."
description_zh: "当表格文件是主要输入或输出时使用此技能。适用于读取、编辑、修复 .xlsx/.xlsm/.csv/.tsv 文件，新增列、公式、格式、图表或清洗数据，也适用于从零创建工作簿或不同表格格式之间的转换。"
license: Proprietary. LICENSE.txt has complete terms
tools:
  - exec_command
  - list_files
  - read_file
  - edit_file
  - write_file
  - workspace_map
  - register_artifact
  - publish_output
  - analyze_image
  - web_search
  - Agent
name_zh: 电子表格
---

# XLSX Creation, Editing, And Analysis

Follow the harness workspace contract.

Use this skill for spreadsheet knowledge and output quality; artifact publishing is handled by the runtime tools.

## What This Skill Covers

Use this skill for spreadsheet deliverables: Excel workbooks, macro-enabled workbooks when only non-macro content is touched, CSV/TSV cleanup, tabular transformations, formulas, charts, formatting, and workbook repair.

## General Requirements

- Preserve existing templates, formatting, formulas, sheet order, named ranges, and user-facing conventions unless the user asks for redesign.
- Deliver workbooks with no formula errors such as `#REF!`, `#DIV/0!`, `#VALUE!`, `#N/A`, or `#NAME?`.
- Keep raw data, assumptions, calculations, and presentation sheets clearly separated when building new analytical workbooks.
- Use formulas with cell references instead of unexplained hardcoded values.
- Validate generated data files and final workbook artifacts.

## Reading And Cleaning Data

Inspect workbook sheets, dimensions, headers, merged cells, formulas, and data types before modifying. For CSV/TSV cleanup, detect delimiters, malformed rows, encoding issues, repeated headers, and junk preamble/footer rows before writing the cleaned workbook.

## Workbook Generation

Prefer a structured generation flow:

1. Normalize source data.
2. Write intermediate data in a machine-checkable format.
3. Generate sheets, formulas, tables, charts, and formatting.
4. Recalculate formulas when needed.
5. Validate workbook structure and computed values.

## Financial Model Subtype

Only apply investment-banking or financial-model formatting conventions when the user's task is clearly a financial model, valuation model, operating model, budget model, or similar finance deliverable. For that subtype, read `references/financial-model.md`.

For ordinary spreadsheets, do not impose finance-specific color coding, source-note wording, valuation multiples, or projection conventions.

## Common Pitfalls

- formulas shifted by one row or column
- accidental string numbers
- charts pointing at stale ranges
- hidden sheets or filters dropping rows
- date serials formatted as plain numbers
- destructive overwrites of user templates
- formulas that work before export but are not recalculated in the final workbook
