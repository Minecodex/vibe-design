from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.critique.work_root import (
    normalize_relpath,
    safe_work_root,
    work_root_from_entry,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("html-ppt-prepared", "html-ppt-prepared"),
        ("project/html-ppt-prepared", "html-ppt-prepared"),
        ("/html-ppt-prepared/", "html-ppt-prepared"),
        ("html-ppt-prepared/index.html", "html-ppt-prepared/index.html"),
        ("project/a/b.html", "a/b.html"),
        ("", ""),
        (None, ""),
        ("../escape", ""),
        ("a/../b", ""),
    ],
)
def test_normalize_relpath(value, expected):
    assert normalize_relpath(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("html-ppt-prepared", "html-ppt-prepared"),
        ("project/html-ppt-prepared", "html-ppt-prepared"),
        ("html-ppt-prepared/index.html", ""),  # not a single component
        ("project/a/b", ""),
        ("", ""),
        (None, ""),
    ],
)
def test_safe_work_root(value, expected):
    assert safe_work_root(value) == expected


@pytest.mark.parametrize(
    "entry,expected",
    [
        ("html-ppt-prepared/index.html", "html-ppt-prepared"),
        ("project/html-ppt-prepared/index.html", "html-ppt-prepared"),
        ("a/b/c.html", "a"),
        ("index.html", ""),  # bare top-level file has no work root
        ("", ""),
        (None, ""),
    ],
)
def test_work_root_from_entry(entry, expected):
    assert work_root_from_entry(entry) == expected
