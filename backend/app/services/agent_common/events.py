from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class AgentEvent:
    """Agent SSE event payload shared by harness runtime and API streaming."""

    type: str
    data: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "data": self.data}, ensure_ascii=False)
