from app.services.agent_harness.capabilities.skills import catalog_service as skill_catalog_service


def test_skill_catalog_json_bytes_uses_generation_cache(monkeypatch):
    calls = {"build": 0}

    def _payload():
        calls["build"] += 1
        return [{"id": "web", "name": "Web"}]

    monkeypatch.setattr(skill_catalog_service, "_CATALOG_CACHE", None)
    monkeypatch.setattr(skill_catalog_service, "skills_generation", lambda: 1)
    monkeypatch.setattr(skill_catalog_service, "build_skill_catalog_payload", _payload)

    first = skill_catalog_service.skill_catalog_json_bytes()
    second = skill_catalog_service.skill_catalog_json_bytes()

    assert first == second
    assert calls["build"] == 1


def test_skill_catalog_json_bytes_rebuilds_when_generation_changes(monkeypatch):
    calls = {"build": 0, "generation": 1}

    def _payload():
        calls["build"] += 1
        return [{"id": f"skill-{calls['build']}", "name": "Skill"}]

    monkeypatch.setattr(skill_catalog_service, "_CATALOG_CACHE", None)
    monkeypatch.setattr(skill_catalog_service, "skills_generation", lambda: calls["generation"])
    monkeypatch.setattr(skill_catalog_service, "build_skill_catalog_payload", _payload)

    first = skill_catalog_service.skill_catalog_json_bytes()
    calls["generation"] = 2
    second = skill_catalog_service.skill_catalog_json_bytes()

    assert first != second
    assert calls["build"] == 2
