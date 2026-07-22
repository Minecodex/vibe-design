from __future__ import annotations

import json
import threading

from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.workspace.generated_content import asset_store
from app.services.agent_harness.workspace.generated_content.asset_store import list_assets, register_asset_bytes


def test_register_uploaded_asset_bytes_writes_to_reference_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Uploads")
    conversation_root = tmp_path / "users" / "7" / "conversations" / conversation["id"]

    asset = register_asset_bytes(
        7,
        conversation["id"],
        content=b"image-bytes",
        kind="input",
        original_name="photo.jpg",
        mime_type="image/jpeg",
        source="upload",
    )

    assert asset["path"] == "references/inputs/upload_001/source.jpg"
    assert (conversation_root / asset["path"]).read_bytes() == b"image-bytes"
    assert not (conversation_root / "assets").exists()

    metadata = json.loads(
        (conversation_root / "references" / "inputs" / "upload_001" / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["original_name"] == "photo.jpg"
    assert (conversation_root / ".meta" / "assets_manifest.json").is_file()


def test_register_asset_bytes_serializes_manifest_updates_across_threads(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Concurrent uploads")
    real_next_asset_id = asset_store._next_asset_id
    inner_done = threading.Event()
    inner_errors: list[BaseException] = []
    state = {"injected": False, "thread": None}

    def register_inner_asset() -> None:
        try:
            register_asset_bytes(
                7,
                conversation["id"],
                content=b"inner",
                kind="input",
                original_name="inner.txt",
                mime_type="text/plain",
                source="upload",
            )
        except BaseException as exc:  # pragma: no cover - surfaced after join
            inner_errors.append(exc)
        finally:
            inner_done.set()

    def interleaving_next_asset_id(root, prefix):
        candidate = real_next_asset_id(root, prefix)
        if not state["injected"]:
            state["injected"] = True
            thread = threading.Thread(target=register_inner_asset)
            state["thread"] = thread
            thread.start()
            inner_done.wait(timeout=0.25)
        return candidate

    monkeypatch.setattr(asset_store, "_next_asset_id", interleaving_next_asset_id)

    register_asset_bytes(
        7,
        conversation["id"],
        content=b"outer",
        kind="input",
        original_name="outer.txt",
        mime_type="text/plain",
        source="upload",
    )

    thread = state["thread"]
    assert isinstance(thread, threading.Thread)
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert inner_errors == []

    assets = sorted(list_assets(7, conversation["id"]), key=lambda item: item["asset_id"])
    assert [item["asset_id"] for item in assets] == ["upload_001", "upload_002"]
    assert [item["original_name"] for item in assets] == ["outer.txt", "inner.txt"]
