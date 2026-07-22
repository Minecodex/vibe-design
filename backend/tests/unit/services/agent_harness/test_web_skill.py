from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.services.agent_harness.capabilities.skills import get_skill


def _load_web_scaffolder_module():
    script_path = (
        Path(__file__).resolve().parents[4]
        / "app"
        / "services"
        / "agent_harness"
        / "capabilities"
        / "skills"
        / "web"
        / "scripts"
        / "landing_page_scaffolder.py"
    )
    spec = importlib.util.spec_from_file_location("test_web_scaffolder", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_skill_prompt_is_harness_aware():
    skill = get_skill("web")

    assert skill is not None
    assert "workspace contract" in skill.system_prompt.lower()
    assert "$SKILL_DIR" not in skill.system_prompt
    assert "$SCRATCH_DIR" not in skill.system_prompt
    assert "$GENERATED_DIR" not in skill.system_prompt
    assert "Do not assume Next.js" in skill.system_prompt
    assert "web_search" in skill.tools
    assert "exec_command" in skill.tools
    assert "list_files" in skill.tools
    assert "write_file" in skill.tools
    assert "edit_file" in skill.tools
    assert "workspace_map" in skill.tools
    assert "publish_output" in skill.tools
    assert "generate_video" in skill.tools


def test_web_scaffolder_renders_faq_in_tsx_and_html():
    module = _load_web_scaffolder_module()
    config = {
        "title": "Acme Landing Page",
        "meta_description": "Ship releases faster with fewer regressions.",
        "hero": {
            "headline": "Ship faster",
            "subheadline": "Catch regressions before they reach users.",
        },
        "faq": {
            "title": "Frequently Asked Questions",
            "items": [
                {"question": "Does it support staging?", "answer": "Yes, including previews."},
                {"question": "Can I self-host it?", "answer": "Enterprise plans can."},
            ],
        },
        "cta": {
            "headline": "Start now",
            "subheadline": "Deploy with confidence.",
            "text": "Start free trial",
            "url": "#start",
        },
    }

    tsx_output = module.generate_tsx(config)
    html_output = module.generate_html(config)

    assert "function FAQSection()" in tsx_output
    assert "<FAQSection />" in tsx_output
    assert '"@type":"FAQPage"' in tsx_output.replace(" ", "")
    assert "Frequently Asked Questions" in html_output
    assert "Does it support staging?" in html_output


def test_web_scaffolder_reads_config_from_stdin(monkeypatch, capsys):
    module = _load_web_scaffolder_module()
    payload = {
        "title": "StdIn Page",
        "hero": {"headline": "Hello", "subheadline": "World"},
    }
    monkeypatch.setattr(
        "sys.argv",
        ["landing_page_scaffolder.py", "-", "--format", "json"],
    )
    monkeypatch.setattr("sys.stdin.read", lambda: json.dumps(payload))

    module.main()

    stdout = capsys.readouterr().out
    assert '"title": "StdIn Page"' in stdout
