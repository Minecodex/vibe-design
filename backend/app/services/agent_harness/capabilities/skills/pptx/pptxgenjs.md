# PptxGenJS Reference

Use this reference when creating a deck from scratch or when a requested edit is easier to regenerate than to patch in XML.

## Basic Structure

```javascript
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = process.env.HARNESS_AUTHOR_NAME || "Harness";
pres.subject = "Generated presentation";
pres.title = "Presentation";

const slide = pres.addSlide();
slide.addText("Title", {
  x: 0.6,
  y: 0.4,
  w: 8.8,
  h: 0.6,
  fontFace: "Aptos Display",
  fontSize: 32,
  bold: true,
  color: "1F2937",
  margin: 0,
});
```

The runtime capability profile explains where scratch data, generated files, and referenced assets belong.

## Data Separation

Keep substantial slide content outside the generator:

- slide outlines
- speaker notes
- image manifests
- chart data
- repeated section metadata
- theme tokens

Read that data from a structured file so layout code stays small and auditable.

## Layout Basics

Coordinates are in inches. Common dimensions:

- `LAYOUT_WIDE`: 13.333 x 7.5
- `LAYOUT_16X9`: 10 x 5.625
- `LAYOUT_4X3`: 10 x 7.5

Use stable positions and dimensions. Avoid letting text boxes, icons, and charts resize the layout unpredictably.

## Text

- Use `margin: 0` when aligning text precisely with shapes.
- Use `breakLine: true` for rich-text arrays with multiple lines.
- Do not prefix manual bullet characters when using PptxGenJS bullet options.
- Keep body text left-aligned unless there is a deliberate visual reason.
- Make title/body size contrast clear.

## Images

Prefer real topic-relevant images or user-provided assets. Preserve aspect ratio unless the design explicitly uses a crop. Add alt text when the library and output path support it.

## Charts And Tables

Keep chart data close to the source data. For tables, use consistent row heights, clear headers, and enough padding to avoid cramped text.

## QA

After rendering:

- extract text and check ordering
- render representative slides
- inspect for clipping, overlaps, low contrast, stale placeholders, and missing media
- re-check affected slides after fixes
