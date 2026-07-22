from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Literal

from app.services.agent_harness.workspace.conversation.workspace_preview_service import create_html_bundle_from_entry
from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
    get_conversation_dir,
)
from app.services.agent_harness.workspace.generated_content.file_version_store import (
    append_file_version,
    guess_file_type,
)

VersionedDeliverableKind = Literal["document", "sheet", "presentation", "web"]
SUPPORTED_VERSIONED_DELIVERABLE_KINDS: tuple[VersionedDeliverableKind, ...] = (
    "document",
    "sheet",
    "presentation",
    "web",
)

_VERSIONED_KIND_BY_FILE_TYPE: dict[str, VersionedDeliverableKind] = {
    "document": "document",
    "markdown": "document",
    "text": "document",
    "sheet": "sheet",
    "presentation": "presentation",
    "html": "web",
    "js_module": "web",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobWorkspaceService:
    def __init__(
        self,
        *,
        user_id: int,
        conversation_id: str,
        run_id: str,
        conversation_dir: Path | None = None,
    ) -> None:
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.run_id = run_id
        if conversation_dir is None:
            conversation_dir = get_conversation_dir(user_id, conversation_id)
        self.conversation_dir = Path(conversation_dir).resolve()
        self.work_dir = self.conversation_dir / "project"
        self.assets_dir = self.conversation_dir / "references"
        self.published_dir = self.conversation_dir / "published"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.published_dir.mkdir(parents=True, exist_ok=True)

    def publish_output(
        self,
        *,
        source_path: str,
        entry_path: str | None = None,
        validation: dict[str, Any] | None = None,
        mode: str | None = None,
        entry: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(mode or "file").strip().lower() or "file"
        if normalized_mode == "file":
            return self.publish_file_output(
                source_path=source_path,
                entry_path=entry_path,
                validation=validation,
                note=note,
            )
        if normalized_mode == "html_bundle":
            return self.publish_html_bundle_output(
                source_path=source_path,
                validation=validation,
                entry=entry,
                note=note,
            )
        raise ValueError(f"Unsupported publish mode: {mode}")

    def publish_file_output(
        self,
        *,
        source_path: str,
        entry_path: str | None = None,
        validation: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        del validation
        resolved_source = self._resolve_work_file(source_path)
        if not resolved_source.exists() or not resolved_source.is_file():
            raise FileNotFoundError(source_path)
        publish_source = entry_path or source_path
        file_name = self._infer_publish_name(publish_source)
        file_kind = self._infer_publish_kind(file_name)
        published = append_file_version(
            self.user_id,
            self.conversation_id,
            source_path=resolved_source,
            name=file_name,
            file_type=file_kind,
            run_id=self.run_id,
            note=note,
            artifact_metadata={"artifact_kind": "file"},
            created_by="agent",
        )
        return published

    def publish_html_bundle_output(
        self,
        *,
        source_path: str,
        validation: dict[str, Any] | None = None,
        entry: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        resolved_entry = self._resolve_work_file(source_path)
        if not resolved_entry.exists() or not resolved_entry.is_file():
            raise FileNotFoundError(source_path)
        if resolved_entry.suffix.lower() not in {".html", ".htm"}:
            raise ValueError("HTML bundle publish mode requires an .html or .htm entry file")

        bundle_path: Path | None = None
        try:
            bundle_path = create_html_bundle_from_entry(
                resolved_entry,
                files_root=resolved_entry.parent,
                output_dir=self.work_dir,
            )
            display_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", resolved_entry.stem).strip("-") or "bundle"
            display_name = f"{display_stem}.zip"
            published = append_file_version(
                self.user_id,
                self.conversation_id,
                source_path=bundle_path,
                name=display_name,
                file_type="web",
                run_id=self.run_id,
                note=note,
                artifact_metadata={
                    "artifact_kind": "web_bundle",
                    "bundle_format": "zip",
                    "entry": str(entry or (validation or {}).get("entry") or resolved_entry.name),
                    "source_path": self._work_relative_path(resolved_entry),
                    "members_count": int((validation or {}).get("bundle_member_count") or 0),
                },
                created_by="agent",
            )
            return published
        finally:
            if bundle_path is not None:
                try:
                    bundle_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _resolve_work_file(self, relative_path: str) -> Path:
        normalized = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
        if normalized.startswith("project/"):
            normalized = normalized[8:]
        elif normalized.startswith("work/"):
            raise FileNotFoundError(relative_path)
        candidate = (self.work_dir / normalized).resolve()
        candidate.relative_to(self.work_dir.resolve())
        return candidate

    def _infer_publish_name(self, entry_path: str) -> str:
        normalized = str(entry_path or "").replace("\\", "/").strip().lstrip("/")
        if normalized.startswith("project/"):
            normalized = normalized[8:]
        return Path(normalized).name or Path(entry_path).name

    def _infer_publish_kind(self, display_name: str) -> VersionedDeliverableKind:
        guessed_type = guess_file_type(display_name)
        inferred_kind = _VERSIONED_KIND_BY_FILE_TYPE.get(guessed_type)
        if inferred_kind is None:
            raise ValueError(
                f"Deliverable type '{guessed_type}' inferred from '{display_name}' is not supported for version publishing"
            )
        return inferred_kind

    def _work_relative_path(self, resolved_path: Path) -> str:
        return resolved_path.resolve().relative_to(self.work_dir.resolve()).as_posix()
