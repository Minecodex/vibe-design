"""Workspace cleanup strategy for Harness agent.

Provides scheduled and on-demand cleanup of conversation workspaces:
- TTL-based: remove workspaces for inactive conversations
- Size-based: cap per-user total workspace size
- Orphan detection: remove workspace dirs that no longer have a conversation record
"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.services.agent_harness.runtime.eventing.event_log import clear_conversation_event_caches
from app.services.agent_harness.workspace.conversation.conversation_service import get_conversation

logger = logging.getLogger(__name__)

# Defaults (can be overridden via config)
DEFAULT_TTL_DAYS = 30  # Delete workspaces for conversations inactive > N days
DEFAULT_MAX_USER_SIZE_MB = 2048  # 2GB per user


@dataclass
class CleanupStats:
    """Summary of a cleanup run."""
    orphan_dirs_removed: int = 0
    expired_dirs_removed: int = 0
    oversized_dirs_trimmed: int = 0
    bytes_freed: int = 0
    errors: list[str] | None = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def _workspace_root() -> Path:
    return Path(getattr(settings, "HARNESS_WORKSPACE_ROOT", "workspace"))


def _dir_size(path: Path) -> int:
    """Total size in bytes of all files under path."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return total


def _dir_mtime(path: Path) -> float:
    """Most recent modification time of any file under path."""
    latest = 0.0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                mt = f.stat().st_mtime
                if mt > latest:
                    latest = mt
    except Exception:
        pass
    return latest or path.stat().st_mtime


def _read_workspace_metadata(user_id: int, conversation_id: str) -> dict | None:
    conversation = get_conversation(user_id, conversation_id)
    if not isinstance(conversation, dict):
        return None
    return conversation


async def cleanup_workspaces(
    db=None,
    *,
    ttl_days: int = DEFAULT_TTL_DAYS,
    max_user_size_mb: int = DEFAULT_MAX_USER_SIZE_MB,
    dry_run: bool = False,
) -> CleanupStats:
    """Run full workspace cleanup.

    Should be called periodically (e.g. daily cron).
    The db parameter is kept for API compatibility but not used.
    """
    stats = CleanupStats()
    root = _workspace_root()
    users_dir = root / "users"

    if not users_dir.exists():
        return stats

    now = time.time()
    ttl_seconds = ttl_days * 86400

    for user_dir in users_dir.iterdir():
        if not user_dir.is_dir():
            continue

        try:
            user_id = int(user_dir.name)
        except ValueError:
            continue

        convs_dir = user_dir / "conversations"
        if not convs_dir.exists():
            continue

        for conv_dir in list(convs_dir.iterdir()):
            if not conv_dir.is_dir():
                continue

            meta = _read_workspace_metadata(user_id, conv_dir.name)

            # 1. Orphan: no active conversation record
            if meta is None:
                logger.info("Orphan workspace: %s", conv_dir)
                freed = _dir_size(conv_dir)
                if not dry_run:
                    _safe_remove(conv_dir, stats)
                    clear_conversation_event_caches(user_id, conv_dir.name)
                stats.orphan_dirs_removed += 1
                stats.bytes_freed += freed
                continue

            # 2. Deleted conversation
            if meta.get("status") == "deleted":
                logger.info("Deleted conv workspace: %s", conv_dir)
                freed = _dir_size(conv_dir)
                if not dry_run:
                    _safe_remove(conv_dir, stats)
                    clear_conversation_event_caches(user_id, conv_dir.name)
                stats.expired_dirs_removed += 1
                stats.bytes_freed += freed
                continue

            # 3. Inactive: no file changes for ttl_days
            last_modified = _dir_mtime(conv_dir)
            if now - last_modified > ttl_seconds:
                logger.info(
                    "Inactive workspace: %s (%.0f days)",
                    conv_dir, (now - last_modified) / 86400,
                )
                freed = _dir_size(conv_dir)
                if not dry_run:
                    _safe_remove(conv_dir, stats)
                    clear_conversation_event_caches(user_id, conv_dir.name)
                stats.expired_dirs_removed += 1
                stats.bytes_freed += freed
                continue

        # 4. Per-user size cap: remove oldest conversations first
        remaining = [d for d in convs_dir.iterdir() if d.is_dir()]
        total_size = sum(_dir_size(d) for d in remaining)
        max_bytes = max_user_size_mb * 1024 * 1024

        if total_size > max_bytes:
            by_age = sorted(remaining, key=_dir_mtime)
            for conv_dir in by_age:
                if total_size <= max_bytes:
                    break
                freed = _dir_size(conv_dir)
                logger.info(
                    "Size cap: removing %s (freed %d bytes)",
                    conv_dir, freed,
                )
                if not dry_run:
                    _safe_remove(conv_dir, stats)
                    clear_conversation_event_caches(user_id, conv_dir.name)
                total_size -= freed
                stats.oversized_dirs_trimmed += 1
                stats.bytes_freed += freed

    logger.info(
        "Workspace cleanup complete: orphans=%d expired=%d oversized=%d freed=%.1fMB errors=%d%s",
        stats.orphan_dirs_removed,
        stats.expired_dirs_removed,
        stats.oversized_dirs_trimmed,
        stats.bytes_freed / 1024 / 1024,
        len(stats.errors),
        " (dry run)" if dry_run else "",
    )
    return stats


def _safe_remove(path: Path, stats: CleanupStats) -> None:
    """Remove a directory tree, counting errors."""
    try:
        shutil.rmtree(path)
    except Exception as e:
        logger.warning("Failed to remove %s", path, exc_info=True)
        stats.errors.append(str(e))


def cleanup_single_conversation(
    user_id: int,
    conversation_id: str,
) -> int:
    """Remove workspace for a single conversation. Returns bytes freed."""
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir
    conv_dir = get_conversation_dir(user_id, conversation_id)
    if not conv_dir.exists():
        clear_conversation_event_caches(user_id, conversation_id)
        return 0
    freed = _dir_size(conv_dir)
    try:
        shutil.rmtree(conv_dir)
        logger.info("Cleaned workspace: user=%s conv=%s freed=%d", user_id, conversation_id, freed)
    except Exception:
        logger.warning("Failed to clean workspace: user=%s conv=%s", user_id, conversation_id, exc_info=True)
        freed = 0
    clear_conversation_event_caches(user_id, conversation_id)
    return freed


def get_workspace_stats(user_id: int) -> dict:
    """Get workspace usage stats for a user."""
    root = _workspace_root()
    user_dir = root / "users" / str(user_id) / "conversations"
    if not user_dir.exists():
        return {
            "user_id": user_id,
            "total_conversations": 0,
            "total_size_bytes": 0,
            "conversations": [],
        }

    conversations = []
    total_size = 0
    for conv_dir in sorted(user_dir.iterdir()):
        if not conv_dir.is_dir():
            continue
        size = _dir_size(conv_dir)
        file_count = sum(1 for f in conv_dir.rglob("*") if f.is_file())
        total_size += size
        conversations.append({
            "conversation_id": conv_dir.name,
            "size_bytes": size,
            "file_count": file_count,
        })

    return {
        "user_id": user_id,
        "total_conversations": len(conversations),
        "total_size_bytes": total_size,
        "conversations": sorted(conversations, key=lambda c: c["size_bytes"], reverse=True),
    }
