from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from app.services.agent_harness.catalog import list_design_system_summaries_sync

_CATEGORY_TAGS: dict[str, list[str]] = {
    "themed & unique": ["expressive", "brand-led", "stylized"],
    "product & saas": ["product", "enterprise", "structured"],
    "editorial & content": ["editorial", "content", "storytelling"],
    "creative & portfolio": ["creative", "portfolio", "showcase"],
    "dashboard & data": ["dashboard", "data-dense", "technical"],
    "commerce & marketing": ["marketing", "conversion", "campaign"],
}

_OVERRIDES: dict[str, dict[str, object]] = {
    "default": {
        "resolver_summary": "Balanced default design system for general-purpose product, content, and company tasks.",
        "resolver_tags": ["balanced", "neutral", "product", "general-purpose"],
        "preferred_for": ["landing-page", "company-site", "product-page", "docs", "dashboard"],
        "avoid_for": [],
        "tone": "professional",
        "density": "balanced",
        "category": "Product & SaaS",
        "featured_priority": 1,
    },
    "application": {
        "resolver_summary": "Professional application-style system for company pages, product surfaces, and high-trust web work.",
        "resolver_tags": ["enterprise", "product", "professional", "structured"],
        "preferred_for": ["landing-page", "company-site", "product-page", "dashboard", "docs"],
        "avoid_for": ["art-portfolio", "playful-campaign"],
        "tone": "professional",
        "density": "balanced",
        "category": "Product & SaaS",
        "featured_priority": 2,
    },
    "agentic": {
        "resolver_summary": "AI-first system for agent workflows, delegated task views, and modern conversational product interfaces.",
        "resolver_tags": ["ai", "agentic", "modern", "product"],
        "preferred_for": ["dashboard", "product-page", "company-site", "landing-page"],
        "avoid_for": ["formal-finance", "luxury-editorial"],
        "tone": "technical",
        "density": "balanced",
        "category": "Themed & Unique",
        "featured_priority": 6,
    },
    "ant": {
        "resolver_summary": "Structured enterprise application system suitable for dense product pages, dashboards, and documentation-heavy tasks.",
        "resolver_tags": ["enterprise", "structured", "technical", "data-dense"],
        "preferred_for": ["dashboard", "docs", "product-page", "company-site"],
        "avoid_for": ["art-portfolio", "playful-campaign"],
        "tone": "technical",
        "density": "dense",
        "category": "Dashboard & Data",
        "featured_priority": 8,
    },
}


@dataclass(slots=True)
class DesignSystemResolverMetadata:
    id: str
    resolver_summary: str
    resolver_tags: list[str]
    preferred_for: list[str]
    avoid_for: list[str]
    tone: str
    density: str
    category: str
    featured_priority: int | None = None


def _slug_to_title(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").strip().title()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _infer_tags(slug: str, title: str, summary: str, category: str) -> list[str]:
    haystack = f"{slug} {title} {summary} {category}".lower()
    tags = list(_CATEGORY_TAGS.get(category.strip().lower(), ["product", "balanced"]))

    keyword_map = {
        "enterprise": ["enterprise", "b2b", "workspace", "business"],
        "editorial": ["editorial", "magazine", "publish", "content"],
        "playful": ["playful", "friendly", "fun", "youthful"],
        "luxury": ["luxury", "premium", "elegant", "sophisticated"],
        "minimal": ["minimal", "clean", "neutral", "restrained"],
        "dashboard": ["dashboard", "analytics", "admin", "data"],
        "docs": ["docs", "documentation", "developer", "technical"],
        "creative": ["creative", "portfolio", "studio", "showcase"],
        "marketing": ["marketing", "campaign", "conversion", "landing"],
        "ai": ["ai", "agent", "assistant", "automation"],
        "product": ["product", "saas", "app", "application"],
    }
    for tag, needles in keyword_map.items():
        if any(needle in haystack for needle in needles):
            tags.append(tag)
    return _unique(tags)


def _infer_tone(tags: list[str]) -> str:
    if "luxury" in tags:
        return "premium"
    if "playful" in tags:
        return "friendly"
    if "editorial" in tags:
        return "editorial"
    if "docs" in tags or "dashboard" in tags:
        return "technical"
    return "professional"


def _infer_density(tags: list[str]) -> str:
    if "dashboard" in tags or "docs" in tags:
        return "dense"
    if "luxury" in tags or "minimal" in tags or "creative" in tags:
        return "airy"
    return "balanced"


def _infer_preferred_for(tags: list[str]) -> list[str]:
    preferred = ["company-site", "product-page"]
    if "marketing" in tags or "luxury" in tags or "creative" in tags:
        preferred.append("landing-page")
    if "dashboard" in tags:
        preferred.append("dashboard")
    if "docs" in tags or "editorial" in tags:
        preferred.append("docs")
    if "creative" in tags:
        preferred.append("portfolio")
    return _unique(preferred)


def _infer_avoid_for(tags: list[str]) -> list[str]:
    avoid: list[str] = []
    if "dashboard" in tags or "docs" in tags:
        avoid.append("playful-campaign")
    if "creative" in tags or "luxury" in tags:
        avoid.append("dense-data")
    if "playful" in tags:
        avoid.append("formal-finance")
    return _unique(avoid)


def _build_generated_metadata(system_id: str, title: str, summary: str, category: str) -> DesignSystemResolverMetadata:
    tags = _infer_tags(system_id, title, summary, category)
    tone = _infer_tone(tags)
    density = _infer_density(tags)
    preferred_for = _infer_preferred_for(tags)
    avoid_for = _infer_avoid_for(tags)
    resolver_summary = f"{title} style for {', '.join(preferred_for[:3])} tasks with a {tone} tone and {density} information density."
    return DesignSystemResolverMetadata(
        id=system_id,
        resolver_summary=resolver_summary,
        resolver_tags=tags,
        preferred_for=preferred_for,
        avoid_for=avoid_for,
        tone=tone,
        density=density,
        category=category,
        featured_priority=50,
    )


def _apply_override(base: DesignSystemResolverMetadata, override: dict[str, object]) -> DesignSystemResolverMetadata:
    merged = {
        "id": base.id,
        "resolver_summary": base.resolver_summary,
        "resolver_tags": list(base.resolver_tags),
        "preferred_for": list(base.preferred_for),
        "avoid_for": list(base.avoid_for),
        "tone": base.tone,
        "density": base.density,
        "category": base.category,
        "featured_priority": base.featured_priority,
    }
    merged.update(override)
    return DesignSystemResolverMetadata(**merged)


@lru_cache(maxsize=1)
def get_design_system_resolver_registry() -> dict[str, DesignSystemResolverMetadata]:
    registry: dict[str, DesignSystemResolverMetadata] = {}
    for system in list_design_system_summaries_sync():
        category = str(system.category or "").strip() or "Product & SaaS"
        metadata = DesignSystemResolverMetadata(
            id=system.id,
            resolver_summary=system.resolver_summary,
            resolver_tags=list(system.resolver_tags),
            preferred_for=list(system.preferred_for),
            avoid_for=list(system.avoid_for),
            tone=system.tone,
            density=system.density,
            category=category,
            featured_priority=system.featured,
        )
        override = _OVERRIDES.get(system.id)
        if override:
            metadata = _apply_override(metadata, override)
        registry[system.id] = metadata
    return registry


def clear_design_system_resolver_registry_cache() -> None:
    get_design_system_resolver_registry.cache_clear()


def list_design_system_resolver_metadata() -> list[DesignSystemResolverMetadata]:
    return list(get_design_system_resolver_registry().values())


def get_design_system_resolver_metadata(design_system_id: str | None) -> DesignSystemResolverMetadata | None:
    normalized = str(design_system_id or "").strip()
    if not normalized:
        return None
    return get_design_system_resolver_registry().get(normalized)
