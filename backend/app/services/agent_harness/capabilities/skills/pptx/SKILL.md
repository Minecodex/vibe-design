---
name: pptx
display_name_zh: PowerPoint 演示文稿
description: "Use this skill whenever the primary deliverable is a native .pptx file. This includes creating, reading, parsing, editing, repairing, merging, or splitting PowerPoint files; extracting text; and working with templates, layouts, speaker notes, or comments. Trigger whenever the user references a .pptx filename or asks for a PowerPoint file, regardless of whether the content is a presentation, report, or other slide-based deliverable."
description_zh: "只要主要交付物是原生 .pptx 文件，就应使用此技能。适用于创建、读取、解析、编辑、修复、合并或拆分 PowerPoint 文件，也适用于提取文本、处理模板、版式、备注和评论。只要用户提到 .pptx 文件名，或要求输出 PowerPoint 文件，就应触发。"
od:
  category: structured-document
  mode: document
  scenario: presentation
  featured: 4
  design_system:
    requires: true
    sections:
      - Typography
      - Layout
      - Motion posture
  craft:
    requires:
      - narrative-clarity
      - slide-rhythm
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
name_zh: PowerPoint 幻灯片
---

# PPTX Skill

Follow the harness workspace contract.

Use this skill for presentation/domain guidance; artifact publishing is handled by the runtime tools.

## What This Skill Covers

Use this skill to create, inspect, edit, repair, or summarize PowerPoint presentations. Respect existing templates and slide masters when editing an uploaded or previously generated deck.

## Quick Reference

| Task | Guide |
|------|-------|
| Read or summarize a deck | Extract text first; render or thumbnail only when visual layout matters |
| Edit a deck or template | Read `editing.md` |
| Create from scratch | Read `pptxgenjs.md` |
| Inspect Office XML | Use the Office helper scripts by relative path |

Useful helper references include `scripts/thumbnail.py`, `scripts/preview.py`, `scripts/office/unpack.py`, and `scripts/office/pack.py`.

## Editing Existing Decks

Before editing, inspect the deck's slide count, layout conventions, theme colors, fonts, master layouts, speaker notes, and any placeholder text. Prefer focused edits that preserve template behavior.

When manipulating unpacked XML, keep relationships, slide ids, layout references, notes references, and content types consistent. After repacking, validate and inspect enough rendered output to catch broken layouts or missing content.

## Creating Decks From Scratch

Keep slide data separate from generator code. Store substantial copy, image manifests, speaker notes, and repeated layout data in a structured data file, then keep the generator focused on rendering.

Design choices should follow the user's topic, audience, and brand. Avoid generic default styling, but do not override a provided template's established visual language.

## QA Guidance

Check content and visual output before finishing:

- missing or duplicated slides
- leftover placeholder text
- text overflow, clipping, or collisions
- inconsistent alignment, margins, or spacing
- low contrast
- images that are missing, stretched, or cropped badly
- speaker notes or citations in the wrong place

For small edits, verify the affected slides. For newly generated decks, render enough slides to confirm the pattern is sound.
