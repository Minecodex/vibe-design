"""Open-Design token schema helpers for Home Harness design systems."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TokenSpec:
    name: str
    layer: str
    fallback: str | None = None
    alias_to: str | None = None


TOKEN_SCHEMA: tuple[TokenSpec, ...] = (
    TokenSpec("--bg", "A1-identity"),
    TokenSpec("--surface", "A1-identity"),
    TokenSpec("--surface-warm", "B-slot", alias_to="var(--surface)"),
    TokenSpec("--fg", "A1-identity"),
    TokenSpec("--fg-2", "B-slot", alias_to="var(--fg)"),
    TokenSpec("--muted", "A1-identity"),
    TokenSpec("--meta", "B-slot", alias_to="var(--muted)"),
    TokenSpec("--border", "A1-identity"),
    TokenSpec("--border-soft", "B-slot", alias_to="var(--border)"),
    TokenSpec("--accent", "A1-identity"),
    TokenSpec("--accent-on", "A2", fallback="#ffffff"),
    TokenSpec("--accent-hover", "A2", fallback="color-mix(in oklab, var(--accent), black 8%)"),
    TokenSpec("--accent-active", "A2", fallback="color-mix(in oklab, var(--accent), black 14%)"),
    TokenSpec("--success", "A2", fallback="#16a34a"),
    TokenSpec("--warn", "A2", fallback="#eab308"),
    TokenSpec("--danger", "A2", fallback="#dc2626"),
    TokenSpec("--font-display", "A1-identity"),
    TokenSpec("--font-body", "A1-identity"),
    TokenSpec("--font-mono", "A2", fallback='ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Monaco, Consolas, monospace'),
    TokenSpec("--text-xs", "A1-structure"),
    TokenSpec("--text-sm", "A1-structure"),
    TokenSpec("--text-base", "A1-structure"),
    TokenSpec("--text-lg", "A1-structure"),
    TokenSpec("--text-xl", "A1-structure"),
    TokenSpec("--text-2xl", "A1-structure"),
    TokenSpec("--text-3xl", "A1-structure"),
    TokenSpec("--text-4xl", "A1-structure"),
    TokenSpec("--leading-body", "A1-structure"),
    TokenSpec("--leading-tight", "A1-structure"),
    TokenSpec("--tracking-display", "A1-structure"),
    TokenSpec("--space-1", "A2", fallback="4px"),
    TokenSpec("--space-2", "A2", fallback="8px"),
    TokenSpec("--space-3", "A2", fallback="12px"),
    TokenSpec("--space-4", "A2", fallback="16px"),
    TokenSpec("--space-5", "A2", fallback="20px"),
    TokenSpec("--space-6", "A2", fallback="24px"),
    TokenSpec("--space-8", "A2", fallback="32px"),
    TokenSpec("--space-12", "A2", fallback="48px"),
    TokenSpec("--section-y-desktop", "A1-structure"),
    TokenSpec("--section-y-tablet", "A1-structure"),
    TokenSpec("--section-y-phone", "A1-structure"),
    TokenSpec("--radius-sm", "A2", fallback="8px"),
    TokenSpec("--radius-md", "A2", fallback="12px"),
    TokenSpec("--radius-lg", "A2", fallback="16px"),
    TokenSpec("--radius-pill", "A2", fallback="9999px"),
    TokenSpec("--elev-flat", "A2", fallback="none"),
    TokenSpec("--elev-ring", "A2", fallback="0 0 0 1px var(--border)"),
    TokenSpec("--elev-raised", "A2", fallback="0 2px 8px color-mix(in oklab, var(--fg), transparent 92%)"),
    TokenSpec("--focus-ring", "A2", fallback="0 0 0 3px color-mix(in oklab, var(--accent), transparent 70%)"),
    TokenSpec("--motion-fast", "A2", fallback="150ms"),
    TokenSpec("--motion-base", "A2", fallback="200ms"),
    TokenSpec("--ease-standard", "A2", fallback="cubic-bezier(0.2, 0, 0, 1)"),
    TokenSpec("--container-max", "A1-structure"),
    TokenSpec("--container-gutter-desktop", "A1-structure"),
    TokenSpec("--container-gutter-tablet", "A1-structure"),
    TokenSpec("--container-gutter-phone", "A1-structure"),
)

TOKEN_SCHEMA_NAMES = frozenset(spec.name for spec in TOKEN_SCHEMA)

BRAND_EXTENSIONS: dict[str, frozenset[str]] = {
    "default": frozenset({"--space-20"}),
    "openai": frozenset({"--space-16"}),
    "kami": frozenset(
        {
            "--accent-light",
            "--text-md",
            "--leading-display",
            "--leading-dense",
            "--tracking-eyebrow",
            "--tracking-label",
            "--space-7",
            "--space-18",
            "--space-22",
            "--radius-xs",
            "--radius-xl",
            "--elev-ring-accent",
        }
    ),
}

BRAND_EXTENSION_PREFIXES = ("--tag-bg-",)


def is_allowed_extension(brand: str, token_name: str) -> bool:
    if token_name in BRAND_EXTENSIONS.get(brand, frozenset()):
        return True
    return any(token_name.startswith(prefix) for prefix in BRAND_EXTENSION_PREFIXES)


def unknown_token_names(brand: str, declared_names: set[str]) -> list[str]:
    return sorted(
        name
        for name in declared_names
        if name not in TOKEN_SCHEMA_NAMES and not is_allowed_extension(brand, name)
    )


def fallback_token_value(name: str) -> str | None:
    for spec in TOKEN_SCHEMA:
        if spec.name == name:
            return spec.alias_to or spec.fallback
    return None
