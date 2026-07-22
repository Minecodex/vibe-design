from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import SkillProtocol, ValidationProfile, WritePolicy


def validate_protocol_html_path(path: Path, protocol: SkillProtocol | None) -> dict[str, Any]:
    if protocol is None:
        return _valid()
    profile = protocol.validation_profile
    if not profile.hard_block and not profile.checklist_path:
        return _valid(metadata=_profile_metadata(profile))
    if not path.exists() or not path.is_file():
        return _invalid(["protocol entry file does not exist"], profile)
    return validate_protocol_html_text(path.read_text(encoding="utf-8"), profile=profile, base_dir=path.parent)


def validate_protocol_write_content(
    content: str,
    *,
    normalized_path: str,
    protocol: SkillProtocol | None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    if protocol is None:
        return _valid()
    policy = protocol.write_policy
    if not _is_protected_path(normalized_path, policy):
        return _valid(metadata={"write_policy": policy.kind})
    if not policy.hard_block:
        return _valid(metadata={"write_policy": policy.kind, "protected_entry": True})
    profile = ValidationProfile(
        kind=policy.kind,
        required_selectors=policy.required_selectors,
        required_asset_refs=policy.required_asset_refs,
        hard_block=True,
    )
    result = validate_protocol_html_text(content, profile=profile, base_dir=base_dir)
    result.setdefault("metadata", {})["protected_entry"] = True
    return result


def validate_protocol_html_text(
    content: str,
    *,
    profile: ValidationProfile,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if profile.checklist_path:
        if not profile.checklist_source_path or not Path(profile.checklist_source_path).is_file():
            errors.append(f"protocol validation failed: checklist file is missing or unreadable: {profile.checklist_path}")
    for selector in profile.required_selectors:
        if not _html_contains_selector(content, selector):
            errors.append(f"protocol validation failed: missing required selector {selector}")
    for asset_ref in profile.required_asset_refs:
        if asset_ref not in content:
            errors.append(f"protocol validation failed: missing required asset reference {asset_ref}")
        elif base_dir is not None and not (base_dir / asset_ref).resolve().is_file():
            errors.append(f"protocol validation failed: required asset file is missing: {asset_ref}")
    if errors:
        return _invalid(errors, profile)
    return _valid(metadata=_profile_metadata(profile))


def _is_protected_path(normalized_path: str, policy: WritePolicy) -> bool:
    target = str(normalized_path or "").replace("\\", "/").strip().lstrip("/")
    if target.startswith("project/"):
        target = target[8:]
    return any(target == entry for entry in policy.protected_entry_paths)


def _html_contains_selector(content: str, selector: str) -> bool:
    selector = selector.strip()
    if selector.startswith("."):
        class_names = [item for item in selector.split(".") if item]
        class_attrs = re.findall(r"""class\s*=\s*["']([^"']*)["']""", content)
        for raw_classes in class_attrs:
            tokens = set(raw_classes.split())
            if all(class_name in tokens for class_name in class_names):
                return True
        return False
    if selector.startswith("#"):
        id_value = re.escape(selector[1:])
        return bool(re.search(r"""id\s*=\s*["']""" + id_value + r"""["']""", content))
    return selector in content


def _profile_metadata(profile: ValidationProfile) -> dict[str, Any]:
    return {
        "protocol_validation_profile": profile.kind,
        "protocol_required_selectors": list(profile.required_selectors),
        "protocol_required_asset_refs": list(profile.required_asset_refs),
        "protocol_checklist_path": profile.checklist_path,
        "protocol_checklist_available": bool(profile.checklist_source_path and Path(profile.checklist_source_path).is_file()),
    }


def _valid(*, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"valid": True, "errors": [], "metadata": metadata or {}}


def _invalid(errors: list[str], profile: ValidationProfile) -> dict[str, Any]:
    return {
        "valid": False,
        "errors": errors,
        "metadata": _profile_metadata(profile),
    }
