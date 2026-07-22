from pathlib import Path

from runtime.dev_requirements_fingerprint import compute_fingerprint


def test_compute_fingerprint_changes_when_primary_requirements_change(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements_dev = tmp_path / "requirements-dev.txt"
    requirements.write_text("fastapi==0.1.0\n", encoding="utf-8")
    requirements_dev.write_text("-r requirements.txt\npytest==8.0.0\n", encoding="utf-8")

    original = compute_fingerprint([requirements, requirements_dev])

    requirements.write_text("fastapi==0.2.0\n", encoding="utf-8")

    updated = compute_fingerprint([requirements, requirements_dev])

    assert updated != original


def test_compute_fingerprint_is_stable_for_same_files(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements_dev = tmp_path / "requirements-dev.txt"
    requirements.write_text("fastapi==0.1.0\n", encoding="utf-8")
    requirements_dev.write_text("-r requirements.txt\npytest==8.0.0\n", encoding="utf-8")

    first = compute_fingerprint([requirements, requirements_dev])
    second = compute_fingerprint([Path(requirements), Path(requirements_dev)])

    assert first == second


def test_compute_fingerprint_follows_nested_requirement_includes(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements_dev = tmp_path / "requirements-dev.txt"
    requirements.write_text("fastapi==0.1.0\n", encoding="utf-8")
    requirements_dev.write_text("-r requirements.txt\npytest==8.0.0\n", encoding="utf-8")

    original = compute_fingerprint([requirements_dev])

    requirements.write_text("fastapi==0.2.0\n", encoding="utf-8")

    updated = compute_fingerprint([requirements_dev])

    assert updated != original


def test_compute_fingerprint_is_independent_of_absolute_file_location(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()

    for root in (first_root, second_root):
        (root / "requirements.txt").write_text("fastapi==0.1.0\n", encoding="utf-8")
        (root / "requirements-dev.txt").write_text(
            "-r requirements.txt\npytest==8.0.0\n",
            encoding="utf-8",
        )

    first = compute_fingerprint([first_root / "requirements-dev.txt"])
    second = compute_fingerprint([second_root / "requirements-dev.txt"])

    assert first == second


def test_compute_fingerprint_changes_when_duplicate_requirement_order_changes(tmp_path):
    requirements = tmp_path / "requirements-dev.txt"
    requirements.write_text(
        "fastapi==0.1.0\npytest==8.3.3\nfastapi==0.1.0\n",
        encoding="utf-8",
    )

    original = compute_fingerprint([requirements])

    requirements.write_text(
        "fastapi==0.1.0\nfastapi==0.1.0\npytest==8.3.3\n",
        encoding="utf-8",
    )

    updated = compute_fingerprint([requirements])

    assert updated != original
