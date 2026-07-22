# Financial Model Subtype Reference

Use these conventions only when the spreadsheet deliverable is clearly a financial model, valuation model, operating model, budget model, or similar finance workbook.

## Formatting

- Blue text: hardcoded inputs and scenario assumptions.
- Black text: formulas and calculations.
- Green text: links pulling from other worksheets in the same workbook.
- Red text: external links to other files.
- Yellow fill: key assumptions or cells that need user attention.

## Number Formats

- Years should be text labels, not comma-formatted numbers.
- Currency should state units in the header, for example `Revenue ($mm)`.
- Zeros should display as `-` where that matches the model style.
- Percentages usually use one decimal place.
- Valuation multiples usually use `0.0x`.
- Negative numbers usually use parentheses.

## Formula Construction

- Put assumptions in dedicated cells and reference them from formulas.
- Keep formulas consistent across projection periods.
- Check references, ranges, and circular references.
- Test zero, negative, and missing-value edge cases.

## Source Notes

Document material hardcodes near the relevant inputs. Include source name, date or period, and enough detail for a reviewer to trace the assumption. Use URLs only when the source is public and relevant.
