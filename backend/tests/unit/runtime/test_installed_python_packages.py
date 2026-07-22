from __future__ import annotations

from types import SimpleNamespace

from runtime.installed_python_packages import collect_installed_packages, main


def test_collect_installed_packages_normalizes_distribution_names():
    distributions = [
        SimpleNamespace(metadata={"Name": "My_Package"}, version="1.2.3"),
        SimpleNamespace(metadata={"Name": "another.package"}, version="4.5.6"),
    ]

    installed = collect_installed_packages(distributions)

    assert installed == {
        "my-package": "1.2.3",
        "another-package": "4.5.6",
    }


def test_main_prints_installed_packages_as_sorted_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "runtime.installed_python_packages.collect_installed_packages",
        lambda distributions=None: {
            "z-package": "9.9.9",
            "a-package": "1.0.0",
        },
    )

    exit_code = main([])

    assert exit_code == 0
    assert capsys.readouterr().out == '{\n  "a-package": "1.0.0",\n  "z-package": "9.9.9"\n}\n'
