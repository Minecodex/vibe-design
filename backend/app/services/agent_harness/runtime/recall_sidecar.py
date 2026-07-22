from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.agent_harness.runtime.context_recall.store import load_collapse_commits
from app.services.agent_harness.runtime.conversation_events import load_conversation_events
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta
from app.services.agent_harness.runtime.system_write_lease import system_write_lease
from app.services.agent_harness.workspace.conversation.conversation_service import load_messages
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey


def recall_sidecar_path(user_id: int, conversation_id: str, *, meta_dir: Path | None = None) -> Path:
    return (meta_dir or ensure_harness_meta(user_id, conversation_id)) / "recall.sqlite"


def recall_cursor_path(user_id: int, conversation_id: str, *, meta_dir: Path | None = None) -> Path:
    return (meta_dir or ensure_harness_meta(user_id, conversation_id)) / "recall_cursor.json"


def _recall_system_write_paths() -> list[str]:
    return [
        ".meta/recall.sqlite",
        ".meta/recall.sqlite-journal",
        ".meta/recall.sqlite-shm",
        ".meta/recall.sqlite-wal",
        ".meta/recall_cursor.json",
    ]


def _load_cursor(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"last_message_seq": 0, "last_event_sequence": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"last_message_seq": 0, "last_event_sequence": 0}
    if not isinstance(data, dict):
        return {"last_message_seq": 0, "last_event_sequence": 0}
    return {
        "last_message_seq": int(data.get("last_message_seq") or 0),
        "last_event_sequence": int(data.get("last_event_sequence") or 0),
    }


def _save_cursor(path: Path, cursor: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "last_message_seq": int(cursor.get("last_message_seq") or 0),
                "last_event_sequence": int(cursor.get("last_event_sequence") or 0),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS recall_chunks ("
        "chunk_id TEXT PRIMARY KEY, source TEXT NOT NULL, source_id TEXT, seq INTEGER, "
        "created_at TEXT, text TEXT NOT NULL, metadata_json TEXT NOT NULL)"
    )
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS recall_chunks_fts USING fts5("
            "chunk_id UNINDEXED, text, tags)"
        )
    except sqlite3.OperationalError:
        pass
    return conn


def _message_text(message: dict[str, Any]) -> str:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    if str(metadata.get("message_kind") or "").strip() == "agent_context":
        return ""
    parts = [str(message.get("content") or "")]
    if message.get("tool_name"):
        parts.append(str(message.get("tool_name")))
    if isinstance(message.get("tool_calls"), list):
        parts.append(json.dumps(message["tool_calls"], ensure_ascii=False))
    for value in metadata.values():
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(part for part in parts if part)


def _tags(text: str) -> str:
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*|[\u4e00-\u9fff]{2,}", text)
    return " ".join(sorted(set(token.lower() for token in tokens if len(token) >= 2))[:80])


def rebuild_recall_sidecar(user_id: int, conversation_id: str, *, meta_dir: Path | None = None) -> dict[str, Any]:
    """Incrementally update the recall sidecar.

    Despite the legacy name, this no longer wipes the FTS index. It reads a
    cursor from ``.meta/recall_cursor.json`` and only indexes messages /
    events whose sequence exceeds the cursor.

    First-time entry (no cursor file) does NOT backfill history — it
    initializes the cursor to the current max sequence and returns. This
    matches the agreed-upon "no legacy data migration" scope.
    """
    db_path = recall_sidecar_path(user_id, conversation_id, meta_dir=meta_dir)
    cursor_path_ = recall_cursor_path(user_id, conversation_id, meta_dir=meta_dir)
    with system_write_lease(
        user_id=user_id,
        conversation_id=conversation_id,
        owner="recall_sidecar",
        paths=_recall_system_write_paths(),
        ttl_seconds=max(float(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_LEASE_SECONDS", 60) or 60), 1.0),
    ):
        return _rebuild_recall_sidecar_under_lease(
            user_id,
            conversation_id,
            meta_dir=meta_dir,
            db_path=db_path,
            cursor_path_=cursor_path_,
        )


def _rebuild_recall_sidecar_under_lease(
    user_id: int,
    conversation_id: str,
    *,
    meta_dir: Path | None,
    db_path: Path,
    cursor_path_: Path,
) -> dict[str, Any]:
    is_first_time = not cursor_path_.exists()
    cursor = _load_cursor(cursor_path_)

    if is_first_time:
        # Initialize cursor at current head, do not backfill.
        max_message_seq = 0
        for message in load_messages(user_id, conversation_id):
            try:
                max_message_seq = max(max_message_seq, int(message.get("_seq") or 0))
            except (TypeError, ValueError):
                continue
        max_event_seq = _latest_event_sequence(user_id, conversation_id)
        new_cursor = {
            "last_message_seq": max_message_seq,
            "last_event_sequence": max_event_seq,
        }
        _save_cursor(cursor_path_, new_cursor)
        # Ensure the SQLite file exists with the right schema so search calls work.
        conn = _connect(db_path)
        conn.close()
        return {"path": str(db_path), "chunks": 0, "skipped_initial_backfill": True}

    last_message_seq = int(cursor.get("last_message_seq") or 0)
    last_event_sequence = int(cursor.get("last_event_sequence") or 0)
    new_last_message_seq = last_message_seq
    new_last_event_sequence = last_event_sequence

    conn = _connect(db_path)
    try:
        count = 0
        for message in load_messages(user_id, conversation_id):
            try:
                msg_seq = int(message.get("_seq") or 0)
            except (TypeError, ValueError):
                continue
            if msg_seq <= last_message_seq:
                continue
            append_message_to_recall_sidecar(user_id, conversation_id, message, conn=conn, meta_dir=meta_dir)
            count += 1
            new_last_message_seq = max(new_last_message_seq, msg_seq)

        for event in _load_v2_compaction_boundary_events(user_id, conversation_id):
            seq_value = _event_sequence(event)
            if seq_value <= last_event_sequence:
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            _upsert_chunk(
                conn,
                chunk_id=f"compaction_boundary:{payload.get('boundary_id') or event.get('event_id') or seq_value or count}",
                source="compactions",
                source_id=str(payload.get("boundary_id") or event.get("event_id") or ""),
                seq=seq_value or None,
                created_at=event.get("created_at"),
                text=json.dumps(event, ensure_ascii=False, sort_keys=True),
                metadata={
                    "source_kind": "compaction_boundary_v2",
                    "boundary_id": payload.get("boundary_id"),
                    "compact_type": payload.get("compact_type"),
                },
            )
            count += 1
            new_last_event_sequence = max(new_last_event_sequence, seq_value)

        for commit in load_collapse_commits(user_id, conversation_id, meta_dir=meta_dir):
            seq_value = _event_sequence(commit)
            if seq_value <= last_event_sequence:
                continue
            _upsert_chunk(
                conn,
                chunk_id=f"collapse_commit:{commit.get('commit_id')}",
                source="collapse_commits",
                source_id=str(commit.get("commit_id") or ""),
                seq=seq_value or None,
                created_at=commit.get("created_at"),
                text=json.dumps(commit, ensure_ascii=False, sort_keys=True),
                metadata={"source_kind": "collapse_commit", "commit_id": commit.get("commit_id")},
            )
            count += 1
            new_last_event_sequence = max(new_last_event_sequence, seq_value)

        for event in _load_tool_result_events(user_id, conversation_id):
            seq_value = _event_sequence(event)
            if seq_value <= last_event_sequence:
                continue
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            text = json.dumps(payload.get("inline_payload") or payload, ensure_ascii=False, sort_keys=True)
            _upsert_chunk(
                conn,
                chunk_id=f"tool_result:{payload.get('result_ref') or event.get('id')}",
                source="tool_results",
                source_id=str(payload.get("result_ref") or event.get("id") or ""),
                seq=seq_value or None,
                created_at=event.get("created_at"),
                text=text,
                metadata={
                    "source_kind": "tool_result",
                    "result_ref": payload.get("result_ref"),
                    "tool": payload.get("tool"),
                    "preview": payload.get("preview"),
                },
            )
            count += 1
            new_last_event_sequence = max(new_last_event_sequence, seq_value)

        conn.commit()
    finally:
        conn.close()

    _save_cursor(
        cursor_path_,
        {
            "last_message_seq": new_last_message_seq,
            "last_event_sequence": new_last_event_sequence,
        },
    )
    return {"path": str(db_path), "chunks": count}


def _event_sequence(event: dict[str, Any]) -> int:
    if not isinstance(event, dict):
        return 0
    try:
        return int(event.get("sequence") or event.get("seq") or 0)
    except (TypeError, ValueError):
        return 0


def _load_v2_compaction_boundary_events(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for event in load_conversation_events(user_id, conversation_id):
        if str(event.get("type") or event.get("event_type") or "") != "compaction_boundary":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if int(payload.get("schema_version") or 0) != 2:
            continue
        events.append(event)
    return events


def rebuild_recall_sidecar_with_guard(
    user_id: int,
    conversation_id: str,
    *,
    meta_dir: Path | None = None,
    target_sequence: int | None = None,
) -> dict[str, Any]:
    version = target_sequence if target_sequence is not None else _latest_event_sequence(user_id, conversation_id)
    coordinator = EphemeralTaskCoordinator(
        ttl_seconds=max(float(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_LEASE_SECONDS", 60) or 60), 1.0)
    )
    lease = coordinator.start_sync(
        EphemeralTaskKey.build(
            domain="context-projection",
            kind="recall_sidecar_refresh",
            resource_parts=[user_id, conversation_id, "recall_sidecar_refresh"],
            version=version,
        ),
        owner_prefix="projection",
    )
    if not lease.acquired:
        return {"status": "skipped_duplicate", "chunks": None}
    try:
        result = rebuild_recall_sidecar(user_id, conversation_id, meta_dir=meta_dir)
    except Exception as exc:
        coordinator.fail_sync(lease, error_type=type(exc).__name__)
        raise
    coordinator.finish_sync(lease, status="done", result={"chunks": result.get("chunks")})
    return result


def append_message_to_recall_sidecar(
    user_id: int,
    conversation_id: str,
    message: dict[str, Any],
    *,
    conn: sqlite3.Connection | None = None,
    meta_dir: Path | None = None,
) -> None:
    owns_conn = conn is None
    lease_context = system_write_lease(
        user_id=user_id,
        conversation_id=conversation_id,
        owner="recall_sidecar",
        paths=_recall_system_write_paths(),
        ttl_seconds=30.0,
    ) if owns_conn else None
    if lease_context is not None:
        lease_context.__enter__()
    try:
        connection = conn or _connect(recall_sidecar_path(user_id, conversation_id, meta_dir=meta_dir))
        try:
            text = _message_text(message)
            if not text.strip():
                return
            _upsert_chunk(
                connection,
                chunk_id=f"message:{message.get('id') or message.get('_seq') or abs(hash(text))}",
                source="conversation",
                source_id=str(message.get("id") or ""),
                seq=int(message.get("_seq") or 0),
                created_at=message.get("created_at"),
                text=text,
                metadata={
                    "role": message.get("role"),
                    "tool_name": message.get("tool_name"),
                },
            )
            if owns_conn:
                connection.commit()
        finally:
            if owns_conn:
                connection.close()
    finally:
        if lease_context is not None:
            lease_context.__exit__(None, None, None)


def search_recall_sidecar(
    user_id: int,
    conversation_id: str,
    *,
    query: str,
    limit: int,
    before_seq: int | None = None,
    meta_dir: Path | None = None,
    sources: list[str] | None = None,
) -> list[dict[str, Any]] | None:
    path = recall_sidecar_path(user_id, conversation_id, meta_dir=meta_dir)
    if not path.exists():
        return None
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return []
    conn = _connect(path)
    try:
        candidates = _fts_search(conn, normalized_query, before_seq=before_seq, sources=sources)
        if not candidates:
            candidates = _like_search(conn, normalized_query.lower(), before_seq=before_seq, sources=sources)
    finally:
        conn.close()
    return candidates[: max(1, int(limit))]


def _fts_search(conn: sqlite3.Connection, query: str, *, before_seq: int | None, sources: list[str] | None) -> list[dict[str, Any]]:
    try:
        params: list[Any] = [_fts_query(query)]
        sql = "SELECT c.* FROM recall_chunks_fts f JOIN recall_chunks c ON c.chunk_id = f.chunk_id WHERE recall_chunks_fts MATCH ?"
        if sources:
            sql += f" AND c.source IN ({','.join('?' for _ in sources)})"
            params.extend([str(source) for source in sources])
        sql += " ORDER BY rank LIMIT 50"
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [_row_to_match(row, query) for row in rows if before_seq is None or int(row["seq"] or 0) < before_seq]


def _like_search(conn: sqlite3.Connection, query: str, *, before_seq: int | None, sources: list[str] | None) -> list[dict[str, Any]]:
    params: list[Any] = [f"%{query}%"]
    sql = "SELECT * FROM recall_chunks WHERE lower(text) LIKE ?"
    if sources:
        sql += f" AND source IN ({','.join('?' for _ in sources)})"
        params.extend([str(source) for source in sources])
    if before_seq is not None:
        sql += " AND seq < ?"
        params.append(int(before_seq))
    sql += " ORDER BY seq DESC LIMIT 50"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_match(row, query) for row in rows]


def _row_to_match(row: sqlite3.Row, query: str) -> dict[str, Any]:
    metadata = json.loads(row["metadata_json"] or "{}")
    text = str(row["text"] or "")
    out = {
        "source": row["source"],
        "id": row["source_id"],
        "seq": int(row["seq"] or 0) or None,
        "created_at": row["created_at"],
        "role": metadata.get("role"),
        "snippet": _safe_snippet(text, query),
        "score": _score(text, query),
    }
    if metadata.get("result_ref"):
        out["result_ref"] = metadata.get("result_ref")
    if metadata.get("boundary_id"):
        out["boundary_id"] = metadata.get("boundary_id")
    return out


def _fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_./-]+|[\u4e00-\u9fff]+", query)
    return " OR ".join(f'"{term}"' for term in terms[:8]) or f'"{query}"'


def _snippet(text: str, query: str, *, width: int = 180) -> str:
    lowered = text.lower()
    index = lowered.find(query.lower())
    if index < 0:
        return text[:width]
    start = max(0, index - width // 3)
    end = min(len(text), index + len(query) + width // 2)
    snippet = text[start:end].replace("\n", " ").strip()
    return snippet if len(snippet) <= width else snippet[: width - 1] + "..."


def _safe_snippet(text: str, query: str) -> str:
    return _redact_sensitive_text(_snippet(text, query))


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
    query = query.lower()
    terms = [term for term in re.split(r"\s+", query) if term]
    return lowered.count(query) * 20 + sum(5 for term in terms if term in lowered)


def _upsert_chunk(
    conn: sqlite3.Connection,
    *,
    chunk_id: str,
    source: str,
    source_id: str,
    seq: int | None,
    created_at: Any,
    text: str,
    metadata: dict[str, Any],
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO recall_chunks "
        "(chunk_id, source, source_id, seq, created_at, text, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            chunk_id,
            source,
            source_id,
            seq,
            created_at,
            text,
            json.dumps(metadata, ensure_ascii=False),
        ),
    )
    try:
        conn.execute("DELETE FROM recall_chunks_fts WHERE chunk_id = ?", (chunk_id,))
        conn.execute(
            "INSERT INTO recall_chunks_fts (chunk_id, text, tags) VALUES (?, ?, ?)",
            (chunk_id, text, _tags(text)),
        )
    except sqlite3.OperationalError:
        pass


def _load_tool_result_events(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events

    return [
        event
        for event in load_conversation_events(user_id, conversation_id)
        if str(event.get("type") or "") == "tool_result_recorded"
    ]


def _latest_event_sequence(user_id: int, conversation_id: str) -> int:
    latest = 0
    for event in load_conversation_events(user_id, conversation_id):
        try:
            latest = max(latest, int(event.get("sequence") or 0))
        except (TypeError, ValueError):
            continue
    return latest
