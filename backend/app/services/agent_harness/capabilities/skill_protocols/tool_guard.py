from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent_harness.capabilities.skill_protocols.base import (
    ProtocolFailure,
    RuntimeExecutionContract,
    SkillProtocol,
)
from app.services.agent_harness.capabilities.skill_protocols.registry import resolve_protocol_for_context
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult
from app.services.agent_harness.runtime.effect_journal import record_effect_journal_entry
from app.services.agent_harness.runtime.system_write_lease import is_system_write_leased
from app.services.agent_harness.runtime.artifacts.policy import ToolPolicyService

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


FileSnapshot = dict[str, tuple[int, int]]


class ProtocolToolGuard:
    """Protocol-level guardrails for tools that mutate or publish artifacts."""

    def __init__(self, ctx: "HarnessContext", protocol: SkillProtocol | None = None) -> None:
        self.ctx = ctx
        self.protocol = protocol or resolve_protocol_for_context(ctx)
        self.contract = build_runtime_execution_contract(ctx, self.protocol)
        self.runtime_policy = ToolPolicyService(ctx)

    def check_write_target(self, normalized_path: str, *, operation: str = "write") -> ProtocolFailure | None:
        runtime_failure = self.runtime_policy.check_write_target(normalized_path, operation=operation)
        if runtime_failure is not None:
            return runtime_failure
        contract = self.contract
        if contract is None or not contract.artifact_work_root:
            return None
        target = _normalize_artifact_path(normalized_path)
        if not target:
            return None
        if _same_artifact_path(target, contract.artifact_input_path):
            return None
        if _is_readonly_work_target(target):
            return self.build_failure("readonly_input_write", target=target)
        if _is_inside_root(target, contract.artifact_work_root):
            if operation == "delete" and target == contract.active_entry:
                return self.build_failure("protocol_structure_missing", target=target)
            return None
        return self.build_failure("artifact_work_root_mismatch", target=target)

    def check_publish_entry(self, entry_relative_path: str) -> ProtocolFailure | None:
        runtime_failure = self.runtime_policy.check_publish_entry(entry_relative_path)
        if runtime_failure is not None:
            return runtime_failure
        return None

    def snapshot_effects(self) -> FileSnapshot | None:
        snapshot: FileSnapshot = {}
        roots = [
            self.ctx.references_dir,
            self.ctx.skill_dir,
            self.ctx.published_dir,
            self.ctx.agent_dir,
            self.ctx.meta_dir,
            self.ctx.logs_dir,
        ]
        if self.contract is not None or self.runtime_policy.active:
            roots.insert(0, self.ctx.project_dir)
        for root in roots:
            if not root.exists():
                continue
            for path in _iter_snapshot_files(root):
                try:
                    stat = path.stat()
                    rel = path.resolve().relative_to(self.ctx.conversation_dir.resolve()).as_posix()
                except OSError:
                    continue
                snapshot[rel] = (int(stat.st_size), int(stat.st_mtime_ns))
        return snapshot

    def check_command_effects(self, before: FileSnapshot | None) -> ProtocolFailure | None:
        contract = self.contract
        if before is None:
            return None
        after = self.snapshot_effects() or {}
        changed_paths = sorted(
            path for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        )
        if not changed_paths:
            return None
        journal_paths: list[dict[str, Any]] = []
        for path in changed_paths:
            after_stat = after.get(path)
            if self._is_system_owned_change(path, after_stat[1] if after_stat is not None else None):
                journal_paths.append({
                    "path": path,
                    "attribution": "system_write_lease",
                    "allowed": True,
                })
                continue
            failure = self._failure_for_changed_conversation_path(path)
            if failure is not None:
                journal_paths.append({
                    "path": path,
                    "attribution": "tool",
                    "allowed": False,
                    "failure_kind": failure.failure_kind,
                })
                self._record_effect_journal(result="blocked", changed_paths=journal_paths)
                return failure
            journal_paths.append({
                "path": path,
                "attribution": "tool",
                "allowed": True,
            })
        self._record_effect_journal(result="allowed", changed_paths=journal_paths)
        return None

    def _is_system_owned_change(self, conversation_path: str, changed_mtime_ns: int | None) -> bool:
        try:
            tool_scope = self.ctx.get_tool_stream_scope() or {}
        except RuntimeError:
            tool_scope = {}
        return is_system_write_leased(
            user_id=self.ctx.user_id,
            conversation_id=self.ctx.conversation_id,
            conversation_path=conversation_path,
            changed_mtime_ns=changed_mtime_ns,
            run_id=self.ctx.run_id,
            tool_call_id=tool_scope.get("tool_call_id"),
            workspace_root=self.ctx.workspace_root,
        )

    def _record_effect_journal(self, *, result: str, changed_paths: list[dict[str, Any]]) -> None:
        try:
            tool_scope = self.ctx.get_tool_stream_scope() or {}
        except RuntimeError:
            tool_scope = {}
        try:
            record_effect_journal_entry(
                user_id=self.ctx.user_id,
                conversation_id=self.ctx.conversation_id,
                run_id=self.ctx.run_id,
                tool_call_id=tool_scope.get("tool_call_id"),
                tool_name=str(tool_scope.get("tool_name") or "exec_command"),
                result=result,
                changed_paths=changed_paths,
                workspace_root=self.ctx.workspace_root,
            )
        except Exception:
            pass

    def _failure_for_changed_conversation_path(self, conversation_path: str) -> ProtocolFailure | None:
        runtime_failure = self.runtime_policy.check_changed_conversation_path(conversation_path)
        if runtime_failure is not None:
            return runtime_failure
        rel = _normalize_artifact_path(conversation_path)
        if rel.startswith("references/") or rel == "references" or rel.startswith("skill/") or rel == "skill":
            return self.build_failure("readonly_input_write", target=rel)
        if rel.startswith("published/") or rel == "published":
            return self.build_failure("system_root_write", target=rel)
        if (
            rel.startswith(".agent/")
            or rel == ".agent"
            or rel.startswith(".meta/")
            or rel == ".meta"
            or rel.startswith("logs/")
            or rel == "logs"
        ):
            return self.build_failure("hidden_root_write", target=rel)
        contract = self.contract
        if contract is None or not contract.artifact_work_root:
            return None
        if not rel.startswith("project/"):
            return None
        project_rel = rel.removeprefix("project/").strip("/")
        if _is_inside_root(project_rel, contract.artifact_work_root):
            return None
        return self.build_failure("artifact_work_root_mismatch", target=project_rel)

    def build_failure(self, failure_kind: str, *, target: str | None = None) -> ProtocolFailure:
        contract = self.contract or RuntimeExecutionContract()
        active_entry = contract.active_entry
        artifact_work_root = contract.artifact_work_root
        family = self.protocol.family
        message, action, next_tool = _failure_guidance(
            failure_kind,
            target=target,
            active_entry=active_entry,
            artifact_work_root=artifact_work_root,
        )
        return ProtocolFailure(
            failure_kind=failure_kind,
            message=message,
            expected_active_entry=active_entry,
            allowed_artifact_work_root=artifact_work_root,
            suggested_next_tool=next_tool,
            suggested_action=action,
            protocol_family=family,
        )


def build_runtime_execution_contract(
    ctx: "HarnessContext",
    protocol: SkillProtocol | None = None,
) -> RuntimeExecutionContract | None:
    resolved_protocol = protocol or resolve_protocol_for_context(ctx)
    if resolved_protocol.runtime_execution_contract is not None:
        return resolved_protocol.runtime_execution_contract
    session = getattr(ctx, "prepared_workspace", None)
    entry_path = str(getattr(session, "entry_path", "") or "").replace("\\", "/").strip().strip("/")
    artifact_work_root = str(getattr(session, "artifact_work_root", "") or "").replace("\\", "/").strip().strip("/")
    if not entry_path or not artifact_work_root:
        prepared_entry = str(getattr(ctx, "prepared_entry_file", "") or "").replace("\\", "/").strip().strip("/")
        prepared_dir = str(getattr(ctx, "artifact_work_root", "") or "").replace("\\", "/").strip().strip("/")
        entry_path = prepared_entry
        artifact_work_root = prepared_dir or (prepared_entry.split("/", 1)[0] if "/" in prepared_entry else "")
    if not entry_path or not artifact_work_root:
        return None
    return RuntimeExecutionContract(
        active_entry=entry_path,
        artifact_work_root=artifact_work_root,
        writable_roots=[artifact_work_root],
        readonly_roots=["references", "skill", "published"],
        validation_profile=resolved_protocol.family,
    )


def tool_result_from_protocol_failure(
    failure: ProtocolFailure,
    *,
    metadata: dict[str, Any] | None = None,
) -> ToolResult:
    payload = failure.to_payload()
    result_metadata = {
        "failure_kind": failure.failure_kind,
        "protocol_failure": payload,
        "recovery_hint": failure.recovery_hint(),
        **(metadata or {}),
    }
    return ToolResult(output=failure.message, is_error=True, metadata=result_metadata)


def _failure_guidance(
    failure_kind: str,
    *,
    target: str | None,
    active_entry: str | None,
    artifact_work_root: str | None,
) -> tuple[str, str, str]:
    entry = f"project/{active_entry}" if active_entry else "当前协议发布目标"
    root = f"project/{artifact_work_root}/" if artifact_work_root else "当前 artifact work directory"
    target_label = target or "目标路径"
    if failure_kind == "readonly_input_write":
        message = (
            f"协议把 {target_label} 所在区域标记为只读输入素材区，例如 references/ 或 skill/。"
            f"这些文件只能作为参考输入，不能直接当成交付产物修改。"
        )
        action = f"如果需要这些资源，请复制到当前 artifact work directory（{root}）内再引用。"
        return message, action, "exec_command"
    if failure_kind == "system_root_write":
        message = f"协议把 {target_label} 标记为系统管理的发布区，不能由命令直接写入。"
        action = f"请只在当前 artifact work directory（{root}）内生成交付物，先用 register_artifact 登记主入口，再通过 publish_output 发布。"
        return message, action, "register_artifact"
    if failure_kind == "hidden_root_write":
        message = f"协议把 {target_label} 标记为内部隐藏状态目录，不能作为模型可见输入或输出。"
        action = f"请把可交付内容写回当前 artifact work directory（{root}）；不要读写 .agent/、.meta/ 或 logs/。"
        return message, action, "exec_command"
    if failure_kind == "protocol_structure_missing":
        message = f"操作会破坏当前协议骨架：{target_label} 是主入口或关键结构。"
        action = f"先恢复 {entry} 的协议骨架，再用 edit_file 修改内容区域。"
        return message, action, "edit_file"
    message = f"写入目标 {target_label} 不在当前 artifact work directory（{root}）内。"
    action = f"回到 {root} 继续执行；最终文件完成后再调用 register_artifact 登记 manifest entry。"
    return message, action, "write_file"


def _normalize_artifact_path(path: str | None) -> str:
    normalized = str(path or "").replace("\\", "/").strip().lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def _is_inside_root(path: str, root: str | None) -> bool:
    normalized = _normalize_artifact_path(path)
    normalized_root = _normalize_artifact_path(root)
    return bool(normalized_root) and (normalized == normalized_root or normalized.startswith(f"{normalized_root}/"))


def _is_readonly_work_target(path: str) -> bool:
    normalized = _normalize_artifact_path(path)
    return normalized == "references" or normalized.startswith("references/") or normalized == "skill" or normalized.startswith("skill/")


def _same_artifact_path(left: str | None, right: str | None) -> bool:
    return bool(_normalize_artifact_path(left)) and _normalize_artifact_path(left) == _normalize_artifact_path(right)


def _iter_snapshot_files(root: Path):
    ignored_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__"}
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in ignored_dirs:
                    continue
                stack.append(entry)
            elif entry.is_file():
                yield entry
