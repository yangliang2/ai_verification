"""Public-contract tests for source-authorized runtime preparation."""

from __future__ import annotations

import copy
import difflib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest

import aiverify.runner.cli as cli
from aiverify.injection import (
    CuratedSourceCatalog,
    CuratedSourceEntry,
    FaultOperator,
    FixtureAnchor,
    InjectionAdmission,
    InjectionCandidate,
    InjectionMaterializer,
    InjectionReceipt,
    SourceDelta,
    TaxonomyRelationship,
    VerifierPacket,
    admit_catalogued_candidate,
    capture_baseline_provenance,
    change_target_packet_id,
)
from aiverify.runner.admission import (
    HostAuthority,
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    SourceAuthority,
    admit_production_seam,
    verify_admitted_receipt,
)
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    AaptApkInspector,
    ApkInspector,
    ApkMetadata,
    CleanCheckoutSourceAuthority,
    RuntimeBuildRecipe,
    RuntimePreparationHandoff,
    RuntimePreparationVerificationError,
    SealedInjectionSourceAuthority,
    prepare_runtime_case,
    verify_runtime_preparation_receipt,
)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


class _SuccessfulBuild(CommandRunner):
    def __init__(self, apk_bytes: bytes) -> None:
        self.apk_bytes = apk_bytes
        self.calls: list[tuple[list[str], Path | None, int | None]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append((list(args), cwd, timeout_seconds))
        assert cwd is not None
        apk = cwd / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        apk.parent.mkdir(parents=True, exist_ok=True)
        apk.write_bytes(self.apk_bytes)
        return CommandResult(args=list(args), stdout="built\n", stderr="", returncode=0)


class _SourceDriftingBuild(_SuccessfulBuild):
    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        result = super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )
        assert cwd is not None
        (cwd / "source.txt").write_text("drifted during build\n", encoding="utf-8")
        return result


class _DuplicateAliasBuild(_SuccessfulBuild):
    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        result = super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )
        assert cwd is not None
        output = cwd / "build" / "outputs" / "apk" / "debug"
        (output / "alias-debug.apk").symlink_to("app-debug.apk")
        return result


class _ContradictoryBuild(_SuccessfulBuild):
    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        result = super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )
        return replace(result, args=["different-build"])


class _StaticApkInspector(ApkInspector):
    def __init__(
        self,
        *,
        package: str = "org.example.injected",
        launcher_activity: str = "org.example.injected.MainActivity",
    ) -> None:
        self.package = package
        self.launcher_activity = launcher_activity

    def inspect(self, apk_path: Path) -> ApkMetadata:
        return ApkMetadata(
            package=self.package,
            launcher_activity=self.launcher_activity,
        )


class _FailingApkInspector(ApkInspector):
    def inspect(self, apk_path: Path) -> ApkMetadata:
        raise RuntimeError("controlled inspection failure")


class _SourceDriftingApkInspector(_StaticApkInspector):
    def __init__(self, source_path: Path) -> None:
        super().__init__()
        self.source_path = source_path

    def inspect(self, apk_path: Path) -> ApkMetadata:
        metadata = super().inspect(apk_path)
        self.source_path.write_text("drifted during APK inspection\n", encoding="utf-8")
        return metadata


class _ApkDriftingInspector(_StaticApkInspector):
    def inspect(self, apk_path: Path) -> ApkMetadata:
        metadata = super().inspect(apk_path)
        apk_path.write_bytes(b"drifted during APK inspection")
        return metadata


class _EmptyHostSourceAuthority(SourceAuthority):
    def resolve_host(
        self,
        spec: RunSpec,
        options: PlannedRunnerOptions,
        runner: CommandRunner,
    ) -> dict[str, object]:
        return {}


class _ApkDriftingSourceAuthority(SourceAuthority):
    def __init__(self, apk_path: Path) -> None:
        self.apk_path = apk_path
        self.calls = 0
        self.delegate = CleanCheckoutSourceAuthority()

    def resolve_host(
        self,
        spec: RunSpec,
        options: PlannedRunnerOptions,
        runner: CommandRunner,
    ) -> HostAuthority:
        self.calls += 1
        resolved = self.delegate.resolve_host(spec, options, runner)
        if self.calls == 2:
            self.apk_path.write_bytes(b"drifted during source authority check")
        return resolved


class _NoApkBuild(CommandRunner):
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
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
        return CommandResult(
            args=list(args),
            stdout="",
            stderr="controlled build result",
            returncode=self.returncode,
        )


class _ReadOnlyGitRunner(CommandRunner):
    _ALLOWED = frozenset(
        {
            ("rev-parse", "--show-toplevel"),
            ("remote", "get-url", "origin"),
            ("rev-parse", "HEAD"),
            ("status", "--porcelain=v1", "--untracked-files=all"),
        }
    )

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
        assert Path(args[0]).name == "git"
        assert tuple(args[1:]) in self._ALLOWED
        self.calls.append(list(args))
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


class _AdmissionOrderedBuild(_SuccessfulBuild):
    def __init__(self, apk_bytes: bytes, admission_runner: _ReadOnlyGitRunner) -> None:
        super().__init__(apk_bytes)
        self.admission_runner = admission_runner

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        assert len(self.admission_runner.calls) == 4
        return super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )


class _OutsideApkBuild(_SuccessfulBuild):
    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        result = super().run(
            args,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            input_text=input_text,
        )
        assert cwd is not None
        output = cwd / "build" / "outputs" / "apk" / "debug"
        (output / "app-debug.apk").unlink()
        outside = cwd.parent / "outside.apk"
        outside.write_bytes(self.apk_bytes)
        (output / "app-debug.apk").symlink_to(outside)
        return result


@dataclass(frozen=True)
class _CleanCase:
    repository: Path
    host: Path
    spec: RunSpec
    options: PlannedRunnerOptions


def _clean_case(tmp_path: Path, *, host_subdir: bool = False) -> _CleanCase:
    repository = tmp_path / "clean-repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Runtime Preparation Test")
    _git(repository, "config", "user.email", "runtime@example.invalid")
    _git(repository, "remote", "add", "origin", "https://example.invalid/clean.git")
    host = repository / "app" if host_subdir else repository
    host.mkdir(exist_ok=True)
    ignored_build = "/app/build/" if host_subdir else "/build/"
    (repository / ".gitignore").write_text(f"{ignored_build}\n", encoding="utf-8")
    (host / "gradlew").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (host / "gradlew").chmod(0o755)
    (host / "source.txt").write_text("clean\n", encoding="utf-8")
    _git(repository, "add", ".gitignore", str(host.relative_to(repository)))
    _git(repository, "commit", "-m", "clean baseline")
    commit = _git(repository, "rev-parse", "HEAD")
    run_spec_path = tmp_path / "clean-run-spec.yaml"
    run_spec_path.write_text(
        "host_project:\n"
        "  root: ${PROJECT_SOURCE}\n"
        "  origin: https://example.invalid/clean.git\n"
        f"  commit: {commit}\n"
        "apk_glob: build/outputs/apk/**/*.apk\n"
        "package: org.example.injected\n"
        "activity: org.example.injected.MainActivity\n"
        "scenario:\n"
        "  id: clean-runtime-preparation\n",
        encoding="utf-8",
    )
    spec = load_run_spec(
        run_spec_path,
        environ={"PROJECT_SOURCE": str(host)},
    )
    options = PlannedRunnerOptions(
        device="emulator-5554",
        workdir=repository,
        artifact_dir=tmp_path / "clean-run" / "artifacts",
        android_bin=str(_executable(tmp_path / "clean-bin" / "android")),
        adb_bin=str(_executable(tmp_path / "clean-bin" / "adb")),
        codex_bin=str(_executable(tmp_path / "clean-bin" / "codex")),
        allow_host_project_subdir=host_subdir,
    )
    return _CleanCase(repository=repository, host=host, spec=spec, options=options)


@dataclass(frozen=True)
class _SealedCase:
    repository: Path
    materializer: InjectionMaterializer
    admission: InjectionAdmission
    receipt: InjectionReceipt
    packet: VerifierPacket
    worktree: Path
    spec: RunSpec
    options: PlannedRunnerOptions
    recipe: RuntimeBuildRecipe

    def cleanup(self) -> None:
        shutil.rmtree(self.worktree / "build", ignore_errors=True)
        self.materializer.cleanup(self.receipt)


def _sealed_case(tmp_path: Path) -> _SealedCase:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Runtime Preparation Test")
    _git(repository, "config", "user.email", "runtime@example.invalid")
    _git(repository, "remote", "add", "origin", "https://example.invalid/app.git")
    (repository / ".gitignore").write_text("/build/\n", encoding="utf-8")
    (repository / "gradlew").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (repository / "gradlew").chmod(0o755)
    (repository / "source.txt").write_text("baseline\n", encoding="utf-8")
    (repository / "fixture.txt").write_text("fixture\n", encoding="utf-8")
    _git(repository, "add", ".gitignore", "gradlew", "source.txt", "fixture.txt")
    _git(repository, "commit", "-m", "baseline")
    baseline_commit = _git(repository, "rev-parse", "HEAD")
    baseline = capture_baseline_provenance(repository, baseline_commit)

    patch_text = "".join(
        difflib.unified_diff(
            ["baseline\n"],
            ["injected\n"],
            fromfile="a/source.txt",
            tofile="b/source.txt",
        )
    )
    delta = SourceDelta.from_patch(
        delta_id="runtime-change",
        patch_text=patch_text,
        source_ref="patches/runtime-change.patch",
    )
    patch_path = repository / (delta.source_ref or "")
    patch_path.parent.mkdir()
    patch_path.write_text(delta.patch_text, encoding="utf-8")
    candidate = InjectionCandidate(
        candidate_id="runtime-candidate",
        baseline=baseline,
        source_delta=delta,
        operator=FaultOperator(
            operator_id="runtime-operator",
            version="v1",
            applicability="single fixture source",
            safety_boundary="local source preparation only",
        ),
        variant="defect",
    )
    entry = CuratedSourceEntry(
        source_id="runtime-source",
        candidate=candidate,
        patch_path=delta.source_ref or "",
        fixture_anchor=FixtureAnchor(
            path="fixture.txt",
            sha256=sha256((repository / "fixture.txt").read_bytes()).hexdigest(),
        ),
        population_classification="curated_controlled_injection",
        taxonomy_relationship=TaxonomyRelationship.known("runtime-test"),
    )
    catalog = CuratedSourceCatalog(entries=(entry,))
    catalog_path = repository / "catalog.json"
    catalog_path.write_text(json.dumps(catalog.to_dict()), encoding="utf-8")
    _git(repository, "add", "catalog.json", "patches")
    _git(repository, "commit", "-m", "catalog")

    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")
    admission = admit_catalogued_candidate(
        catalog_path,
        "runtime-source",
        materializer,
    )
    assert admission.status == "sealed"
    assert admission.receipt is not None
    receipt = admission.receipt
    assert receipt.worktree is not None
    packet = VerifierPacket(
        packet_id=change_target_packet_id(
            source_origin=baseline.source_origin,
            source_commit=baseline.commit,
            baseline_source_tree_sha256=baseline.source_tree_sha256,
            materialized_source_tree_sha256=receipt.result_source_tree_sha256 or "",
            patch_sha256=delta.patch_sha256,
            result_diff_sha256=receipt.result_diff_sha256 or "",
            receipt_identity_sha256=receipt.receipt_identity_sha256,
        ),
        source_origin=baseline.source_origin,
        source_commit=baseline.commit,
        baseline_source_tree_sha256=baseline.source_tree_sha256,
        materialized_source_tree_sha256=receipt.result_source_tree_sha256 or "",
        worktree_path=receipt.worktree.path,
        patch_format=delta.format,
        patch_path=str(patch_path.resolve()),
        patch_text=delta.patch_text,
        patch_sha256=delta.patch_sha256,
        result_diff_sha256=receipt.result_diff_sha256 or "",
        receipt_identity_sha256=receipt.receipt_identity_sha256,
    )

    worktree = Path(receipt.worktree.path)
    run_spec_path = tmp_path / "run-spec.yaml"
    run_spec_path.write_text(
        "host_project:\n"
        "  root: ${PROJECT_SOURCE}\n"
        f"  origin: {baseline.source_origin}\n"
        f"  commit: {baseline.commit}\n"
        "apk_glob: build/outputs/apk/**/*.apk\n"
        "package: org.example.injected\n"
        "activity: org.example.injected.MainActivity\n"
        "scenario:\n"
        "  id: runtime-preparation\n",
        encoding="utf-8",
    )
    spec = load_run_spec(run_spec_path, environ={"PROJECT_SOURCE": str(worktree)})
    options = PlannedRunnerOptions(
        device="emulator-5554",
        workdir=worktree,
        artifact_dir=tmp_path / "run" / "artifacts",
        android_bin=str(_executable(tmp_path / "bin" / "android")),
        adb_bin=str(_executable(tmp_path / "bin" / "adb")),
        codex_bin=str(_executable(tmp_path / "bin" / "codex")),
    )
    recipe = RuntimeBuildRecipe(
        args=("./gradlew", "assembleDebug"),
        timeout_seconds=120,
        apk_glob=spec.apk_glob,
    )
    return _SealedCase(
        repository=repository,
        materializer=materializer,
        admission=admission,
        receipt=receipt,
        packet=packet,
        worktree=worktree,
        spec=spec,
        options=options,
        recipe=recipe,
    )


def test_sealed_injection_is_admitted_before_build_and_prepared(
    tmp_path: Path,
) -> None:
    case = _sealed_case(tmp_path)
    build = _SuccessfulBuild(b"fixed test apk")

    try:
        prepared = prepare_runtime_case(
            source_authority=SealedInjectionSourceAuthority(
                case.admission,
                case.packet,
                case.repository / "catalog.json",
            ),
            build_recipe=case.recipe,
            spec=case.spec,
            options=case.options,
            build_runner=build,
            apk_inspector=_StaticApkInspector(),
        )

        assert prepared.prepared is True
        assert prepared.rejection_code is None
        assert build.calls == [
            (["./gradlew", "assembleDebug"], case.worktree, 120),
        ]
        before = prepared.receipt["source"]["before"]
        after = prepared.receipt["source"]["after"]
        assert before["worktree"]["source_tree_sha256"] == after["worktree"][
            "source_tree_sha256"
        ]
        assert before["worktree"]["complete_tree_sha256"] != after["worktree"][
            "complete_tree_sha256"
        ]
        assert prepared.receipt["apk"] == {
            "bytes": len(b"fixed test apk"),
            "launcher_activity": "org.example.injected.MainActivity",
            "package": "org.example.injected",
            "path": "build/outputs/apk/debug/app-debug.apk",
            "sha256": sha256(b"fixed test apk").hexdigest(),
        }
        assert prepared.receipt_sha256 == sha256(prepared.receipt_bytes).hexdigest()
        assert prepared.receipt["production_admission"]["side_effects"]["build"] is False
        assert prepared.receipt["build"]["apk_glob"] == case.spec.apk_glob
        assert prepared.receipt["build"]["executable"]["path"] == str(
            (case.worktree / "gradlew").resolve()
        )
    finally:
        case.cleanup()


def test_clean_checkout_is_prepared_through_the_same_public_interface(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    build = _SuccessfulBuild(b"clean apk")

    prepared = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert prepared.prepared is True
    assert prepared.receipt["source"]["before"]["worktree"]["clean"] is True
    verify_runtime_preparation_receipt(
        prepared.receipt,
        spec=case.spec,
        options=case.options,
        source_authority=CleanCheckoutSourceAuthority(),
        apk_inspector=_StaticApkInspector(),
    )


def test_clean_authority_rejects_an_ordinary_dirty_checkout_before_build(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    (case.repository / "source.txt").write_text("dirty\n", encoding="utf-8")
    build = _SuccessfulBuild(b"must not be written")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "source_admission_rejected"
    assert build.calls == []


def test_source_authority_cannot_admit_an_empty_host_identity(tmp_path: Path) -> None:
    case = _clean_case(tmp_path)

    result = admit_production_seam(
        case.spec,
        case.options,
        source_authority=_EmptyHostSourceAuthority(),
    )

    assert result.admitted is False
    assert result.receipt["checks"]["host_identity"]["status"] == "failed"
    assert result.receipt["host"] == {}


def test_legacy_clean_admission_receipt_remains_compatible_only_when_pristine(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    current = admit_production_seam(case.spec, case.options)
    legacy = copy.deepcopy(current.receipt)
    legacy_worktree = legacy["host"]["worktree"]
    legacy_worktree.pop("source_tree_sha256")
    legacy_worktree.pop("complete_tree_sha256")
    legacy_worktree.pop("declared_injection")

    verified = verify_admitted_receipt(legacy, case.spec, case.options)

    assert verified.admitted is True
    ignored = case.repository / "build" / "stale-input.txt"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("not legacy-compatible\n", encoding="utf-8")
    with pytest.raises(
        ProductionSeamAdmissionError,
        match="admission receipt source/worktree drift",
    ):
        verify_admitted_receipt(legacy, case.spec, case.options)


def test_preexisting_ignored_sealed_source_is_rejected_before_build(
    tmp_path: Path,
) -> None:
    case = _sealed_case(tmp_path)
    ignored = case.worktree / "build" / "generated" / "stale-source.txt"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("can influence build\n", encoding="utf-8")
    build = _SuccessfulBuild(b"must not be written")

    try:
        rejected = prepare_runtime_case(
            source_authority=SealedInjectionSourceAuthority(
                case.admission,
                case.packet,
                case.repository / "catalog.json",
            ),
            build_recipe=case.recipe,
            spec=case.spec,
            options=case.options,
            build_runner=build,
            apk_inspector=_StaticApkInspector(),
        )

        assert rejected.rejection_code == "source_worktree_not_pristine"
        assert build.calls == []
    finally:
        case.cleanup()


def test_build_recipe_cannot_hide_a_shell_behind_env(tmp_path: Path) -> None:
    case = _clean_case(tmp_path)
    build = _SuccessfulBuild(b"must not be written")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("env", "bash", "-c", "./gradlew assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "prohibited_build_command"
    assert build.calls == []


def test_post_build_source_drift_is_rejected_before_apk_handoff(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    build = _SourceDriftingBuild(b"untrusted apk")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "post_build_source_drift"
    assert len(build.calls) == 1


def test_prepared_receipt_reverification_rejects_apk_byte_drift(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    authority = CleanCheckoutSourceAuthority()
    prepared = prepare_runtime_case(
        source_authority=authority,
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"trusted apk"),
        apk_inspector=_StaticApkInspector(),
    )
    apk_path = (
        case.repository
        / "build"
        / "outputs"
        / "apk"
        / "debug"
        / "app-debug.apk"
    )
    apk_path.write_bytes(b"drifted apk")

    try:
        verify_runtime_preparation_receipt(
            prepared,
            spec=case.spec,
            options=case.options,
            source_authority=authority,
            apk_inspector=_StaticApkInspector(),
        )
    except RuntimePreparationVerificationError as error:
        assert str(error) == "runtime preparation APK bytes drifted"
    else:
        raise AssertionError("APK drift was accepted")


def test_prepared_receipt_reverification_rejects_ignored_worktree_drift(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    authority = CleanCheckoutSourceAuthority()
    prepared = prepare_runtime_case(
        source_authority=authority,
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"trusted apk"),
        apk_inspector=_StaticApkInspector(),
    )
    ignored = case.repository / "build" / "generated" / "late-source.txt"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("late ignored input\n", encoding="utf-8")

    with pytest.raises(
        RuntimePreparationVerificationError,
        match="runtime preparation source or runner policy drifted",
    ):
        verify_runtime_preparation_receipt(
            prepared,
            spec=case.spec,
            options=case.options,
            source_authority=authority,
            apk_inspector=_StaticApkInspector(),
        )


def test_duplicate_apk_locator_matches_fail_closed_even_for_one_inode(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_DuplicateAliasBuild(b"same inode apk"),
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "apk_ambiguous"


def test_runner_reverifies_prepared_apk_before_establishing_execution_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _clean_case(tmp_path)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            (str(Path(case.options.codex_bin).parent), os.environ.get("PATH", ""))
        ),
    )
    spec = replace(
        case.spec,
        live_validation=replace(
            case.spec.live_validation,
            android_bin=case.options.android_bin,
            adb_bin=case.options.adb_bin,
        ),
    )
    options = replace(case.options, codex_bin="codex")
    authority = CleanCheckoutSourceAuthority()
    prepared = prepare_runtime_case(
        source_authority=authority,
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=spec.apk_glob,
        ),
        spec=spec,
        options=options,
        build_runner=_SuccessfulBuild(b"runner handoff apk"),
        apk_inspector=_StaticApkInspector(),
    )
    apk_path = (
        case.repository
        / "build"
        / "outputs"
        / "apk"
        / "debug"
        / "app-debug.apk"
    )
    apk_path.write_bytes(b"runner handoff drift")

    def fail_if_established(*args: object, **kwargs: object) -> None:
        raise AssertionError("ExecutionRecord was established before handoff verification")

    monkeypatch.setattr(cli.ExecutionRecordStore, "establish", fail_if_established)
    with pytest.raises(
        RuntimePreparationVerificationError,
        match="runtime preparation APK bytes drifted",
    ):
        cli.run(
            spec,
            device=options.device,
            artifact_dir=options.artifact_dir,
            workdir=options.workdir,
            admission_options=options,
            runtime_preparation_handoff=RuntimePreparationHandoff(
                receipt=prepared,
                source_authority=authority,
                apk_inspector=_StaticApkInspector(),
            ),
        )


def test_runner_rejects_contradictory_admission_and_preparation_handoffs(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    authority = CleanCheckoutSourceAuthority()
    prepared = prepare_runtime_case(
        source_authority=authority,
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"runner handoff apk"),
        apk_inspector=_StaticApkInspector(),
    )

    with pytest.raises(
        ProductionSeamAdmissionError,
        match="admission and runtime preparation handoffs are mutually exclusive",
    ):
        cli.run(
            case.spec,
            device=case.options.device,
            artifact_dir=case.options.artifact_dir,
            workdir=case.options.workdir,
            admission_receipt=prepared.receipt["production_admission"],
            admission_options=case.options,
            runtime_preparation_handoff=RuntimePreparationHandoff(
                receipt=prepared,
                source_authority=authority,
                apk_inspector=_StaticApkInspector(),
            ),
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "worktree_path",
        "packet_id",
        "origin",
        "baseline_commit",
        "result_tree",
        "result_diff",
        "receipt_identity",
        "tracked_source",
        "packet_material",
        "ownership_marker",
    ),
)
def test_sealed_authority_rejects_every_cross_bound_source_drift_before_build(
    tmp_path: Path,
    mutation: str,
) -> None:
    case = _sealed_case(tmp_path)
    packet = case.packet
    restore: tuple[Path, bytes] | None = None
    if mutation == "worktree_path":
        packet = replace(packet, worktree_path=str(case.repository.resolve()))
    elif mutation == "packet_id":
        packet = replace(packet, packet_id="change-target-000000000000000000000000")
    elif mutation == "origin":
        _git(case.worktree, "remote", "set-url", "origin", "https://example.invalid/drift.git")
    elif mutation == "baseline_commit":
        packet = replace(packet, source_commit="0" * 40)
    elif mutation == "result_tree":
        packet = replace(packet, materialized_source_tree_sha256="0" * 64)
    elif mutation == "result_diff":
        packet = replace(packet, result_diff_sha256="0" * 64)
    elif mutation == "receipt_identity":
        packet = replace(packet, receipt_identity_sha256="0" * 64)
    elif mutation == "tracked_source":
        source = case.worktree / "source.txt"
        restore = (source, source.read_bytes())
        source.write_text("drifted source\n", encoding="utf-8")
    elif mutation == "packet_material":
        patch_path = Path(packet.patch_path)
        restore = (patch_path, patch_path.read_bytes())
        patch_path.write_text("drifted packet\n", encoding="utf-8")
    elif mutation == "ownership_marker":
        marker = case.worktree / ".aiverify-injection-ownership.json"
        restore = (marker, marker.read_bytes())
        marker.write_text("{}\n", encoding="utf-8")
    build = _SuccessfulBuild(b"must not be written")

    try:
        rejected = prepare_runtime_case(
            source_authority=SealedInjectionSourceAuthority(
                case.admission,
                packet,
                case.repository / "catalog.json",
            ),
            build_recipe=case.recipe,
            spec=case.spec,
            options=case.options,
            build_runner=build,
            apk_inspector=_StaticApkInspector(),
        )

        assert rejected.rejection_code == "source_admission_rejected"
        assert build.calls == []
    finally:
        if mutation == "origin":
            _git(
                case.worktree,
                "remote",
                "set-url",
                "origin",
                "https://example.invalid/app.git",
            )
        if restore is not None:
            restore[0].write_bytes(restore[1])
        case.cleanup()


def test_build_result_must_confirm_the_exact_requested_argument_vector(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_ContradictoryBuild(b"unbound apk"),
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "build_command_mismatch"


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    (
        ("build_failed", "build_failed"),
        ("build_timeout", "build_timeout"),
        ("apk_missing", "apk_missing"),
        ("apk_outside_host", "apk_outside_host"),
        ("apk_package_mismatch", "apk_package_mismatch"),
        ("apk_activity_mismatch", "apk_activity_mismatch"),
        ("apk_inspection_failed", "apk_inspection_failed"),
    ),
)
def test_expected_build_and_apk_failures_return_stable_rejections(
    tmp_path: Path,
    failure: str,
    expected_code: str,
) -> None:
    case = _clean_case(tmp_path)
    build: CommandRunner
    inspector: ApkInspector = _StaticApkInspector()
    if failure == "build_failed":
        build = _NoApkBuild(9)
    elif failure == "build_timeout":
        build = _NoApkBuild(124)
    elif failure == "apk_missing":
        build = _NoApkBuild(0)
    elif failure == "apk_outside_host":
        build = _OutsideApkBuild(b"outside apk")
    else:
        build = _SuccessfulBuild(b"manifest test apk")
        if failure == "apk_package_mismatch":
            inspector = _StaticApkInspector(package="org.example.other")
        elif failure == "apk_activity_mismatch":
            inspector = _StaticApkInspector(
                launcher_activity="org.example.injected.OtherActivity"
            )
        else:
            inspector = _FailingApkInspector()

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=inspector,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == expected_code
    assert rejected.receipt["status"] == "rejected"
    assert "build" not in rejected.receipt
    assert "apk" not in rejected.receipt


@pytest.mark.parametrize("authority_input", ("unsealed", "fabricated"))
def test_unsealed_or_fabricated_injection_authority_never_runs_build(
    tmp_path: Path,
    authority_input: str,
) -> None:
    case = _sealed_case(tmp_path)
    admission: object = case.admission
    if authority_input == "unsealed":
        admission = admit_catalogued_candidate(
            case.repository / "catalog.json",
            "missing-source",
            case.materializer,
        )
    else:
        admission = {"status": "sealed", "identity_sha256": "0" * 64}
    build = _SuccessfulBuild(b"must not be written")

    try:
        rejected = prepare_runtime_case(
            source_authority=SealedInjectionSourceAuthority(
                admission,  # type: ignore[arg-type]
                case.packet,
                case.repository / "catalog.json",
            ),
            build_recipe=case.recipe,
            spec=case.spec,
            options=case.options,
            build_runner=build,
            apk_inspector=_StaticApkInspector(),
        )

        assert rejected.rejection_code == "source_admission_rejected"
        assert build.calls == []
    finally:
        case.cleanup()


def test_self_consistent_replacement_packet_is_not_bound_to_sealed_admission(
    tmp_path: Path,
) -> None:
    case = _sealed_case(tmp_path)
    replacement_path = case.repository / "patches" / "replacement.patch"
    replacement_text = case.packet.patch_text + "\n"
    replacement_path.write_text(replacement_text, encoding="utf-8")
    replacement = replace(
        case.packet,
        patch_path=str(replacement_path.resolve()),
        patch_text=replacement_text,
        patch_sha256=sha256(replacement_text.encode("utf-8")).hexdigest(),
    )
    replacement = replace(replacement, packet_id=replacement.canonical_packet_id)
    build = _SuccessfulBuild(b"must not be written")

    try:
        rejected = prepare_runtime_case(
            source_authority=SealedInjectionSourceAuthority(
                case.admission,
                replacement,
                case.repository / "catalog.json",
            ),
            build_recipe=case.recipe,
            spec=case.spec,
            options=case.options,
            build_runner=build,
            apk_inspector=_StaticApkInspector(),
        )

        assert rejected.rejection_code == "source_admission_rejected"
        assert build.calls == []
    finally:
        case.cleanup()


@pytest.mark.parametrize(
    ("drift", "message"),
    (
        ("receipt", "runtime preparation receipt identity drifted"),
        ("run_spec", "runtime preparation Run Spec drifted"),
        ("runner_options", "runtime preparation source or runner policy drifted"),
        ("source", "runtime preparation source or runner policy drifted"),
        ("manifest", "runtime preparation APK manifest drifted"),
    ),
)
def test_handoff_reverification_fails_closed_on_every_identity_drift(
    tmp_path: Path,
    drift: str,
    message: str,
) -> None:
    case = _clean_case(tmp_path)
    authority = CleanCheckoutSourceAuthority()
    prepared = prepare_runtime_case(
        source_authority=authority,
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"handoff apk"),
        apk_inspector=_StaticApkInspector(),
    )
    options = case.options
    inspector: ApkInspector = _StaticApkInspector()
    receipt_to_verify: object = prepared
    if drift == "receipt":
        tampered = copy.deepcopy(prepared.receipt)
        tampered["build"]["duration_seconds"] = 999  # type: ignore[index]
        receipt_to_verify = tampered
    elif drift == "run_spec":
        assert case.spec.source_path is not None
        case.spec.source_path.write_bytes(case.spec.source_path.read_bytes() + b"\n")
    elif drift == "runner_options":
        options = replace(case.options, requested_driver_model="drifted-model")
    elif drift == "source":
        (case.repository / "source.txt").write_text("drifted\n", encoding="utf-8")
    else:
        inspector = _StaticApkInspector(package="org.example.drifted")

    with pytest.raises(RuntimePreparationVerificationError, match=message):
        verify_runtime_preparation_receipt(
            receipt_to_verify,  # type: ignore[arg-type]
            spec=case.spec,
            options=options,
            source_authority=authority,
            apk_inspector=inspector,
        )


def test_handoff_reverification_rejects_a_new_duplicate_apk(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    authority = CleanCheckoutSourceAuthority()
    prepared = prepare_runtime_case(
        source_authority=authority,
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"prepared apk"),
        apk_inspector=_StaticApkInspector(),
    )
    duplicate = (
        case.repository
        / "build"
        / "outputs"
        / "apk"
        / "release"
        / "app-release.apk"
    )
    duplicate.parent.mkdir(parents=True)
    duplicate.write_bytes(b"second apk")

    with pytest.raises(
        RuntimePreparationVerificationError,
        match="runtime preparation APK set drifted",
    ):
        verify_runtime_preparation_receipt(
            prepared,
            spec=case.spec,
            options=case.options,
            source_authority=authority,
            apk_inspector=_StaticApkInspector(),
        )


def test_final_source_check_runs_after_apk_inspection(tmp_path: Path) -> None:
    case = _clean_case(tmp_path)

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"untrusted after inspection"),
        apk_inspector=_SourceDriftingApkInspector(case.repository / "source.txt"),
    )

    assert rejected.rejection_code == "post_build_source_drift"


def test_apk_bytes_cannot_drift_during_manifest_inspection(tmp_path: Path) -> None:
    case = _clean_case(tmp_path)

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"inspected apk"),
        apk_inspector=_ApkDriftingInspector(),
    )

    assert rejected.rejection_code == "apk_drift_during_inspection"


def test_apk_bytes_cannot_drift_during_final_source_authority_check(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    apk_path = (
        case.repository
        / "build"
        / "outputs"
        / "apk"
        / "debug"
        / "app-debug.apk"
    )

    rejected = prepare_runtime_case(
        source_authority=_ApkDriftingSourceAuthority(apk_path),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"authority-inspected apk"),
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "apk_drift_during_inspection"


def test_missing_build_executable_is_rejected_after_admission(tmp_path: Path) -> None:
    case = _clean_case(tmp_path)
    build = _SuccessfulBuild(b"must not be written")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./missing/gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "build_executable_unavailable"
    assert build.calls == []


def test_invalid_apk_inspector_is_a_stable_rejection_before_build(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    build = _SuccessfulBuild(b"must not be written")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=object(),  # type: ignore[arg-type]
    )

    assert rejected.rejection_code == "apk_inspector_unavailable"
    assert build.calls == []


@pytest.mark.parametrize(
    "args",
    (
        ("adb", "install", "app.apk"),
        ("android", "run"),
        ("codex", "exec"),
        ("emulator", "@device"),
        ("env", "sh", "-c", "./gradlew assembleDebug"),
        ("./gradlew", "installDebug"),
        ("./gradlew", "connectedAndroidTest"),
        ("./gradlew", ":app:installDebug"),
        ("./gradlew", ":app:connectedAndroidTest"),
        ("./gradlew", ":app:instDeb"),
    ),
)
def test_build_recipe_rejects_shell_device_deployment_and_agent_commands(
    tmp_path: Path,
    args: tuple[str, ...],
) -> None:
    case = _clean_case(tmp_path)
    build = _SuccessfulBuild(b"must not be written")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=args,
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert rejected.rejection_code == "prohibited_build_command"
    assert build.calls == []


def test_build_recipe_allows_only_explicit_assemble_tasks_and_safe_flags(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    build = _SuccessfulBuild(b"qualified assemble apk")

    prepared = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", ":app:assembleDebug", "--no-daemon"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert prepared.prepared is True
    assert build.calls == [
        (["./gradlew", ":app:assembleDebug", "--no-daemon"], case.host, 120),
    ]


def test_admission_runner_observes_only_read_only_git_before_build(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    admission_runner = _ReadOnlyGitRunner()
    build = _AdmissionOrderedBuild(b"ordered apk", admission_runner)

    prepared = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        admission_command_runner=admission_runner,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert prepared.prepared is True
    assert len(admission_runner.calls) == 8
    assert len(build.calls) == 1


def test_production_apk_inspector_uses_a_shell_free_local_aapt_vector(
    tmp_path: Path,
) -> None:
    apk_path = tmp_path / "app.apk"
    apk_path.write_bytes(b"apk")

    class AaptRunner(CommandRunner):
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], Path | None]] = []

        def run(
            self,
            args: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int | None = None,
            input_text: str | None = None,
        ) -> CommandResult:
            self.calls.append((list(args), cwd))
            return CommandResult(
                args=list(args),
                stdout=(
                    "package: name='org.example.injected' versionCode='1'\n"
                    "launchable-activity: name='.MainActivity' label='' icon=''\n"
                ),
                stderr="",
                returncode=0,
            )

    runner = AaptRunner()

    metadata = AaptApkInspector(
        "/sdk/aapt2",
        command_runner=runner,
    ).inspect(apk_path)

    assert metadata == ApkMetadata(
        package="org.example.injected",
        launcher_activity="org.example.injected.MainActivity",
    )
    assert runner.calls == [
        (["/sdk/aapt2", "dump", "badging", str(apk_path.resolve())], tmp_path),
    ]


def test_preparation_outcome_does_not_expose_mutable_receipt_state(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path)
    prepared = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=_SuccessfulBuild(b"immutable receipt apk"),
        apk_inspector=_StaticApkInspector(),
    )

    exposed = prepared.receipt
    exposed["status"] = "tampered"

    assert prepared.receipt["status"] == "prepared"


def test_clean_host_subdirectory_is_the_exact_build_working_directory(
    tmp_path: Path,
) -> None:
    case = _clean_case(tmp_path, host_subdir=True)
    build = _SuccessfulBuild(b"subdirectory apk")

    prepared = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=RuntimeBuildRecipe(
            args=("./gradlew", "assembleDebug"),
            timeout_seconds=120,
            apk_glob=case.spec.apk_glob,
        ),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StaticApkInspector(),
    )

    assert prepared.prepared is True
    assert build.calls == [
        (["./gradlew", "assembleDebug"], case.host, 120),
    ]
    assert prepared.receipt["build"]["cwd"] == str(case.host)
