from __future__ import annotations

import pytest

from runtime.incremental_pip_sync import main, requirements_to_install


def test_requirements_to_install_only_returns_missing_or_mismatched_specs(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements_dev = tmp_path / "requirements-dev.txt"
    requirements.write_text(
        "\n".join(
            [
                "# base runtime deps",
                "fastapi==0.115.5",
                "uvicorn[standard]==0.32.1  # keep in sync",
                "",
            ]
        ),
        encoding="utf-8",
    )
    requirements_dev.write_text(
        "\n".join(
            [
                "-r requirements.txt",
                "",
                "# dev helpers",
                "pytest==8.3.3",
                "",
            ]
        ),
        encoding="utf-8",
    )

    pending = requirements_to_install(
        [requirements_dev],
        installed_packages={
            "fastapi": "0.115.5",
            "pytest": "8.2.0",
        },
    )

    assert pending == [
        "uvicorn[standard]==0.32.1",
        "pytest==8.3.3",
    ]


def test_requirements_to_install_treats_extras_as_not_provably_satisfied(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("uvicorn[standard]==0.32.1\n", encoding="utf-8")

    pending = requirements_to_install(
        [requirements],
        installed_packages={
            "uvicorn": "0.32.1",
        },
    )

    assert pending == ["uvicorn[standard]==0.32.1"]


def test_requirements_to_install_does_not_uninstall_removed_packages(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi==0.115.5\n", encoding="utf-8")

    pending = requirements_to_install(
        [requirements],
        installed_packages={
            "fastapi": "0.115.5",
            "unused-package": "9.9.9",
        },
    )

    assert pending == []


def test_requirements_to_install_rejects_cyclic_includes(tmp_path):
    first = tmp_path / "requirements.txt"
    second = tmp_path / "requirements-dev.txt"
    first.write_text("-r requirements-dev.txt\n", encoding="utf-8")
    second.write_text("-r requirements.txt\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cyclic requirement include"):
        requirements_to_install([first], installed_packages={})


def test_requirements_to_install_keeps_duplicate_declaration_order_in_fingerprint_source(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.5\npytest==8.3.3\nfastapi==0.115.5\n",
        encoding="utf-8",
    )

    pending = requirements_to_install(
        [requirements],
        installed_packages={},
    )

    assert pending == [
        "fastapi==0.115.5",
        "pytest==8.3.3",
    ]


def test_requirements_to_install_rejects_conflicting_duplicate_package_specs(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "fastapi==0.115.5\nfastapi==0.116.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflicting requirement declarations for fastapi"):
        requirements_to_install([requirements], installed_packages={})


def test_requirements_to_install_supports_windows_include_paths(tmp_path):
    nested_dir = tmp_path / "deps"
    nested_dir.mkdir()
    included = nested_dir / "requirements-dev.txt"
    included.write_text("pytest==8.3.3\n", encoding="utf-8")
    root = tmp_path / "requirements.txt"
    root.write_text("-r deps\\requirements-dev.txt\n", encoding="utf-8")

    pending = requirements_to_install([root], installed_packages={})

    assert pending == ["pytest==8.3.3"]


def test_requirements_to_install_raises_for_missing_included_file(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("-r missing.txt\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        requirements_to_install([requirements], installed_packages={})


def test_main_prints_pending_requirements_one_per_line(tmp_path, capsys):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("fastapi==0.115.5\npytest==8.3.3\n", encoding="utf-8")

    exit_code = main(
        [
            "--installed-json",
            '{"fastapi": "0.115.5"}',
            str(requirements),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "pytest==8.3.3\n"


def test_main_rejects_malformed_installed_json(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest==8.3.3\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="invalid --installed-json"):
        main(
            [
                "--installed-json",
                "{not-json}",
                str(requirements),
            ]
        )


def test_main_rejects_non_object_installed_json(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest==8.3.3\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="must decode to a JSON object"):
        main(
            [
                "--installed-json",
                '["pytest"]',
                str(requirements),
            ]
        )
