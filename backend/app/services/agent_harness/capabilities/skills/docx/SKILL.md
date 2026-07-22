---
name: docx
name_zh: Word 文档
display_name_zh: Word 文档
description: "Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a 'report', 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation."
description_zh: "当用户希望创建、读取、编辑或处理 Word 文档（.docx）时使用此技能。适用于报告、备忘录、信函、模板等正式文档产出，也适用于目录、标题、页码、页眉页脚、批注、修订、图片替换、查找替换和内容重组等 Word 工作流。"
license: Proprietary. LICENSE.txt has complete terms
od:
  category: structured-document
  mode: document
  scenario: narrative
  featured: 3
  design_system:
    requires: true
    sections:
      - Typography
      - Layout
      - Brand application
  craft:
    requires:
      - information-hierarchy
      - typographic-rhythm
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
  - generate_image
  - web_search
  - Agent
---

# DOCX Creation, Editing, And Analysis

Follow the harness workspace contract.

## Overview

A `.docx` file is a ZIP archive containing WordprocessingML XML files. Prefer high-level generation libraries for new documents, and unpack/edit/repack only when preserving an existing file's structure matters.

## Quick Reference

| Task | Approach |
|------|----------|
| Read content | Use text extraction first; unpack XML only when structure or tracked changes matter |
| Create a document | Generate from structured content with a DOCX library |
| Edit an existing document | Unpack, edit the relevant XML, validate, then repack |
| Work with comments or tracked changes | Use the helper scripts and preserve WordprocessingML structure |

Useful helper references include `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/office/validate.py`, `scripts/comment.py`, and `scripts/accept_changes.py`.

## Creating New Documents

Keep substantial source content separate from generator code. Store long outlines, tables, repeated sections, and source text in data files, then keep the generator focused on layout, styles, and assembly.

Use semantic document structure:

- heading levels for headings and table-of-contents entries
- paragraphs for body copy
- tables only for tabular content
- page headers and footers only when they are part of the deliverable

After generation, validate the draft document and inspect extracted text for missing sections, placeholder text, broken order, or obvious formatting loss.

## Editing Existing Documents

When updating an existing `.docx`, preserve the user's template unless they explicitly ask for redesign. Match existing styles, numbering, section breaks, headers, footers, and document conventions.

Recommended workflow:

1. Inspect the document text and structure.
2. Unpack only if a high-level library cannot preserve the required structure.
3. Make focused XML edits.
4. Validate and repack.
5. Re-read or render enough of the result to catch structural regressions.

## Tracked Changes And Comments

Tracked-change XML must wrap whole runs or paragraphs rather than inserting change tags inside an existing run. Preserve the original run properties so formatting remains stable.

Use smart quote XML entities when adding professional prose directly to XML:

| Entity | Character |
|--------|-----------|
| `&#x2018;` | left single quote |
| `&#x2019;` | right single quote / apostrophe |
| `&#x201C;` | left double quote |
| `&#x201D;` | right double quote |

For comments, let the helper script create the supporting comment parts, then add range markers in `document.xml`. Comment range markers are paragraph-level siblings of runs, not children inside a run.

## XML Editing Pitfalls

- Keep required child-element order in paragraph and run properties.
- Add `xml:space="preserve"` when a text node intentionally starts or ends with whitespace.
- Use valid relationship ids and content-type entries for inserted images.
- Never leave malformed XML, duplicate relationship ids, or missing media references.
- If accepting or rejecting changes, verify the resulting clean document still preserves the intended paragraph and list structure.
