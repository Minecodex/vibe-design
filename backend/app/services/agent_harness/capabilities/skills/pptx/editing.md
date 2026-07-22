# Editing Existing PPTX Files

Use this reference when the user provides an existing presentation or template that must be preserved.

## Inspect First

Before editing, identify:

- slide count and intended order
- theme colors and fonts
- slide masters and layouts
- placeholder text
- speaker notes
- media and chart dependencies
- any repeated design system inside the deck

Prefer text extraction for content review and rendered thumbnails or slide images for layout review.

## Edit Safely

When a high-level library can preserve the file, prefer it. When XML editing is required:

1. Unpack the deck.
2. Edit the smallest relevant XML files.
3. Keep relationship ids, slide ids, layout ids, notes references, and content types consistent.
4. Clean obvious empty placeholder artifacts only when they are not part of the template.
5. Pack and validate the result.

## Slide Operations

When duplicating or inserting slides, update all related presentation metadata:

- presentation slide list
- slide relationship file
- content types
- notes slide relationships when present
- media relationships copied from the source slide

## QA Checklist

- slide order is correct
- no missing media
- no placeholder text remains unless intentionally preserved
- edited slides still use the correct master/layout
- text is not clipped or overlapping
- charts and tables still point to valid data
- speaker notes are preserved when relevant
