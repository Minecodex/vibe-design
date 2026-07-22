from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


def build_turn_idempotency_key(*parts: Any) -> str:
    prefix = str(parts[0] if parts else "turn").replace("\n", " ").strip() or "turn"
    normalized_prefix = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in prefix)[:40] or "turn"
    canonical = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return f"{normalized_prefix}:{digest}"
