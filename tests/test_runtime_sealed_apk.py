"""Public-contract tests for the mapped-lane sealed Runtime APK handoff."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from aiverify.bench import opencalc_discovery as discovery
from aiverify.bench import runtime_mapping
from aiverify.runner import cli
from aiverify.runner.admission import (
    CleanCheckoutSourceAuthority,
    HostAuthority,
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    SourceAuthority,
    SourceAuthorityBinding,
)
from aiverify.runner.command import (
    CommandResult,
    CommandRunner,
    SubprocessCommandRunner,
)
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    AaptApkInspector,
    ApkInspector,
    ApkMetadata,
    MappedRuntimeSourceAuthority,
    RuntimeBuildEnvironment,
    RuntimeBuildRecipe,
    RuntimeInputVault,
    RuntimeInputVaultManifest,
    RuntimePreparationHandoff,
    RuntimeSigningIdentity,
    RuntimeToolIdentity,
    prepare_runtime_case,
    runtime_preparation_uses_test_substitutes,
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


@dataclass(frozen=True)
class _StrictCase:
    repository: Path
    spec: RunSpec
    options: PlannedRunnerOptions
    vault: RuntimeInputVault
    signer: RuntimeSigningIdentity
    metadata: ApkMetadata
    sealed_path: Path


class _StrictBuild(CommandRunner):
    def __init__(self, apk_bytes: bytes) -> None:
        self.apk_bytes = apk_bytes
        self.calls: list[tuple[list[str], Path | None, int | None]] = []
        self.environment: dict[str, str] | None = None

    def bind_environment(self, environment: dict[str, str]) -> None:
        self.environment = dict(environment)

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
        apk = cwd / "app" / "build" / "outputs" / "apk" / "debug" / "app-debug.apk"
        apk.parent.mkdir(parents=True, exist_ok=True)
        apk.write_bytes(self.apk_bytes)
        return CommandResult(
            args=list(args), stdout="offline build\n", stderr="", returncode=0
        )


class _StrictInspector(ApkInspector):
    def __init__(self, metadata: ApkMetadata) -> None:
        self.metadata = metadata
        self.paths: list[Path] = []

    def inspect(self, apk_path: Path) -> ApkMetadata:
        self.paths.append(apk_path)
        return self.metadata


class _ExtraApkBuild(_StrictBuild):
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
        (cwd / "build").mkdir(parents=True, exist_ok=True)
        (cwd / "build" / "other.apk").write_bytes(self.apk_bytes)
        return result


class _TimedOutBuild(CommandRunner):
    def __init__(self) -> None:
        self.calls = 0

    def bind_environment(self, environment: dict[str, str]) -> None:
        del environment

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls += 1
        raise subprocess.TimeoutExpired(args, timeout_seconds or 0)


class _MappedDelegate(SourceAuthority):
    def __init__(self, host: HostAuthority) -> None:
        self.host = host
        self.verified_request_ids: list[str] = []

    @property
    def materialized_source_tree_sha256(self) -> str:
        return self.host.worktree.source_tree_sha256

    @property
    def declares_injection(self) -> bool:
        return True

    def verify_runtime_source_request(
        self,
        request: runtime_mapping.RuntimeSourceRequest,
    ) -> None:
        self.verified_request_ids.append(request.request_id)

    def resolve_host(
        self,
        spec: RunSpec,
        options: PlannedRunnerOptions,
        runner: CommandRunner,
    ) -> HostAuthority:
        return self.host


def _mapped_source_request(
    lane_id: str,
    *,
    host: HostAuthority,
) -> runtime_mapping.RuntimeSourceRequest:
    is_change = lane_id in {"ocrc-v1-lane-01", "ocrc-v1-lane-02"}
    target_kind = "ChangeTarget" if is_change else "ProjectTarget"
    variant = (
        "control" if lane_id in {"ocrc-v1-lane-01", "ocrc-v1-lane-03"} else "defect"
    )
    return runtime_mapping.RuntimeSourceRequest(
        request_id=f"test-release:{lane_id}:source-request",
        candidate_identity_sha256="0" * 64,
        candidate_manifest_sha256="1" * 64,
        candidate_artifact_inventory_sha256="2" * 64,
        lane_id=lane_id,
        target_kind=target_kind,
        variant=variant,
        catalog_id=f"catalog-{lane_id}",
        package_id=f"package-{lane_id}",
        target_id=f"target-{lane_id}",
        source_id=f"source-{lane_id}",
        source_origin=host.origin,
        baseline_commit=host.commit if is_change else "3" * 40,
        baseline_tree_sha256="4" * 64,
        baseline_archive_sha256="5" * 64,
        source_commit=host.commit,
        source_tree_sha256=host.worktree.source_tree_sha256,
        materialized_tree_sha256="6" * 40,
        worktree_path=host.host_project,
        target_path="source.txt",
        target_file_sha256="7" * 64,
        anchor_identity_sha256="8" * 64,
        context_acquisition_identity_sha256="9" * 64,
        discovery_materialization_identity_sha256="a" * 64,
        campaign_identity_sha256="b" * 64,
        patch_ref="patches/test.patch",
        patch_sha256="c" * 64,
        patch_format="unified_diff",
        materialization_kind=(
            "change_target_pristine_source"
            if is_change
            else "project_target_synthetic_commit"
        ),
        materialization_receipt_identity_sha256=None if is_change else "d" * 64,
        result_diff_sha256=None if is_change else "e" * 64,
        scope=None if is_change else discovery.REQUIRED_CONTEXT_PATHS,
        discovery_budget=None if is_change else discovery.REQUIRED_CONTEXT_BUDGET,
        source_package_identity_sha256="f" * 64,
        discovery_result_identity_sha256="0" * 64,
        leakage_audit_identity_sha256="1" * 64,
    )


def _strict_recipe(case: _StrictCase) -> RuntimeBuildRecipe:
    (case.repository / "java").mkdir()
    (case.repository / "android-sdk").mkdir()
    (case.repository / "tool-bin").mkdir()
    (case.repository / "gradlew").chmod(0o555)
    return RuntimeBuildRecipe(
        args=(
            "./gradlew",
            "--offline",
            "--no-daemon",
            "--no-build-cache",
            "--no-configuration-cache",
            "--max-workers=1",
            "--console=plain",
            "clean",
            ":app:assembleDebug",
        ),
        timeout_seconds=900,
        apk_glob=case.spec.apk_glob,
        output_relative_path=case.spec.apk_glob,
        environment_policy={
            "mode": "private_allowlist",
            "dependency_resolution": "offline",
            "network_claim": "none",
            "retry": False,
        },
        environment=RuntimeBuildEnvironment(
            variables=(
                ("ANDROID_SDK_ROOT", str(case.repository / "android-sdk")),
                ("JAVA_HOME", str(case.repository / "java")),
                ("LANG", "C.UTF-8"),
                ("LC_ALL", "C.UTF-8"),
                ("PATH", str(case.repository / "tool-bin")),
                ("SOURCE_DATE_EPOCH", "1783693058"),
                ("TZ", "UTC"),
            )
        ),
        tool_identities=(
            RuntimeToolIdentity.from_path(
                "gradle-wrapper",
                case.repository / "gradlew",
            ),
        ),
    )


def _strict_case(tmp_path: Path) -> _StrictCase:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.name", "Runtime Sealed APK Test")
    _git(repository, "config", "user.email", "runtime@example.invalid")
    _git(repository, "remote", "add", "origin", "https://example.invalid/opencalc.git")
    (repository / ".gitignore").write_text(
        "/build/\n/app/build/\n",
        encoding="utf-8",
    )
    (repository / "gradlew").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (repository / "gradlew").chmod(0o755)
    (repository / "source.txt").write_text("clean\n", encoding="utf-8")
    _git(repository, "add", ".gitignore", "gradlew", "source.txt")
    _git(repository, "commit", "-m", "clean baseline")
    commit = _git(repository, "rev-parse", "HEAD")

    run_spec_path = tmp_path / "run-spec.yaml"
    run_spec_path.write_text(
        "host_project:\n"
        "  root: ${PROJECT_SOURCE}\n"
        "  origin: https://example.invalid/opencalc.git\n"
        f"  commit: {commit}\n"
        "apk_glob: build/app-debug.apk\n"
        "package: com.example.runtime.debug\n"
        "activity: com.example.runtime.MainActivity\n"
        "scenario:\n"
        "  id: sealed-runtime-apk\n",
        encoding="utf-8",
    )
    spec = load_run_spec(run_spec_path, environ={"PROJECT_SOURCE": str(repository)})
    options = PlannedRunnerOptions(
        device="unused-device",
        workdir=repository,
        artifact_dir=tmp_path / "lane" / "artifacts",
        android_bin=str(_executable(tmp_path / "bin" / "android")),
        adb_bin=str(_executable(tmp_path / "bin" / "adb")),
        codex_bin=str(_executable(tmp_path / "bin" / "codex")),
    )

    vault_root = tmp_path / "runtime-input-vault"
    keystore = vault_root / "signing" / "non-production.keystore"
    certificate = vault_root / "signing" / "non-production-cert.pem"
    dependency = vault_root / "caches" / "modules-2" / "metadata.bin"
    keystore.parent.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    keystore.write_bytes(b"private key bytes stay outside Git")
    certificate.write_bytes(b"certificate public material")
    dependency.write_bytes(b"offline dependency bundle")
    keystore.chmod(0o444)
    certificate.chmod(0o444)
    dependency.chmod(0o444)
    signer = RuntimeSigningIdentity(
        alias="runtime-non-production",
        keystore_path=Path("signing/non-production.keystore"),
        keystore_sha256=hashlib.sha256(keystore.read_bytes()).hexdigest(),
        certificate_path=Path("signing/non-production-cert.pem"),
        certificate_sha256=hashlib.sha256(certificate.read_bytes()).hexdigest(),
    )
    manifest = RuntimeInputVaultManifest.from_directory(
        vault_root,
        family_id="runtime-test-family",
        family_version="v1",
        signing_identity=signer,
        retention_reason="offline build dependency and non-production signing input",
    )
    manifest_path = tmp_path / "runtime-input-vault-manifest.json"
    manifest.write(manifest_path)
    vault = RuntimeInputVault.from_manifest(manifest_path, root=vault_root)

    metadata = ApkMetadata(
        package=spec.package,
        launcher_activity=spec.activity or "",
        version_code=54,
        version_name="3.2.1",
        min_sdk=21,
        target_sdk=35,
        compile_sdk=35,
        debuggable=True,
        signer_sha256=signer.certificate_sha256,
        signer_count=1,
        v1_verified=True,
        v2_verified=True,
    )
    return _StrictCase(
        repository=repository,
        spec=spec,
        options=options,
        vault=vault,
        signer=signer,
        metadata=metadata,
        sealed_path=options.artifact_dir / "build" / "app-debug.apk",
    )


def _mapped_authority(case: _StrictCase) -> MappedRuntimeSourceAuthority:
    clean_host = CleanCheckoutSourceAuthority().resolve_host(
        case.spec,
        case.options,
        SubprocessCommandRunner(),
    )
    mapping = runtime_mapping.SourceAuthorityMapping(
        release_id=runtime_mapping.RUNTIME_MAPPING_RELEASE_ID,
        release_identity_sha256="f" * 64,
        source_requests=tuple(
            _mapped_source_request(lane_id, host=clean_host)
            for lane_id in runtime_mapping.RUNTIME_LANE_IDS
        ),
    )
    mapped_host = replace(
        clean_host,
        worktree=replace(clean_host.worktree, declared_injection=True),
        source_authority=SourceAuthorityBinding(
            kind="mapped_runtime_test",
            claims=(("candidate_identity_sha256", "0" * 64),),
        ),
    )
    return MappedRuntimeSourceAuthority(
        mapping,
        _MappedDelegate(mapped_host),
        "ocrc-v1-lane-01",
    )


def test_strict_preparation_verifies_vault_build_and_seals_one_apk(
    tmp_path: Path,
) -> None:
    case = _strict_case(tmp_path)
    apk_bytes = b"signed APK substitute"
    build = _StrictBuild(apk_bytes)
    inspector = _StrictInspector(case.metadata)
    recipe = _strict_recipe(case)
    source_authority = _mapped_authority(case)

    prepared = prepare_runtime_case(
        source_authority=source_authority,
        build_recipe=recipe,
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=inspector,
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert prepared.prepared is True
    assert build.calls == [(list(recipe.args), case.repository, 900)]
    assert case.sealed_path.read_bytes() == apk_bytes
    assert not case.sealed_path.is_symlink()
    assert case.sealed_path.stat().st_nlink == 1
    assert case.sealed_path.stat().st_mode & 0o222 == 0
    assert build.environment is not None
    private_root = Path(
        prepared.receipt["build"]["private_input_root"]  # type: ignore[index]
    )
    assert not private_root.is_relative_to(case.options.artifact_dir)
    assert Path(build.environment["HOME"]) == private_root / "homes" / "home"
    assert Path(build.environment["GRADLE_USER_HOME"]) == (
        private_root / "homes" / "gradle-user-home"
    )
    private_signing_keystore = (
        private_root / "homes" / "home" / ".android" / "debug.keystore"
    )
    assert (
        private_signing_keystore.read_bytes()
        == (case.vault.root / "signing" / "non-production.keystore").read_bytes()
    )
    assert private_signing_keystore.stat().st_nlink == 1
    assert private_signing_keystore.stat().st_mode & 0o222 == 0
    private_dependency = (
        private_root
        / "homes"
        / "gradle-user-home"
        / "caches"
        / "modules-2"
        / "metadata.bin"
    )
    assert private_dependency.read_bytes() == b"offline dependency bundle"
    assert private_dependency.stat().st_nlink == 1
    assert private_dependency.stat().st_mode & 0o222 == 0
    assert prepared.receipt["build"]["retry"] is False  # type: ignore[index]
    assert prepared.receipt["sealed_apk"]["path"] == str(case.sealed_path.resolve())  # type: ignore[index]
    assert (
        prepared.receipt["sealed_apk"]["sha256"]
        == hashlib.sha256(apk_bytes).hexdigest()
    )  # type: ignore[index]
    assert prepared.receipt["source"]["mapping_binding"]["lane_id"] == (  # type: ignore[index]
        "ocrc-v1-lane-01"
    )
    assert prepared.receipt["runtime_effects"] == {  # type: ignore[index]
        "shell": False,
        "device": False,
        "android_deployment": False,
        "execution_record": False,
        "agent_or_model": False,
    }
    assert b"private key bytes stay outside Git" not in prepared.receipt_bytes
    assert b"password" not in prepared.receipt_bytes.lower()
    assert not (case.options.artifact_dir.parent / "execution-record.json").exists()

    verify_runtime_preparation_receipt(
        prepared,
        spec=case.spec,
        options=case.options,
        source_authority=source_authority,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
    )


def test_strict_preparation_rejects_vault_drift_before_build(tmp_path: Path) -> None:
    case = _strict_case(tmp_path)
    (case.vault.root / "unexpected.bin").write_bytes(b"not in the manifest")
    build = _StrictBuild(b"must not build")

    rejected = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "runtime_input_vault_rejected"
    assert build.calls == []


def test_strict_preparation_rejects_hard_linked_vault_input_before_build(
    tmp_path: Path,
) -> None:
    case = _strict_case(tmp_path)
    linked = tmp_path / "linked-keystore"
    os.link(case.vault.root / "signing" / "non-production.keystore", linked)
    build = _StrictBuild(b"must not build")

    rejected = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "runtime_input_vault_rejected"
    assert build.calls == []


def test_strict_preparation_rejects_ambient_apk_override_before_build(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case = _strict_case(tmp_path)
    monkeypatch.setenv("AIVERIFY_DEPLOYED_APK", str(tmp_path / "ambient.apk"))
    build = _StrictBuild(b"must not build")

    rejected = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "ambient_signing_fallback_forbidden"
    assert build.calls == []


def test_strict_preparation_requires_a_mapped_source_authority(
    tmp_path: Path,
) -> None:
    case = _strict_case(tmp_path)
    build = _StrictBuild(b"must not build")

    rejected = prepare_runtime_case(
        source_authority=CleanCheckoutSourceAuthority(),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "runtime_input_binding_unavailable"
    assert build.calls == []


def test_strict_preparation_rejects_extra_apk_outputs(tmp_path: Path) -> None:
    case = _strict_case(tmp_path)
    build = _ExtraApkBuild(b"one of two APKs")

    rejected = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "apk_extra_output"
    assert build.calls and len(build.calls) == 1


def test_strict_preparation_rejects_incomplete_apk_inspection(tmp_path: Path) -> None:
    case = _strict_case(tmp_path)
    build = _StrictBuild(b"unsigned metadata substitute")
    incomplete = ApkMetadata(
        package=case.metadata.package,
        launcher_activity=case.metadata.launcher_activity,
    )

    rejected = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(incomplete),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "apk_metadata_incomplete"
    assert not case.sealed_path.exists()


def test_strict_preparation_maps_runner_timeout_to_stable_rejection(
    tmp_path: Path,
) -> None:
    case = _strict_case(tmp_path)
    build = _TimedOutBuild()

    rejected = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=build,
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert rejected.prepared is False
    assert rejected.rejection_code == "build_timeout"
    assert build.calls == 1


def test_strict_receipt_rejects_sealed_apk_drift_before_runtime(tmp_path: Path) -> None:
    case = _strict_case(tmp_path)
    apk_bytes = b"signed APK substitute"
    prepared = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=_StrictBuild(apk_bytes),
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        sealed_apk_path=case.sealed_path,
        allow_test_substitutes=True,
    )
    assert prepared.prepared is True

    case.sealed_path.chmod(0o644)
    case.sealed_path.write_bytes(b"drifted sealed APK")
    case.sealed_path.chmod(0o444)

    try:
        verify_runtime_preparation_receipt(
            prepared,
            spec=case.spec,
            options=case.options,
            source_authority=_mapped_authority(case),
            apk_inspector=_StrictInspector(case.metadata),
            runtime_input_vault=case.vault,
            runtime_signing_identity=case.signer,
        )
    except ValueError as error:
        assert "sealed APK bytes drifted" in str(error)
    else:
        raise AssertionError("drifted sealed APK was accepted")


def test_runner_rejects_test_substitute_sealed_handoff_before_execution_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = _strict_case(tmp_path)
    spec = replace(
        case.spec,
        live_validation=replace(
            case.spec.live_validation,
            android_bin=case.options.android_bin,
            adb_bin=case.options.adb_bin,
        ),
    )
    options = replace(case.options, codex_bin="codex")
    prepared = prepare_runtime_case(
        source_authority=_mapped_authority(case),
        build_recipe=_strict_recipe(case),
        spec=case.spec,
        options=case.options,
        build_runner=_StrictBuild(b"test substitute APK"),
        apk_inspector=_StrictInspector(case.metadata),
        runtime_input_vault=case.vault,
        runtime_signing_identity=case.signer,
        allow_test_substitutes=True,
    )

    assert runtime_preparation_uses_test_substitutes(prepared) is True

    def fail_if_established(*args: object, **kwargs: object) -> None:
        raise AssertionError("ExecutionRecord was established for a test substitute")

    monkeypatch.setattr(cli.ExecutionRecordStore, "establish", fail_if_established)
    with pytest.raises(
        ProductionSeamAdmissionError,
        match="test-substitute Runtime APK handoffs cannot reach runtime",
    ):
        cli.run(
            spec,
            device=options.device,
            artifact_dir=options.artifact_dir,
            workdir=options.workdir,
            admission_options=options,
            runtime_preparation_handoff=RuntimePreparationHandoff(
                receipt=prepared,
                source_authority=_mapped_authority(case),
                apk_inspector=_StrictInspector(case.metadata),
            ),
        )


def test_mapped_source_authority_consumes_only_the_selected_released_lane(
    tmp_path: Path,
) -> None:
    case = _strict_case(tmp_path)
    clean_host = CleanCheckoutSourceAuthority().resolve_host(
        case.spec,
        case.options,
        SubprocessCommandRunner(),
    )
    mapped_host = replace(
        clean_host,
        worktree=replace(clean_host.worktree, declared_injection=True),
        source_authority=SourceAuthorityBinding(
            kind="mapped_runtime_test",
            claims=(("candidate_identity_sha256", "0" * 64),),
        ),
    )
    delegate = _MappedDelegate(mapped_host)
    requests = tuple(
        _mapped_source_request(lane_id, host=clean_host)
        for lane_id in runtime_mapping.RUNTIME_LANE_IDS
    )
    mapping = runtime_mapping.SourceAuthorityMapping(
        release_id=runtime_mapping.RUNTIME_MAPPING_RELEASE_ID,
        release_identity_sha256="f" * 64,
        source_requests=requests,
    )
    authority = MappedRuntimeSourceAuthority(
        mapping,
        delegate,
        "ocrc-v1-lane-01",
    )

    resolved = authority.resolve_host(
        case.spec, case.options, SubprocessCommandRunner()
    )

    assert resolved == mapped_host
    assert delegate.verified_request_ids == [requests[0].request_id]


def test_aapt_inspector_requires_the_exact_non_production_signature_vector(
    tmp_path: Path,
) -> None:
    apk_path = tmp_path / "app-debug.apk"
    apk_path.write_bytes(b"apk")
    signer_digest = "ab" * 32
    signer = RuntimeSigningIdentity(
        alias="runtime-non-production",
        keystore_path=Path("signing/non-production.keystore"),
        keystore_sha256="cd" * 32,
        certificate_path=Path("signing/non-production-cert.pem"),
        certificate_sha256=signer_digest,
    )

    class InspectorRunner(CommandRunner):
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
            if args[1:3] == ["dump", "badging"]:
                stdout = (
                    "package: name='com.example.runtime.debug' "
                    "versionCode='54' versionName='3.2.1'\n"
                    "minSdkVersion:'21'\n"
                    "targetSdkVersion:'35'\n"
                    "package: name='com.example.runtime.debug' versionCode='54' "
                    "versionName='3.2.1' compileSdkVersion='35' "
                    "compileSdkVersionCodename='VanillaIceCream'\n"
                    "application-debuggable\n"
                    "launchable-activity: name='com.example.runtime.MainActivity' "
                    "label='' icon=''\n"
                )
            else:
                grouped = ":".join(
                    signer_digest[index : index + 2].upper()
                    for index in range(0, len(signer_digest), 2)
                )
                stdout = (
                    "Signer #1 certificate DN: CN=runtime\n"
                    f"Signer #1 certificate SHA-256 digest: {grouped}\n"
                    "Verified using v1 scheme (JAR signing): true\n"
                    "Verified using v2 scheme (APK Signature Scheme v2): true\n"
                )
            return CommandResult(
                args=list(args), stdout=stdout, stderr="", returncode=0
            )

    runner = InspectorRunner()
    metadata = AaptApkInspector(
        "/sdk/aapt2",
        command_runner=runner,
        apksigner_executable="/sdk/apksigner",
        signing_identity=signer,
        require_signature=True,
    ).inspect(apk_path)

    assert metadata.version_code == 54
    assert metadata.min_sdk == 21
    assert metadata.target_sdk == 35
    assert metadata.compile_sdk == 35
    assert metadata.debuggable is True
    assert metadata.signer_sha256 == signer_digest
    assert metadata.signer_count == 1
    assert metadata.v1_verified is True
    assert metadata.v2_verified is True
    assert runner.calls == [
        ["/sdk/aapt2", "dump", "badging", str(apk_path.resolve())],
        [
            "/sdk/apksigner",
            "verify",
            "--verbose",
            "--print-certs",
            str(apk_path.resolve()),
        ],
    ]
