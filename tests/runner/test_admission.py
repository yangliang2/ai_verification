from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

import aiverify.runner.cli as cli
from aiverify.runner.admission import (
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    admit_production_seam,
    establish_and_abandon_temporary_record,
    verify_admitted_receipt,
)
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.run_spec import load_run_spec


class GitOnlyRunner(CommandRunner):
    """Allow read-only git identity queries and fail on device/tool calls."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(list(args))
        assert Path(args[0]).name == "git", f"prohibited command during admission: {args}"
        process = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        return CommandResult(
            args=list(args),
            stdout=process.stdout,
            stderr=process.stderr,
            returncode=process.returncode,
        )


def _git(cwd: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True
    )
    return process.stdout.strip()


def _fixture(tmp_path: Path, *, host_subdir: bool = False):
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Admission Test")
    _git(repository, "config", "user.email", "admission@example.invalid")
    (repository / "README.md").write_text("clean source\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-qm", "baseline")
    _git(repository, "remote", "add", "origin", "https://example.invalid/project.git")
    host = repository / "app" if host_subdir else repository
    host.mkdir(exist_ok=True)
    commit = _git(repository, "rev-parse", "HEAD")
    source = tmp_path / "run-spec.yaml"
    source.write_text(
        "host_project:\n"
        "  root: ${PROJECT_SOURCE}\n"
        "  origin: https://example.invalid/project.git\n"
        f"  commit: {commit}\n"
        "apk_glob: build/outputs/apk/**/*.apk\n"
        "package: org.example.project\n"
        "activity: org.example.project.MainActivity\n"
        "scenario:\n"
        "  id: admission-smoke\n",
        encoding="utf-8",
    )
    spec = load_run_spec(source, environ={"PROJECT_SOURCE": str(host)})
    binaries: dict[str, Path] = {}
    for name in ("android", "adb", "codex"):
        binary = tmp_path / "bin" / name
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text(f"#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
        binaries[name] = binary
    options = PlannedRunnerOptions(
        device="emulator-5554",
        workdir=repository,
        artifact_dir=tmp_path / "run" / "artifacts",
        requested_driver_model="m9-test-model",
        android_bin=str(binaries["android"]),
        adb_bin=str(binaries["adb"]),
        codex_bin=str(binaries["codex"]),
        allow_host_project_subdir=host_subdir,
    )
    return repository, host, spec, options


def test_root_host_admits_and_receipt_regeneration_is_deterministic(tmp_path: Path) -> None:
    repository, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()

    first = admit_production_seam(spec, options, command_runner=runner)
    second = admit_production_seam(spec, options, command_runner=runner)

    assert first.admitted is True
    assert first.receipt["status"] == "admitted"
    assert first.receipt["side_effects"] == {
        "external": False,
        "build": False,
        "device": False,
        "agent": False,
        "declaration": "read-only git and local source/metadata inspection only",
    }
    assert first.receipt_bytes == second.receipt_bytes
    assert first.receipt_sha256 == hashlib.sha256(first.receipt_bytes).hexdigest()
    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert str(repository) in first.receipt_bytes.decode("utf-8")


def test_codex_cli_default_model_selection_is_explicitly_admitted(
    tmp_path: Path,
) -> None:
    _, _, spec, options = _fixture(tmp_path)
    default_options = replace(
        options,
        requested_driver_model=None,
        requested_l3_model=None,
    )

    result = admit_production_seam(
        spec,
        default_options,
        command_runner=GitOnlyRunner(),
    )

    assert result.admitted is True
    assert result.receipt["runner_policy"]["options"][
        "requested_driver_model"
    ] is None
    assert result.receipt["runner_policy"]["tools"]["model_selection"] == {
        "journey_driver": {
            "policy": "codex_cli_default",
            "requested_model": None,
            "model_override_present": False,
        },
        "l3_semantic_judge": {
            "policy": "codex_cli_default",
            "requested_model": None,
            "model_override_present": False,
        },
    }


def test_empty_model_override_is_rejected(tmp_path: Path) -> None:
    _, _, spec, options = _fixture(tmp_path)
    result = admit_production_seam(
        spec,
        replace(options, requested_driver_model=""),
        command_runner=GitOnlyRunner(),
    )

    assert result.admitted is False
    assert "requested driver model cannot be empty" in result.reasons


def test_historical_host_subdirectory_is_rejected_without_device_side_effects(
    tmp_path: Path,
) -> None:
    _, _, spec, options = _fixture(tmp_path, host_subdir=True)
    # Construct the only policy difference directly so path normalization is explicit.
    strict_options = PlannedRunnerOptions(
        device=options.device,
        workdir=options.workdir,
        artifact_dir=options.artifact_dir,
        requested_driver_model=options.requested_driver_model,
        requested_l3_model=options.requested_l3_model,
        backend=options.backend,
        android_bin=options.android_bin,
        adb_bin=options.adb_bin,
        codex_bin=options.codex_bin,
        runner_policy_version=options.runner_policy_version,
        allow_host_project_subdir=False,
    )
    runner = GitOnlyRunner()

    result = admit_production_seam(spec, strict_options, command_runner=runner)

    assert result.admitted is False
    assert any("subdirectory" in reason for reason in result.reasons)
    assert all(Path(call[0]).name == "git" for call in runner.calls)


def test_corrected_host_subdirectory_policy_admits(tmp_path: Path) -> None:
    _, host, spec, options = _fixture(tmp_path, host_subdir=True)
    result = admit_production_seam(spec, options, command_runner=GitOnlyRunner())

    assert result.admitted is True
    assert result.receipt["host"]["host_project"] == str(host.resolve())
    assert result.receipt["host"]["host_project_within_repository"] is True


def test_sealed_run_spec_commit_can_bind_to_policy_after_mapping_release(
    tmp_path: Path,
) -> None:
    _, _, spec, options = _fixture(tmp_path)
    assert spec.host_locator is not None
    sealed_spec = replace(
        spec,
        host_locator=replace(spec.host_locator, expected_commit="b" * 40),
    )
    bound_options = replace(
        options,
        expected_source_commit=_git(options.workdir, "rev-parse", "HEAD"),
    )

    result = admit_production_seam(
        sealed_spec, bound_options, command_runner=GitOnlyRunner()
    )

    assert result.admitted is True
    assert result.receipt["runner_policy"]["options"]["expected_source_commit"] == (
        bound_options.expected_source_commit
    )


def test_formal_receipt_rejects_option_and_source_drift_before_external_calls(
    tmp_path: Path,
) -> None:
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()
    admitted = admit_production_seam(spec, options, command_runner=runner)
    changed_options = PlannedRunnerOptions(
        device=options.device,
        workdir=options.workdir,
        artifact_dir=options.artifact_dir,
        requested_driver_model="different-model",
        android_bin=options.android_bin,
        adb_bin=options.adb_bin,
        codex_bin=options.codex_bin,
    )
    with pytest.raises(
        ProductionSeamAdmissionError,
        match="formal runner options differ|runner-option drift",
    ):
        verify_admitted_receipt(
            admitted,
            spec,
            changed_options,
            command_runner=runner,
        )

    source = spec.source_path
    assert source is not None
    original = source.read_bytes()
    source.write_bytes(original + b"\n")
    try:
        with pytest.raises(ProductionSeamAdmissionError, match="Run Spec"):
            verify_admitted_receipt(
                admitted,
                spec,
                options,
                command_runner=runner,
            )
    finally:
        source.write_bytes(original)
    assert all(Path(call[0]).name == "git" for call in runner.calls)


def test_formal_runner_checks_receipt_before_establishing_execution_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()
    admitted = admit_production_seam(spec, options, command_runner=runner)
    changed_options = PlannedRunnerOptions(
        device=options.device,
        workdir=options.workdir,
        artifact_dir=options.artifact_dir,
        requested_driver_model="drifted-model",
        android_bin=options.android_bin,
        adb_bin=options.adb_bin,
        codex_bin=options.codex_bin,
    )

    def fail_if_established(*args, **kwargs):
        pytest.fail("formal ExecutionRecord was established before admission verification")

    monkeypatch.setattr(cli.ExecutionRecordStore, "establish", fail_if_established)
    with pytest.raises(
        ProductionSeamAdmissionError,
        match="formal runner options differ|runner-option drift",
    ):
        cli.run(
            spec,
            device=options.device,
            artifact_dir=options.artifact_dir,
            workdir=options.workdir,
            model=options.requested_driver_model,
            run_spec_path=spec.source_path,
            admission_required=True,
            admission_receipt=admitted,
            admission_options=changed_options,
            admission_command_runner=runner,
        )


def test_admission_rejects_preexisting_runner_setup_before_external_side_effects(
    tmp_path: Path,
) -> None:
    _, _, spec, options = _fixture(tmp_path)
    runner_setup = options.artifact_dir.parent / "runner-setup.json"
    runner_setup.parent.mkdir(parents=True)
    runner_setup.write_text('{"status":"stale"}\n', encoding="utf-8")
    runner = GitOnlyRunner()

    result = admit_production_seam(spec, options, command_runner=runner)

    assert result.admitted is False
    assert result.receipt["checks"]["artifact_namespace"] == {
        "status": "failed",
        "message": (
            "formal attempt namespace already contains runner-setup.json"
        ),
    }
    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert runner_setup.read_text(encoding="utf-8") == '{"status":"stale"}\n'


def test_temporary_admission_record_is_terminal_and_non_accountable(tmp_path: Path) -> None:
    _, _, spec, options = _fixture(tmp_path, host_subdir=True)
    rejected = admit_production_seam(spec, PlannedRunnerOptions(
        device=options.device,
        workdir=options.workdir,
        artifact_dir=options.artifact_dir,
        requested_driver_model=options.requested_driver_model,
        android_bin=options.android_bin,
        adb_bin=options.adb_bin,
        codex_bin=options.codex_bin,
    ), command_runner=GitOnlyRunner())

    record = establish_and_abandon_temporary_record(
        tmp_path / "temporary", scenario=spec.scenario.id, admission_receipt=rejected
    )

    assert record["lifecycle_state"] == "preflight_rejected"
    assert record["execution"]["accounting_eligible"] is False
    assert load_execution_record(tmp_path / "temporary" / "execution-record.json")[
        "execution"
    ]["reason"] == "production_seam_admission_rejected"
