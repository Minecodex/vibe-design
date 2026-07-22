# Usage

- `DESIGN.md` describes visual intent and component language.
- `tokens.css` is the binding runtime contract.
- Paste the unscoped `:root { ... }` block from `tokens.css` verbatim into the first `<style>`.
- Do not invent tokens, redefine token values, or write raw hex outside the root block.
- Match component shapes from `components.manifest.json` and `components.html`.
