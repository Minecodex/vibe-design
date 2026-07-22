from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.services.agent_harness.runtime.conversation_events import load_conversation_events
from app.services.agent_harness.workspace.conversation.conversation_service import load_messages

from .store import load_collapse_commits


def search_harness_history(
    user_id: int,
    conversation_id: str,
    *,
    query: str,
    sources: list[str] | None = None,
    limit: int = 8,
    before_seq: int | None = None,
    meta_dir: Path | None = None,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return {"matches": [], "truncated": False}
    selected_sources = set(sources or {"conversation", "tool_results", "compactions", "collapse_commits"})
    matches: list[dict[str, Any]] = []
    exact_reference = _parse_exact_reference(query)
    if exact_reference is not None:
        exact_matches = _recover_exact_reference(
            user_id,
            conversation_id,
            exact_reference=exact_reference,
            selected_sources=selected_sources,
            before_seq=before_seq,
            meta_dir=meta_dir,
        )
        return {"matches": exact_matches[: max(1, limit)], "truncated": len(exact_matches) > max(1, limit)}
    from app.services.agent_harness.runtime.recall_sidecar import search_recall_sidecar

    sidecar_matches = search_recall_sidecar(
        user_id,
        conversation_id,
        query=query,
        limit=limit,
        before_seq=before_seq,
        meta_dir=meta_dir,
        sources=sorted(selected_sources),
    )
    if sidecar_matches:
        matches.extend(sidecar_matches)
    if "conversation" in selected_sources:
        matches.extend(_search_messages(load_messages(user_id, conversation_id), normalized_query, before_seq=before_seq))
    if "compactions" in selected_sources:
        matches.extend(_search_compactions(_load_v2_boundary_events(user_id, conversation_id), normalized_query))
    if "collapse_commits" in selected_sources:
        matches.extend(_search_collapse_commits(load_collapse_commits(user_id, conversation_id, meta_dir=meta_dir), normalized_query))
    if "tool_results" in selected_sources:
        matches.extend(_search_tool_results(user_id, conversation_id, normalized_query, meta_dir=meta_dir))
    matches.sort(key=lambda item: (item.get("score", 0), str(item.get("created_at") or ""), str(item.get("source") or "")), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for match in matches:
        key = (str(match.get("source") or ""), str(match.get("id") or match.get("seq") or match.get("result_ref") or match.get("compaction_id") or ""), str(match.get("snippet") or ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
        if len(deduped) >= max(1, limit):
            break
    return {"matches": deduped, "truncated": len(matches) > len(deduped)}


def _parse_exact_reference(query: str) -> tuple[str, str] | None:
    text = str(query or "").strip()
    match = re.fullmatch(r"(message_id|result_ref|compaction_id|boundary_id|commit_id)\s*:\s*(.+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    key = match.group(1).lower()
    value = match.group(2).strip()
    return (key, value) if value else None


def _recover_exact_reference(
    user_id: int,
    conversation_id: str,
    *,
    exact_reference: tuple[str, str],
    selected_sources: set[str],
    before_seq: int | None,
    meta_dir: Path | None,
) -> list[dict[str, Any]]:
    key, value = exact_reference
    normalized_value = value.lower()
    if key == "message_id" and "conversation" in selected_sources:
        return _recover_message_by_id(user_id, conversation_id, value, before_seq=before_seq)
    if key == "result_ref" and "tool_results" in selected_sources:
        return _recover_tool_result_by_ref(user_id, conversation_id, value)
    if key == "compaction_id" and "compactions" in selected_sources:
        return _recover_compaction_by_id(_load_v2_boundary_events(user_id, conversation_id), normalized_value)
    if key == "boundary_id" and "compactions" in selected_sources:
        return _recover_boundary_by_id(_load_v2_boundary_events(user_id, conversation_id), normalized_value)
    if key == "commit_id" and "collapse_commits" in selected_sources:
        return _recover_collapse_commit_by_id(load_collapse_commits(user_id, conversation_id, meta_dir=meta_dir), normalized_value)
    return []


def _recover_message_by_id(
    user_id: int,
    conversation_id: str,
    message_id: str,
    *,
    before_seq: int | None,
) -> list[dict[str, Any]]:
    for message in load_messages(user_id, conversation_id):
        if str(message.get("id") or "") != str(message_id):
            continue
        seq = int(message.get("_seq") or 0)
        if before_seq is not None and seq >= before_seq:
            return []
        text = _message_text(message)
        return [
            {
                "source": "conversation",
                "id": message.get("id"),
                "seq": seq or None,
                "created_at": message.get("created_at"),
                "role": message.get("role"),
                "snippet": _safe_snippet(text, str(message_id)),
                "score": 10_000,
                "match_type": "exact_reference",
                "reference_type": "message_id",
            }
        ]
    return []


def _recover_tool_result_by_ref(user_id: int, conversation_id: str, result_ref: str) -> list[dict[str, Any]]:
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events

    for event in load_conversation_events(user_id, conversation_id):
        if str(event.get("type") or "") != "tool_result_recorded":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if str(payload.get("result_ref") or "") != str(result_ref):
            continue
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return [
            {
                "source": "tool_results",
                "result_ref": payload.get("result_ref"),
                "created_at": payload.get("created_at") or event.get("created_at"),
                "tool": payload.get("tool"),
                "snippet": _safe_snippet(text, str(result_ref)),
                "score": 10_000,
                "match_type": "exact_reference",
                "reference_type": "result_ref",
            }
        ]
    return []


def _recover_compaction_by_id(events: list[dict[str, Any]], compaction_id: str) -> list[dict[str, Any]]:
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if str(payload.get("boundary_id") or event.get("event_id") or "").lower() != compaction_id:
            continue
        text = json.dumps(event, ensure_ascii=False, sort_keys=True)
        return [
            {
                "source": "compactions",
                "compaction_id": payload.get("boundary_id") or event.get("event_id"),
                "boundary_id": payload.get("boundary_id"),
                "created_at": event.get("created_at"),
                "snippet": _safe_snippet(text, compaction_id),
                "score": 10_000,
                "match_type": "exact_reference",
                "reference_type": "compaction_id",
            }
        ]
    return []


def _recover_boundary_by_id(events: list[dict[str, Any]], boundary_id: str) -> list[dict[str, Any]]:
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if str(payload.get("boundary_id") or "").lower() != boundary_id:
            continue
        text = json.dumps(event, ensure_ascii=False, sort_keys=True)
        return [
            {
                "source": "compactions",
                "boundary_id": payload.get("boundary_id"),
                "created_at": event.get("created_at"),
                "snippet": _safe_snippet(text, boundary_id),
                "score": 10_000,
                "match_type": "exact_reference",
                "reference_type": "boundary_id",
                "covered": payload.get("covered"),
                "compact_type": payload.get("compact_type"),
            }
        ]
    return []


def _recover_collapse_commit_by_id(commits: list[dict[str, Any]], commit_id: str) -> list[dict[str, Any]]:
    for commit in commits:
        if str(commit.get("commit_id") or "").lower() != commit_id:
            continue
        text = json.dumps(commit, ensure_ascii=False, sort_keys=True)
        return [
            {
                "source": "collapse_commits",
                "commit_id": commit.get("commit_id"),
                "created_at": commit.get("created_at"),
                "snippet": _safe_snippet(text, commit_id),
                "score": 10_000,
                "match_type": "exact_reference",
                "reference_type": "commit_id",
            }
        ]
    return []


def _search_messages(messages: Iterable[dict[str, Any]], query: str, *, before_seq: int | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        seq = int(message.get("_seq") or 0)
        if before_seq is not None and seq >= before_seq:
            continue
        text = _message_text(message)
        if query not in text.lower():
            continue
        out.append(
            {
                "source": "conversation",
                "id": message.get("id"),
                "seq": seq or None,
                "created_at": message.get("created_at"),
                "role": message.get("role"),
                "snippet": _safe_snippet(text, query),
                "score": _score(text, query),
            }
        )
    return out


def _search_compactions(events: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        text = json.dumps(event, ensure_ascii=False, sort_keys=True)
        if query not in text.lower():
            continue
        out.append(
            {
                "source": "compactions",
                "compaction_id": payload.get("boundary_id") or event.get("event_id"),
                "boundary_id": payload.get("boundary_id"),
                "created_at": event.get("created_at"),
                "snippet": _safe_snippet(text, query),
                "score": _score(text, query),
            }
        )
    return out


def _load_v2_boundary_events(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for event in load_conversation_events(user_id, conversation_id):
        if str(event.get("type") or event.get("event_type") or "") != "compaction_boundary":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if int(payload.get("schema_version") or 0) != 2:
            continue
        out.append(event)
    return out


def _search_collapse_commits(commits: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for commit in commits:
        text = json.dumps(commit, ensure_ascii=False, sort_keys=True)
        if query not in text.lower():
            continue
        out.append(
            {
                "source": "collapse_commits",
                "commit_id": commit.get("commit_id"),
                "created_at": commit.get("created_at"),
                "snippet": _safe_snippet(text, query),
                "score": _score(text, query),
            }
        )
    return out


def _search_tool_results(user_id: int, conversation_id: str, query: str, *, meta_dir: Path | None = None) -> list[dict[str, Any]]:
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events

    out: list[dict[str, Any]] = []
    for event in load_conversation_events(user_id, conversation_id):
        if str(event.get("type") or "") != "tool_result_recorded":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if query not in text.lower():
            continue
        out.append(
            {
                "source": "tool_results",
                "result_ref": payload.get("result_ref"),
                "created_at": payload.get("created_at"),
                "tool": payload.get("tool"),
                "snippet": _safe_snippet(text, query),
                "score": _score(text, query),
            }
        )
    return out


def _message_text(message: dict[str, Any]) -> str:
    text = str(message.get("content") or "")
    if message.get("tool_name"):
        text += f"\n{message.get('tool_name')}"
    if isinstance(message.get("tool_calls"), list):
        text += "\n" + json.dumps(message["tool_calls"], ensure_ascii=False)
    return text


def _snippet(text: str, query: str, *, width: int = 180) -> str:
    lowered = text.lower()
    index = lowered.find(query)
    if index < 0:
        return text[:width]
    start = max(0, index - width // 3)
    end = min(len(text), index + len(query) + width // 2)
    snippet = text[start:end].replace("\n", " ").strip()
    return snippet if len(snippet) <= width else snippet[: width - 1] + "…"


def _safe_snippet(text: str, query: str, *, width: int = 180) -> str:
    return _redact_sensitive_text(_snippet(text, query, width=width))


def _redact_sensitive_text(text: str) -> str:
    patterns = [
        (re.compile(r"(?i)(authorization\s*[:=]?\s*bearer\s+)[^\s,;}]+"), r"\1[REDACTED_AUTH]"),
        (re.compile(r"(?i)(authorization\s*[:=]\s*)[^\s,;}]+"), r"\1[REDACTED_AUTH]"),
        (re.compile(r"(?i)(cookie\s*[:=]\s*)[^\s,;}]+"), r"\1[REDACTED_COOKIE]"),
        (re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)(\s*[:=]\s*)[^\s,;}]+"), r"\1\2[REDACTED_SECRET]"),
        (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"), "[REDACTED_KEY]"),
    ]
    redacted = text
    for pattern, replacement in patterns:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _score(text: str, query: str) -> int:
    lowered = text.lower()
    return lowered.count(query) * 10 + min(len(query), 20)
