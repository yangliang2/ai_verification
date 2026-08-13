from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[1]


def _pytest_env() -> dict[str, str]:
    env = dict(os.environ)
    python_path = [str(_ROOT / "src")]
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    env.pop("PYTEST_ADDOPTS", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _run_pytest(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "aiverify.pytest_external_fixtures",
            *arguments,
        ],
        cwd=tmp_path,
        env=_pytest_env(),
        check=False,
        capture_output=True,
        text=True,
    )


def _run_probe(
    tmp_path: Path,
    source: str,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    probe = tmp_path / "test_external_fixture_probe.py"
    probe.write_text(source, encoding="utf-8")
    return _run_pytest(tmp_path, *arguments, str(probe))


def test_default_run_skips_external_fixture(tmp_path: Path) -> None:
    result = _run_probe(
        tmp_path,
        """
import pytest


def test_local_fixture():
    pass


@pytest.mark.external_fixture
def test_repository_external_fixture():
    pass
""",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed, 1 skipped" in result.stdout


def test_explicit_option_runs_external_fixture(tmp_path: Path) -> None:
    result = _run_probe(
        tmp_path,
        """
import pytest


def test_local_fixture():
    pass


@pytest.mark.external_fixture
def test_repository_external_fixture():
    pass
""",
        "--run-external-fixtures",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout


def test_explicit_option_preserves_strict_source_identity(tmp_path: Path) -> None:
    invalid_snapshot = tmp_path / "not-a-git-repository"
    invalid_snapshot.mkdir()
    result = _run_probe(
        tmp_path,
        f"""
from pathlib import Path

import pytest

from aiverify.bench import m9_recovery_formal as formal


@pytest.mark.external_fixture
def test_invalid_external_snapshot():
    formal.validate_target_specific_preclaim(Path({str(invalid_snapshot)!r}))
""",
        "--run-external-fixtures",
    )

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "DiscoveryContractError" in output
    assert "source identity command failed" in output


def test_gate_is_discoverable_from_pytest_help(tmp_path: Path) -> None:
    help_result = _run_pytest(tmp_path, "--help")
    markers_result = _run_pytest(tmp_path, "--markers")

    assert help_result.returncode == 0, help_result.stdout + help_result.stderr
    assert "--run-external-fixtures" in help_result.stdout
    assert markers_result.returncode == 0, markers_result.stdout + markers_result.stderr
    assert "external_fixture" in markers_result.stdout
    assert "repository-external fixture" in markers_result.stdout
