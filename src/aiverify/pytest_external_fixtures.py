from __future__ import annotations

import pytest


EXTERNAL_FIXTURE_MARKER = "external_fixture"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("aiverify")
    group.addoption(
        "--run-external-fixtures",
        action="store_true",
        default=False,
        help="run tests that require explicitly admitted repository-external fixtures",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        f"{EXTERNAL_FIXTURE_MARKER}: requires an explicitly admitted repository-external fixture",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--run-external-fixtures"):
        return

    skipped = pytest.mark.skip(
        reason="repository-external fixture tests require explicit admission"
    )
    for item in items:
        if EXTERNAL_FIXTURE_MARKER in item.keywords:
            item.add_marker(skipped)
