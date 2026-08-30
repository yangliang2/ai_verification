"""Recording-fake integration tests for Runtime Family Preparation."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.bench import runtime_calibration, runtime_mapping
from aiverify.bench.runtime_family_preparation import (
    RuntimeFamilyLaneInput,
    RuntimeFamilyLaneResult,
    RuntimeFamilyPreparationReceipt,
    prepare_runtime_family,
    stage_status,
    verify_runtime_family_preparation,
)
from aiverify.runner.admission import PlannedRunnerOptions, SourceAuthority
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    ApkInspector,
    ApkMetadata,
    RuntimeBuildRecipe,
    RuntimeInputVault,
    RuntimeInputVaultManifest,
    RuntimePreparationReceipt,
    RuntimeSigningIdentity,
    _canonical_bytes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = REPO_ROOT / "bench/runtime-calibration/opencalc-input-save-enabled-v1"
MAPPING_ROOT = (
    REPO_ROOT
    / "docs/runs/2026-08-29-issue-206-runtime-mapping-release/verification/family-stage-final"
)


class _RecordingAuthority(SourceAuthority):
    def __init__(self, binding: dict[str, object]) -> None:
        self.mapping_binding = binding

    def resolve_host(
        self, spec: RunSpec, options: PlannedRunnerOptions, runner: object
    ) -> object:
        raise AssertionError("recording family preparer must not resolve a host")


class _RecordingInspector(ApkInspector):
    def inspect(self, apk_path: Path) -> ApkMetadata:
        raise AssertionError("recording family preparer must not inspect an APK")


def _vault(
    tmp_path: Path, *, alias: str = "test-runtime"
) -> tuple[RuntimeInputVault, RuntimeSigningIdentity]:
    root = tmp_path / "vault"
    signing = root / "signing"
    dependency = root / "dependencies" / "metadata.bin"
    signing.mkdir(parents=True)
    dependency.parent.mkdir(parents=True)
    keystore = signing / "runtime.keystore"
    certificate = signing / "runtime-cert.pem"
    keystore.write_bytes(b"test private signer")
    certificate.write_bytes(b"test certificate")
    dependency.write_bytes(b"offline dependency")
    for path in (keystore, certificate, dependency):
        path.chmod(0o444)
    signer = RuntimeSigningIdentity(
        alias=alias,
        keystore_path=Path("signing/runtime.keystore"),
        keystore_sha256=hashlib.sha256(keystore.read_bytes()).hexdigest(),
        certificate_path=Path("signing/runtime-cert.pem"),
        certificate_sha256=hashlib.sha256(certificate.read_bytes()).hexdigest(),
    )
    manifest = RuntimeInputVaultManifest.from_directory(
        root,
        family_id=runtime_mapping.FAMILY_ID,
        family_version=runtime_mapping.FAMILY_VERSION,
        signing_identity=signer,
        retention_reason="recording fake",
    )
    manifest_path = tmp_path / "vault-manifest.json"
    manifest.write(manifest_path)
    return RuntimeInputVault.from_manifest(manifest_path, root=root), signer


def _recipe() -> RuntimeBuildRecipe:
    return RuntimeBuildRecipe(
        args=runtime_calibration.BUILD_COMMAND,
        timeout_seconds=900,
        apk_glob="build/app-debug.apk",
        output_relative_path="build/app-debug.apk",
        environment_policy={
            "mode": "private_allowlist",
            "dependency_resolution": "offline",
            "network_claim": "none",
            "retry": False,
        },
    )


def _receipt(
    lane: RuntimeFamilyLaneInput,
    signer: RuntimeSigningIdentity,
    apk_path: Path,
    apk_bytes: bytes,
    binding: dict[str, object],
    *,
    private_environment_root: Path | None = None,
) -> RuntimePreparationReceipt:
    metadata = {
        "package": lane.spec.package,
        "launcher_activity": lane.spec.activity,
        "version_code": 54,
        "version_name": "3.2.1",
        "min_sdk": 21,
        "target_sdk": 35,
        "compile_sdk": 35,
        "debuggable": True,
        "signer_sha256": signer.certificate_sha256,
        "signer_count": 1,
        "v1_verified": True,
        "v2_verified": True,
    }
    before = {"clean": True, "commit": "a" * 40}
    after = {"clean": True, "commit": "a" * 40}
    source = {
        "authority_kind": type(lane.source_authority).__name__,
        "before": before,
        "after": after,
        "mapping_binding": binding,
    }
    source["identity_sha256"] = hashlib.sha256(_canonical_bytes(source)).hexdigest()
    private_root = private_environment_root or (
        lane.options.workdir.parent / f"private-environment-{lane.lane_id}"
    )
    build = {
        "args": list(lane.build_recipe.args),
        "timeout_seconds": 900,
        "apk_glob": lane.build_recipe.apk_glob,
        "retry": False,
        "private_input_root": str(private_root),
        "runtime_signing_identity": signer.to_dict(),
    }
    Path(build["private_input_root"]).mkdir(parents=True, exist_ok=True)
    build["identity_sha256"] = hashlib.sha256(_canonical_bytes(build)).hexdigest()
    document: dict[str, object] = {
        "schema_version": 1,
        "status": "prepared",
        "prepared": True,
        "rejection_code": None,
        "claim_boundary": "local_source_build_preparation_only",
        "run_spec": {
            "path": str(lane.spec.source_path),
            "bytes": lane.spec.source_path.stat().st_size
            if lane.spec.source_path
            else 0,
            "sha256": lane.spec.source_sha256,
            "scenario": lane.spec.scenario.id,
        },
        "source": source,
        "production_admission": {"host": before},
        "production_admission_sha256": hashlib.sha256(
            _canonical_bytes({"host": before})
        ).hexdigest(),
        "build": build,
        "apk": {
            "built_path": str(apk_path),
            "path": str(apk_path),
            "bytes": len(apk_bytes),
            "sha256": hashlib.sha256(apk_bytes).hexdigest(),
            **metadata,
        },
        "sealed_apk": {
            "path": str(apk_path),
            "bytes": len(apk_bytes),
            "sha256": hashlib.sha256(apk_bytes).hexdigest(),
            "mode": "0444",
            "regular": True,
            "symlink": False,
            "hard_links": 1,
        },
        "runtime_input_vault": lane.runtime_input_vault.receipt(),
        "runtime_effects": {
            "shell": False,
            "device": False,
            "android_deployment": False,
            "execution_record": False,
            "agent_or_model": False,
        },
    }
    identity_body = dict(document)
    document["receipt_identity_sha256"] = hashlib.sha256(
        _canonical_bytes(identity_body)
    ).hexdigest()
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=True,
        receipt_bytes=encoded,
        receipt_sha256=hashlib.sha256(encoded).hexdigest(),
        rejection_code=None,
    )


def _repack_receipt(
    document: dict[str, object], *, recompute_identity: bool = True
) -> RuntimePreparationReceipt:
    if recompute_identity:
        for section_name in ("source", "build"):
            section = document.get(section_name)
            if isinstance(section, dict) and "identity_sha256" in section:
                section_body = dict(section)
                section_body.pop("identity_sha256", None)
                section["identity_sha256"] = hashlib.sha256(
                    _canonical_bytes(section_body)
                ).hexdigest()
        identity_body = dict(document)
        identity_body.pop("receipt_identity_sha256", None)
        document["receipt_identity_sha256"] = hashlib.sha256(
            _canonical_bytes(identity_body)
        ).hexdigest()
    encoded = _canonical_bytes(document)
    rejection_code = document.get("rejection_code")
    return RuntimePreparationReceipt(
        prepared=document.get("prepared") is True,
        receipt_bytes=encoded,
        receipt_sha256=hashlib.sha256(encoded).hexdigest(),
        rejection_code=rejection_code if isinstance(rejection_code, str) else None,
    )


def _family_inputs(tmp_path: Path) -> tuple[tuple[RuntimeFamilyLaneInput, ...], object]:
    vault, signer = _vault(tmp_path)
    lanes: list[RuntimeFamilyLaneInput] = []
    for index, lane_id in enumerate(runtime_mapping.FROZEN_LANE_ORDER, start=1):
        source_dir = tmp_path / f"source-{index}"
        source_dir.mkdir()
        source_spec = load_run_spec(
            CANDIDATE_ROOT / "runtime" / "lanes" / f"lane-{index:02d}" / "run-spec.yaml"
        )
        spec = replace(source_spec, host_project=source_dir)
        mapped_lane = runtime_mapping.load_runtime_mapping_release(
            MAPPING_ROOT / "mapping-release.json"
        ).lanes[index - 1]
        binding = {
            "release_id": runtime_mapping.RUNTIME_MAPPING_RELEASE_ID,
            "release_identity_sha256": runtime_mapping.load_runtime_mapping_release(
                MAPPING_ROOT / "mapping-release.json"
            ).identity_sha256,
            "lane_id": lane_id,
            "source_request_identity_sha256": mapped_lane.source_request.identity_sha256,
            "lane_identity_sha256": mapped_lane.identity_sha256,
            "projection_raw_sha256": mapped_lane.projection_raw_sha256,
            "driver_plan_raw_sha256": mapped_lane.driver_plan_raw_sha256,
            "recipe_raw_sha256": mapped_lane.recipe_raw_sha256,
            "run_spec_raw_sha256": mapped_lane.run_spec_raw_sha256,
        }
        lanes.append(
            RuntimeFamilyLaneInput(
                lane_id=lane_id,
                source_authority=_RecordingAuthority(binding),
                build_recipe=_recipe(),
                spec=spec,
                options=PlannedRunnerOptions(
                    device="none",
                    workdir=source_dir,
                    artifact_dir=tmp_path / "caller-artifacts" / f"lane-{index:02d}",
                    launch=False,
                ),
                apk_inspector=_RecordingInspector(),
                runtime_input_vault=vault,
                runtime_signing_identity=signer,
                allow_test_substitutes=True,
            )
        )
    return tuple(lanes), signer


def _rejected_receipt(code: str) -> RuntimePreparationReceipt:
    document: dict[str, object] = {
        "schema_version": 1,
        "status": "rejected",
        "prepared": False,
        "rejection_code": code,
        "claim_boundary": "local_source_build_preparation_only",
    }
    document["receipt_identity_sha256"] = hashlib.sha256(
        _canonical_bytes(document)
    ).hexdigest()
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=False,
        receipt_bytes=encoded,
        receipt_sha256=hashlib.sha256(encoded).hexdigest(),
        rejection_code=code,
    )


def test_prepare_runtime_family_success_records_four_opaque_lanes_and_gates(
    tmp_path: Path,
) -> None:
    lanes, signer = _family_inputs(tmp_path)
    calls: list[str] = []
    payloads = (b"control", b"defect", b"control", b"defect")

    def preparer(lane: RuntimeFamilyLaneInput) -> RuntimePreparationReceipt:
        calls.append(lane.lane_id)
        index = runtime_mapping.FROZEN_LANE_ORDER.index(lane.lane_id)
        apk_path = lane.options.artifact_dir / "build" / "app-debug.apk"
        apk_path.parent.mkdir(parents=True)
        apk_path.write_bytes(payloads[index])
        apk_path.chmod(0o444)
        binding = lane.source_authority.mapping_binding
        return _receipt(lane, signer, apk_path, payloads[index], binding)

    output = tmp_path / "family-output"
    receipt = prepare_runtime_family(
        candidate_root=CANDIDATE_ROOT,
        predecessor_root=MAPPING_ROOT,
        output_root=output,
        lane_inputs=lanes,
        lane_preparer=preparer,
    )

    assert isinstance(receipt, RuntimeFamilyPreparationReceipt)
    assert receipt.accepted is True
    assert calls == list(runtime_mapping.FROZEN_LANE_ORDER)
    assert [row.status for row in receipt.rows] == ["prepared"] * 4
    assert receipt.gates["sealed_apks"]["passed"] is True
    assert receipt.gates["family_signing_identity"]["passed"] is True
    assert receipt.gates["within_variant_byte_equality"]["passed"] is True
    assert receipt.gates["control_defect_byte_inequality"]["passed"] is True
    assert stage_status(output) == "accepted"
    verify_runtime_family_preparation(receipt)
    assert not list(output.rglob("*ExecutionRecord*"))
    assert not list(output.rglob("execution-record.json"))
    assert (output / "family-preparation.json").is_file()
    assert (output / "stage-terminal.json").is_file()


def test_lane_local_failure_reproves_health_and_continues_planned_lanes(
    tmp_path: Path,
) -> None:
    lanes, signer = _family_inputs(tmp_path)
    calls: list[str] = []
    health_calls: list[tuple[str, str]] = []

    def preparer(lane: RuntimeFamilyLaneInput) -> object:
        calls.append(lane.lane_id)
        if lane.lane_id == runtime_mapping.FROZEN_LANE_ORDER[0]:
            built = lane.options.workdir / "app" / "build" / "outputs" / "app-debug.apk"
            built.parent.mkdir(parents=True)
            built.write_bytes(b"real failed-lane APK")
            built.chmod(0o444)
            return RuntimeFamilyLaneResult(
                receipt=_rejected_receipt("build_failed"),
                artifacts=(built,),
                failure_scope="lane_local",
            )
        index = runtime_mapping.FROZEN_LANE_ORDER.index(lane.lane_id)
        payload = (b"control", b"defect", b"control", b"defect")[index]
        apk_path = lane.options.artifact_dir / "build" / "app-debug.apk"
        apk_path.parent.mkdir(parents=True)
        apk_path.write_bytes(payload)
        apk_path.chmod(0o444)
        return _receipt(
            lane, signer, apk_path, payload, lane.source_authority.mapping_binding
        )

    def health(row: object, next_lane: RuntimeFamilyLaneInput) -> bool:
        health_calls.append((row.lane_id, next_lane.lane_id))  # type: ignore[attr-defined]
        return True

    output = tmp_path / "family-output"
    receipt = prepare_runtime_family(
        candidate_root=CANDIDATE_ROOT,
        predecessor_root=MAPPING_ROOT,
        output_root=output,
        lane_inputs=lanes,
        lane_preparer=preparer,
        shared_health_check=health,
    )

    assert calls == list(runtime_mapping.FROZEN_LANE_ORDER)
    assert health_calls == [("ocrc-v1-lane-01", "ocrc-v1-lane-02")]
    assert [row.status for row in receipt.rows] == [
        "preparation_rejected",
        "prepared_but_family_not_admitted",
        "prepared_but_family_not_admitted",
        "prepared_but_family_not_admitted",
    ]
    preserved = list((output / "lanes" / "lane-01" / "preserved").glob("*"))
    assert len(preserved) == 1
    assert preserved[0].read_bytes() == b"real failed-lane APK"
    assert stage_status(output) == "rejected"
    verify_runtime_family_preparation(receipt)


def test_shared_failure_aborts_without_placeholder_receipts_or_later_builds(
    tmp_path: Path,
) -> None:
    lanes, _ = _family_inputs(tmp_path)
    calls: list[str] = []

    def preparer(lane: RuntimeFamilyLaneInput) -> RuntimeFamilyLaneResult:
        calls.append(lane.lane_id)
        return RuntimeFamilyLaneResult(
            build_started=True,
            build_attempts=1,
            failure_scope="shared",
            rejection_code="runtime_input_vault_rejected",
        )

    output = tmp_path / "family-output"
    receipt = prepare_runtime_family(
        candidate_root=CANDIDATE_ROOT,
        predecessor_root=MAPPING_ROOT,
        output_root=output,
        lane_inputs=lanes,
        lane_preparer=preparer,
    )

    assert calls == [runtime_mapping.FROZEN_LANE_ORDER[0]]
    assert receipt.accepted is False
    assert receipt.rows[0].status == "preparation_rejected"
    assert [row.status for row in receipt.rows[1:]] == [
        "not_prepared_due_to_family_abort"
    ] * 3
    assert all(row.preparation_receipt is None for row in receipt.rows[1:])
    assert not (output / "lanes" / "lane-02").exists()
    assert stage_status(output) == "rejected"


def test_interrupted_started_family_is_abandoned_and_has_no_terminal_receipt(
    tmp_path: Path,
) -> None:
    lanes, _ = _family_inputs(tmp_path)

    def preparer(_lane: RuntimeFamilyLaneInput) -> object:
        raise KeyboardInterrupt

    output = tmp_path / "family-output"
    with pytest.raises(KeyboardInterrupt):
        prepare_runtime_family(
            candidate_root=CANDIDATE_ROOT,
            predecessor_root=MAPPING_ROOT,
            output_root=output,
            lane_inputs=lanes,
            lane_preparer=preparer,
        )
    assert stage_status(output) == "abandoned"
    assert (output / "stage-start.json").is_file()
    assert not (output / "stage-terminal.json").exists()
    assert not (output / "family-preparation.json").exists()


@pytest.mark.parametrize(
    ("name", "payloads"),
    (
        (
            "within_variant_byte_equality",
            (b"control", b"defect", b"different-control", b"defect"),
        ),
        (
            "control_defect_byte_inequality",
            (b"same", b"same", b"same", b"same"),
        ),
    ),
)
def test_failed_byte_gate_preserves_all_sealed_apks(
    tmp_path: Path,
    name: str,
    payloads: tuple[bytes, bytes, bytes, bytes],
) -> None:
    lanes, signer = _family_inputs(tmp_path)

    def preparer(lane: RuntimeFamilyLaneInput) -> RuntimePreparationReceipt:
        index = runtime_mapping.FROZEN_LANE_ORDER.index(lane.lane_id)
        apk_path = lane.options.artifact_dir / "build" / "app-debug.apk"
        apk_path.parent.mkdir(parents=True)
        apk_path.write_bytes(payloads[index])
        apk_path.chmod(0o444)
        return _receipt(
            lane,
            signer,
            apk_path,
            payloads[index],
            lane.source_authority.mapping_binding,
        )

    output = tmp_path / "family-output"
    receipt = prepare_runtime_family(
        candidate_root=CANDIDATE_ROOT,
        predecessor_root=MAPPING_ROOT,
        output_root=output,
        lane_inputs=lanes,
        lane_preparer=preparer,
    )

    assert receipt.accepted is False
    assert receipt.gates[name]["passed"] is False
    assert [row.status for row in receipt.rows] == [
        "prepared_but_family_not_admitted"
    ] * 4
    assert all(
        (
            output
            / "lanes"
            / f"lane-{index:02d}"
            / "artifacts"
            / "build"
            / "app-debug.apk"
        ).is_file()
        for index in range(1, 5)
    )
    verify_runtime_family_preparation(receipt)


def test_metadata_gate_uses_frozen_expected_metadata_not_only_cross_lane_equality(
    tmp_path: Path,
) -> None:
    lanes, signer = _family_inputs(tmp_path)
    wrong_metadata = ApkMetadata(
        package=lanes[0].spec.package,
        launcher_activity=lanes[0].spec.activity or "",
        version_code=54,
        version_name="not-the-frozen-version",
    )
    lanes = (replace(lanes[0], expected_apk_metadata=wrong_metadata), *lanes[1:])

    def preparer(lane: RuntimeFamilyLaneInput) -> RuntimePreparationReceipt:
        apk_path = lane.options.artifact_dir / "build" / "app-debug.apk"
        apk_path.parent.mkdir(parents=True)
        apk_path.write_bytes(
            b"control"
            if lane.lane_id in {"ocrc-v1-lane-01", "ocrc-v1-lane-03"}
            else b"defect"
        )
        apk_path.chmod(0o444)
        return _receipt(
            lane,
            signer,
            apk_path,
            apk_path.read_bytes(),
            lane.source_authority.mapping_binding,
        )

    receipt = prepare_runtime_family(
        candidate_root=CANDIDATE_ROOT,
        predecessor_root=MAPPING_ROOT,
        output_root=tmp_path / "family-output",
        lane_inputs=lanes,
        lane_preparer=preparer,
    )
    assert receipt.accepted is False
    assert receipt.gates["family_metadata_identity"]["passed"] is False
    assert [row.status for row in receipt.rows] == [
        "prepared_but_family_not_admitted"
    ] * 4


@pytest.mark.parametrize(
    "gate_name",
    (
        "sealed_apks",
        "receipt_identity",
        "family_signing_identity",
        "family_vault_identity",
        "independent_build_environments",
        "single_build_attempt",
        "no_runtime_effects",
        "mapping_handoff_identity",
        "source_identity",
    ),
)
def test_each_family_wide_gate_rejects_and_keeps_real_lane_artifacts(
    tmp_path: Path,
    gate_name: str,
) -> None:
    lanes, default_signer = _family_inputs(tmp_path)
    alternate_vault: RuntimeInputVault | None = None
    alternate_signer = default_signer
    if gate_name == "family_signing_identity":
        alternate_vault, alternate_signer = _vault(
            tmp_path / "alternate-signer", alias="alternate-runtime"
        )
    elif gate_name == "family_vault_identity":
        alternate_vault, _ = _vault(tmp_path / "alternate-vault")
    if alternate_vault is not None:
        lanes = (
            *lanes[:3],
            replace(
                lanes[3],
                runtime_input_vault=alternate_vault,
                runtime_signing_identity=alternate_signer,
            ),
        )

    shared_environment: Path | None = None
    if gate_name == "independent_build_environments":
        shared_environment = (
            lanes[2].options.workdir.parent / f"private-environment-{lanes[2].lane_id}"
        )

    def preparer(lane: RuntimeFamilyLaneInput) -> object:
        index = runtime_mapping.FROZEN_LANE_ORDER.index(lane.lane_id)
        payload = (b"control", b"defect", b"control", b"defect")[index]
        apk_path = lane.options.artifact_dir / "build" / "app-debug.apk"
        apk_path.parent.mkdir(parents=True)
        apk_path.write_bytes(payload)
        apk_path.chmod(0o444)
        signer = lane.runtime_signing_identity or default_signer
        receipt = _receipt(
            lane,
            signer,
            apk_path,
            payload,
            lane.source_authority.mapping_binding,
            private_environment_root=shared_environment,
        )
        tamper_last_lane = lane.lane_id == runtime_mapping.FROZEN_LANE_ORDER[3]
        if gate_name == "receipt_identity" and tamper_last_lane:
            document = receipt.receipt
            document["receipt_identity_sha256"] = "0" * 64
            return _repack_receipt(document, recompute_identity=False)
        if gate_name == "sealed_apks" and tamper_last_lane:
            document = receipt.receipt
            assert isinstance(document["sealed_apk"], dict)
            document["sealed_apk"]["sha256"] = "0" * 64
            return _repack_receipt(document)
        if gate_name == "no_runtime_effects" and tamper_last_lane:
            document = receipt.receipt
            assert isinstance(document["runtime_effects"], dict)
            document["runtime_effects"]["shell"] = True
            return _repack_receipt(document)
        if gate_name == "mapping_handoff_identity" and tamper_last_lane:
            document = receipt.receipt
            source = document["source"]
            assert isinstance(source, dict)
            binding = source["mapping_binding"]
            assert isinstance(binding, dict)
            binding["lane_id"] = "tampered-lane"
            return _repack_receipt(document)
        if gate_name == "source_identity" and tamper_last_lane:
            document = receipt.receipt
            source = document["source"]
            assert isinstance(source, dict)
            after = source["after"]
            assert isinstance(after, dict)
            after["commit"] = "b" * 40
            return _repack_receipt(document)
        if gate_name == "single_build_attempt" and tamper_last_lane:
            return RuntimeFamilyLaneResult(
                receipt=receipt,
                build_started=True,
                build_attempts=2,
            )
        return receipt

    output = tmp_path / "family-output"
    receipt = prepare_runtime_family(
        candidate_root=CANDIDATE_ROOT,
        predecessor_root=MAPPING_ROOT,
        output_root=output,
        lane_inputs=lanes,
        lane_preparer=preparer,
    )

    assert receipt.accepted is False
    assert receipt.gates[gate_name]["passed"] is False
    expected_statuses = (
        ["prepared_but_family_not_admitted"] * 4
        if gate_name
        in {
            "family_signing_identity",
            "family_vault_identity",
            "independent_build_environments",
        }
        else ["prepared_but_family_not_admitted"] * 3 + ["preparation_rejected"]
    )
    assert [row.status for row in receipt.rows] == expected_statuses
    assert all(
        (
            output
            / "lanes"
            / f"lane-{index:02d}"
            / "artifacts"
            / "build"
            / "app-debug.apk"
        ).is_file()
        for index in range(1, 5)
    )
    verify_runtime_family_preparation(receipt)
