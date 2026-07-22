from pathlib import Path

from app.services.agent_harness.workspace.generated_content.entry_validation_service import (
    validate_serialized_content,
)


def test_html_validation_ignores_external_and_special_links(tmp_path: Path) -> None:
    result = validate_serialized_content(
        """
<!doctype html>
<html>
  <body>
    <a href="kakjzzw@gmail.com">Email</a>
    <a href="mailto:kakjzzw@gmail.com">Mailto</a>
    <a href="www.example.com/contact">Bare domain</a>
    <a href="//cdn.example.com/app.css">Protocol-relative CDN</a>
    <a href="whatsapp://send?phone=123">Custom protocol</a>
    <a href="sms:+15551234567">SMS</a>
  </body>
</html>
""",
        kind="html",
        path_hint="index.html",
        base_dir=tmp_path,
    )

    assert result["valid"] is True
    assert result["errors"] == []


def test_html_validation_still_rejects_missing_local_dependencies(tmp_path: Path) -> None:
    result = validate_serialized_content(
        '<html><head><link rel="stylesheet" href="missing.css"></head><body></body></html>',
        kind="html",
        path_hint="index.html",
        base_dir=tmp_path,
    )

    assert result["valid"] is False
    assert "missing.css" in result["errors"][0]


def test_html_validation_still_rejects_escaping_relative_dependencies(tmp_path: Path) -> None:
    result = validate_serialized_content(
        '<html><head><link rel="stylesheet" href="../secret.css"></head><body></body></html>',
        kind="html",
        path_hint="index.html",
        base_dir=tmp_path,
    )

    assert result["valid"] is False
    assert "../secret.css" in result["errors"][0]
