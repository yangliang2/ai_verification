from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest

import aiverify.runner.cli as cli
from aiverify.runner.admission import (
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    admit_production_seam,
    establish_and_abandon_temporary_record,
    verify_admitted_receipt,
    write_admission_receipt,
)
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.run_spec import RunSpec, load_run_spec


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


class FailingGitRunner(GitOnlyRunner):
    """Return one controlled Git failure while forbidding every other command."""

    def __init__(self, failing_args: tuple[str, ...]) -> None:
        super().__init__()
        self.failing_args = failing_args

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        if tuple(args[1:]) == self.failing_args:
            self.calls.append(list(args))
            return CommandResult(
                args=list(args),
                stdout="",
                stderr="controlled Git failure",
                returncode=1,
            )
        return super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )


class GitOutputOverrideRunner(GitOnlyRunner):
    """Override one successful Git identity response without allowing other tools."""

    def __init__(self, responses: dict[tuple[str, ...], str]) -> None:
        super().__init__()
        self.responses = responses

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        response = self.responses.get(tuple(args[1:]))
        if response is not None:
            self.calls.append(list(args))
            return CommandResult(
                args=list(args),
                stdout=response,
                stderr="",
                returncode=0,
            )
        return super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
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


def _assert_rejected_without_external_work(
    result, runner: GitOnlyRunner, *, check: str, reason: str, options: PlannedRunnerOptions
) -> None:
    assert result.admitted is False
    assert result.receipt["checks"][check]["status"] == "failed"
    assert any(reason in rejection_reason for rejection_reason in result.reasons)
    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert not (options.artifact_dir.parent / "execution-record.json").exists()


HostRejectionMutation = Callable[
    [Path, Path, RunSpec, PlannedRunnerOptions],
    tuple[RunSpec, PlannedRunnerOptions],
]


def _missing_host_project(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    return replace(spec, host_project=tmp_path / "missing-host"), options


def _non_root_workdir(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    nested = repository / "nested-workdir"
    nested.mkdir()
    return spec, replace(options, workdir=nested)


def _host_outside_repository(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    outside = tmp_path / "outside-host"
    outside.mkdir()
    return replace(spec, host_project=outside), replace(
        options, allow_host_project_subdir=True
    )


def _dirty_host_worktree(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")
    return spec, options


def _missing_host_locator(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    return replace(spec, host_locator=None), options


def _contradictory_host_origin(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    assert spec.host_locator is not None
    return replace(
        spec,
        host_locator=replace(
            spec.host_locator,
            expected_origin="https://example.invalid/other-project.git",
        ),
    ), options


def _invalid_expected_commit(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    return spec, replace(options, expected_source_commit="not-a-git-commit")


def _contradictory_expected_commit(
    tmp_path: Path,
    repository: Path,
    spec: RunSpec,
    options: PlannedRunnerOptions,
) -> tuple[RunSpec, PlannedRunnerOptions]:
    return spec, replace(options, expected_source_commit="a" * 40)


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


def test_serialized_run_spec_drift_is_rejected_before_external_work(
    tmp_path: Path,
) -> None:
    """A caller cannot substitute bytes after the Run Spec has been loaded."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()

    result = admit_production_seam(
        spec,
        options,
        serialized_run_spec=b"substituted Run Spec bytes\n",
        command_runner=runner,
    )

    _assert_rejected_without_external_work(
        result,
        runner,
        check="run_spec_bytes",
        reason="provided serialized Run Spec bytes drifted",
        options=options,
    )


def test_missing_serialized_run_spec_identity_is_rejected_before_external_work(
    tmp_path: Path,
) -> None:
    """Admission requires bytes and a checksum-bound source identity."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()

    result = admit_production_seam(
        replace(spec, source_path=None),
        options,
        command_runner=runner,
    )

    _assert_rejected_without_external_work(
        result,
        runner,
        check="run_spec_bytes",
        reason="exact serialized Run Spec source is unavailable",
        options=options,
    )


def test_unreadable_serialized_run_spec_is_rejected_before_external_work(
    tmp_path: Path,
) -> None:
    """A source read failure is rejection evidence, not an admitted input."""
    _, _, spec, options = _fixture(tmp_path)
    unreadable_source = tmp_path / "run-spec-directory"
    unreadable_source.mkdir()
    runner = GitOnlyRunner()

    result = admit_production_seam(
        replace(spec, source_path=unreadable_source),
        options,
        command_runner=runner,
    )

    _assert_rejected_without_external_work(
        result,
        runner,
        check="run_spec_bytes",
        reason="exact serialized Run Spec source cannot be read",
        options=options,
    )


def test_rejected_admission_receipt_is_persisted_exactly_once(tmp_path: Path) -> None:
    """The local receipt preserves a rejected admission without an external call."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()
    rejected = admit_production_seam(
        spec,
        replace(options, requested_driver_model=" "),
        command_runner=runner,
    )
    receipt_path = tmp_path / "admission-rejected.json"

    write_admission_receipt(rejected, receipt_path)

    assert rejected.admitted is False
    assert receipt_path.read_bytes() == rejected.receipt_bytes
    assert all(Path(call[0]).name == "git" for call in runner.calls)


def test_incomplete_serialized_receipt_is_rejected_before_external_work(
    tmp_path: Path,
) -> None:
    """A mapping receipt cannot omit bound identity fields and remain usable."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()

    with pytest.raises(ProductionSeamAdmissionError, match="Run Spec drift"):
        verify_admitted_receipt(
            {"admitted": True, "reasons": []},
            spec,
            options,
            command_runner=runner,
        )

    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert not (options.artifact_dir.parent / "execution-record.json").exists()


def test_serialized_admitted_receipt_revalidates_without_external_work(
    tmp_path: Path,
) -> None:
    """A complete serialized receipt remains usable only after fresh admission."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()
    admitted = admit_production_seam(spec, options, command_runner=runner)

    verify_admitted_receipt(
        dict(admitted.receipt),
        spec,
        options,
        command_runner=runner,
    )

    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert not (options.artifact_dir.parent / "execution-record.json").exists()


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("run_spec", "Run Spec drift"),
        ("runner_policy", "runner-option drift"),
        ("host", "source/worktree drift"),
        ("target", "target drift"),
        ("artifact_namespace", "artifact namespace drift"),
    ],
)
def test_serialized_receipt_identity_drift_is_rejected_before_external_work(
    tmp_path: Path, field: str, error: str
) -> None:
    """Every receipt identity component is revalidated before a runner advances."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()
    admitted = admit_production_seam(spec, options, command_runner=runner)
    serialized_receipt = dict(admitted.receipt)
    serialized_receipt[field] = {"drifted": field}

    with pytest.raises(ProductionSeamAdmissionError, match=error):
        verify_admitted_receipt(
            serialized_receipt,
            spec,
            options,
            command_runner=runner,
        )

    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert not (options.artifact_dir.parent / "execution-record.json").exists()


@pytest.mark.parametrize(
    ("spec_updates", "option_updates", "reason"),
    [
        ({"package": "invalid-package"}, {}, "Run Spec package identity is invalid"),
        ({"activity": ""}, {}, "Run Spec activity identity is required"),
        ({"apk_glob": "../outside.apk"}, {}, "APK locator escapes the host project"),
        ({"apk_glob": ""}, {}, "APK locator declaration is empty"),
        ({}, {"device": ""}, "deployment device identity is required"),
    ],
    ids=("package", "activity", "escaping-apk", "empty-apk", "device"),
)
def test_target_identity_rejections_are_side_effect_free(
    tmp_path: Path,
    spec_updates: dict[str, object],
    option_updates: dict[str, object],
    reason: str,
) -> None:
    """Malformed deployment identity cannot pass admission into external work."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()

    result = admit_production_seam(
        replace(spec, **spec_updates),
        replace(options, **option_updates),
        command_runner=runner,
    )

    _assert_rejected_without_external_work(
        result,
        runner,
        check="target_declaration",
        reason=reason,
        options=options,
    )


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (_missing_host_project, "host project directory is missing"),
        (_non_root_workdir, "runner workdir is not the repository root"),
        (_host_outside_repository, "host project is outside the repository root"),
        (_dirty_host_worktree, "host worktree is not clean"),
        (_missing_host_locator, "portable host origin and commit locator is required"),
        (_contradictory_host_origin, "host origin contradicts Run Spec locator"),
        (_invalid_expected_commit, "expected source commit binding is not a Git commit"),
        (_contradictory_expected_commit, "host commit contradicts Run Spec locator"),
    ],
    ids=(
        "missing-host",
        "non-root-workdir",
        "outside-host",
        "dirty-worktree",
        "missing-locator",
        "origin-drift",
        "invalid-commit",
        "commit-drift",
    ),
)
def test_host_identity_rejections_are_side_effect_free(
    tmp_path: Path,
    mutate: HostRejectionMutation,
    reason: str,
) -> None:
    """Host provenance failures stop before any Verification Agent work."""
    repository, _, spec, options = _fixture(tmp_path)
    spec, options = mutate(tmp_path, repository, spec, options)
    runner = GitOnlyRunner()

    result = admit_production_seam(spec, options, command_runner=runner)

    _assert_rejected_without_external_work(
        result,
        runner,
        check="host_identity",
        reason=reason,
        options=options,
    )


def test_failed_git_identity_query_is_rejected_before_external_work(
    tmp_path: Path,
) -> None:
    """A failed read-only identity query cannot downgrade into an admitted host."""
    _, _, spec, options = _fixture(tmp_path)
    runner = FailingGitRunner(("remote", "get-url", "origin"))

    result = admit_production_seam(spec, options, command_runner=runner)

    _assert_rejected_without_external_work(
        result,
        runner,
        check="host_identity",
        reason="git identity command failed (remote get-url origin)",
        options=options,
    )


@pytest.mark.parametrize(
    "responses",
    [
        {("remote", "get-url", "origin"): "\n"},
        {("rev-parse", "HEAD"): "not-a-git-commit\n"},
    ],
    ids=("missing-origin", "invalid-commit"),
)
def test_unavailable_host_identity_is_rejected_before_external_work(
    tmp_path: Path, responses: dict[tuple[str, ...], str]
) -> None:
    """Empty or malformed Git identity output is not treated as provenance."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOutputOverrideRunner(responses)

    result = admit_production_seam(spec, options, command_runner=runner)

    _assert_rejected_without_external_work(
        result,
        runner,
        check="host_identity",
        reason="host origin or commit identity is unavailable",
        options=options,
    )


@pytest.mark.parametrize(
    ("option_updates", "reason"),
    [
        ({"backend": "unsupported"}, "unsupported Verification Agent Backend"),
        ({"runner_policy_version": " "}, "runner policy version is required"),
        ({"requested_driver_model": " "}, "requested driver model cannot be empty"),
        ({"requested_l3_model": " "}, "requested L3 model cannot be empty"),
        ({"android_bin": "missing-admission-tool"}, "runner prerequisite is not executable"),
    ],
    ids=("backend", "policy-version", "driver-model", "l3-model", "tool"),
)
def test_runner_policy_rejections_are_side_effect_free(
    tmp_path: Path,
    option_updates: dict[str, object],
    reason: str,
) -> None:
    """Invalid Verification Agent policy cannot progress beyond admission."""
    _, _, spec, options = _fixture(tmp_path)
    options = replace(options, **option_updates)
    runner = GitOnlyRunner()

    result = admit_production_seam(spec, options, command_runner=runner)

    _assert_rejected_without_external_work(
        result,
        runner,
        check="runner_policy",
        reason=reason,
        options=options,
    )


@pytest.mark.parametrize(
    ("artifact_dir", "reason"),
    [
        (Path("/"), "artifact namespace must be an absolute directory"),
        (Path("/artifacts"), "artifact namespace must have a run directory"),
    ],
    ids=("filesystem-root", "root-run-directory"),
)
def test_invalid_artifact_namespace_is_rejected_before_external_work(
    tmp_path: Path, artifact_dir: Path, reason: str
) -> None:
    """An ambiguous output namespace cannot become an admitted formal attempt."""
    _, _, spec, options = _fixture(tmp_path)
    runner = GitOnlyRunner()

    result = admit_production_seam(
        spec,
        replace(options, artifact_dir=artifact_dir),
        command_runner=runner,
    )

    assert result.admitted is False
    assert result.receipt["checks"]["artifact_namespace"]["status"] == "failed"
    assert any(reason in rejection_reason for rejection_reason in result.reasons)
    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert not (tmp_path / "run" / "execution-record.json").exists()


@pytest.mark.parametrize(
    "artifact_name",
    (
        "execution-record.json",
        "verdict.json",
        "live-validation-gate.json",
        "runner-setup.json",
    ),
)
def test_existing_formal_artifact_rejects_namespace_without_mutation(
    tmp_path: Path, artifact_name: str
) -> None:
    """Admission never overwrites artifacts from a prior formal attempt."""
    _, _, spec, options = _fixture(tmp_path)
    marker = options.artifact_dir.parent / artifact_name
    marker.parent.mkdir(parents=True)
    marker.write_text("frozen prior output\n", encoding="utf-8")
    runner = GitOnlyRunner()

    result = admit_production_seam(spec, options, command_runner=runner)

    assert result.admitted is False
    assert result.receipt["checks"]["artifact_namespace"] == {
        "status": "failed",
        "message": f"formal attempt namespace already contains {artifact_name}",
    }
    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert marker.read_text(encoding="utf-8") == "frozen prior output\n"


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


def test_serialized_receipt_drift_blocks_public_runner_before_execution_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tampered receipt must fail before the public runner establishes an attempt."""
    _, _, spec, options = _fixture(tmp_path)
    spec = replace(
        spec,
        live_validation=replace(
            spec.live_validation,
            android_bin=options.android_bin,
            adb_bin=options.adb_bin,
        ),
    )
    options = replace(options, codex_bin="codex")
    runner = GitOnlyRunner()
    admitted = admit_production_seam(spec, options, command_runner=runner)
    serialized_receipt = dict(admitted.receipt)
    serialized_receipt["target"] = {"drifted": True}

    def fail_if_established(*args, **kwargs):
        pytest.fail("formal ExecutionRecord was established before receipt validation")

    monkeypatch.setattr(cli.ExecutionRecordStore, "establish", fail_if_established)
    with pytest.raises(ProductionSeamAdmissionError, match="target drift"):
        cli.run(
            spec,
            device=options.device,
            artifact_dir=options.artifact_dir,
            workdir=options.workdir,
            model=options.requested_driver_model,
            run_spec_path=spec.source_path,
            admission_required=True,
            admission_receipt=serialized_receipt,
            admission_options=options,
            admission_command_runner=runner,
        )

    assert all(Path(call[0]).name == "git" for call in runner.calls)
    assert not (options.artifact_dir.parent / "execution-record.json").exists()


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
