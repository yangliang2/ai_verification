"""M9-R2 non-holdout full-chain recovery canary.

This executor is deliberately separate from the frozen #136/#137 population.
It consumes the historical matched pair recovered by #148 only as canary
input, creates new neutral lane identities, runs the production seam on a real
Android target, invokes a separately identified clean-context falsification
reviewer, and emits a canary-only reconciliation.  It can never emit the M9
formal result word.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from aiverify.bench.m9_qualification import (
    ACTIVITY,
    BACKEND,
    BASELINE_COMMIT,
    CONTRADICTION_REJECTION_BOUNDARY,
    PACKAGE,
    RUNNER_POLICY,
    SOURCE_ORIGIN,
    DEFECT_COMMIT,
    audit_contradiction_packet,
)
from aiverify.discovery import (
    AttackPlan,
    Finding,
    FalsificationReviewContext,
    FalsificationReviewerIdentity,
    ImmutableArtifactRef,
    ProjectTarget,
    RiskHypothesis,
    run_falsification_review,
)
from aiverify.discovery.falsification_review import (
    FALSIFICATION_REVIEW_ROLE_ID,
    REVIEW_DIMENSIONS,
    reconcile_finding,
)
from aiverify.harness.device.controller import DeviceController
from aiverify.providers.codex_cli import CodexCliProvider
from aiverify.runner.admission import (
    PlannedRunnerOptions,
    admit_production_seam,
    write_admission_receipt,
)
from aiverify.runner.cli import build_instruction_prefix, run as run_spec
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.package_reset import PackageResetError, reset_package_data
from aiverify.runner.run_spec import load_run_spec


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_SPEC_ROOT = REPO_ROOT / "bench/m9/recovery-canary"
REVIEW_SCHEMA = Path(__file__).with_name("m9_falsification_review_schema.json")
DEFAULT_ARTIFACT_ROOT = (
    REPO_ROOT
    / "docs/runs/2026-08-07-issue-150-m9-r2-full-chain-canary"
    / "attempts/attempt-01"
)
DEFAULT_FIXTURE_ROOT = Path("/private/tmp/m9-r2-canary-fixtures/attempt-01")
DEFAULT_FIRST_INPUT = Path("/private/tmp/m9-r1-canary-recovery/control")
DEFAULT_SECOND_INPUT = Path("/private/tmp/m9-r1-canary-recovery/defect")
CONTRADICTION_PACKET = (
    REPO_ROOT
    / "docs/runs/2026-08-05-issue-136-qualification-freeze"
    / "contradiction-packet.json"
)

CONTROL_TREE = "19455e693ec8c96c37a56aec55059a220826c5a3"
SECOND_TREE = "34998af23aed59aa17eaf915d848ab1b916a63e2"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
SECOND_PATCH_SHA256 = "cc317d74012a83ab6a2e400fbc7442dfcb3bec8464fdbf68a1ba1cdc7974b277"
FIRST_APK_SHA256 = "d38b30f17010da114b5585dadec8326eb76b04dfbae4a175f7cb2840a0093c66"
SECOND_APK_SHA256 = "61063a0fd247eb03d1bd251b0d9359c3c2a5ea07cb8abe4b38d3daae57c153ac"
APK_RELATIVE = Path("app/build/outputs/apk/debug/app-debug.apk")
LATIN_IME = (
    "com.google.android.inputmethod.latin/"
    "com.android.inputmethod.latin.LatinIME"
)
ENGLISH_US_INPUT_SUBTYPE = "1594443099"
CLAIM_BOUNDARY = (
    "local API-35 execution of one historical matched pair with exact source, "
    "package, runtime, agent, oracle, and review evidence"
)
SOURCE_SCOPE = (
    "app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/DefaultTaskRepository.kt",
    "app/src/main/AndroidManifest.xml",
    "app/build.gradle.kts",
    "settings.gradle.kts",
)


class M9RecoveryCanaryError(RuntimeError):
    """Raised when R2 evidence cannot reach a trustworthy terminal result."""


@dataclass(frozen=True)
class _Variant:
    lane_id: str
    environment_variable: str
    role: str
    source_input: Path
    fixture_commit: str
    expected_tree: str
    expected_patch_sha256: str
    expected_apk_sha256: str


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha(value: object) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _write_json(path: Path, value: object) -> None:
    if path.exists():
        raise M9RecoveryCanaryError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, value: str) -> None:
    if path.exists():
        raise M9RecoveryCanaryError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    input_bytes: bytes | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    process = subprocess.run(
        list(args),
        cwd=str(cwd) if cwd is not None else None,
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    return {
        "args": list(args),
        "cwd": str(cwd.resolve()) if cwd is not None else None,
        "returncode": process.returncode,
        "stdout": process.stdout.decode("utf-8", errors="replace"),
        "stderr": process.stderr.decode("utf-8", errors="replace"),
        "duration_seconds": round(time.monotonic() - started, 3),
    }


def _git(path: Path, *args: str) -> str:
    result = _command(["git", *args], cwd=path)
    if result["returncode"] != 0:
        raise M9RecoveryCanaryError(
            f"git {' '.join(args)} failed in {path}: {result['stderr'].strip()}"
        )
    return str(result["stdout"]).strip()


def _git_patch(path: Path) -> bytes:
    process = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=path,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise M9RecoveryCanaryError(
            f"cannot read source patch from {path}: "
            + process.stderr.decode("utf-8", errors="replace").strip()
        )
    return process.stdout


def _variants(first_input: Path, second_input: Path) -> tuple[_Variant, ...]:
    """Keep the auditor mapping in memory until both reviews are terminal."""

    return (
        _Variant(
            lane_id="m9-r2-canary-alpha",
            environment_variable="M9_R2_CANARY_ALPHA_PROJECT",
            role="control",
            source_input=first_input.resolve(),
            fixture_commit=BASELINE_COMMIT,
            expected_tree=CONTROL_TREE,
            expected_patch_sha256=EMPTY_SHA256,
            expected_apk_sha256=FIRST_APK_SHA256,
        ),
        _Variant(
            lane_id="m9-r2-canary-beta",
            environment_variable="M9_R2_CANARY_BETA_PROJECT",
            role="defect",
            source_input=second_input.resolve(),
            fixture_commit=DEFECT_COMMIT,
            expected_tree=SECOND_TREE,
            expected_patch_sha256=SECOND_PATCH_SHA256,
            expected_apk_sha256=SECOND_APK_SHA256,
        ),
    )


def _contradiction_gate(root: Path) -> dict[str, Any]:
    packet = _read_json(CONTRADICTION_PACKET)
    audit = audit_contradiction_packet(packet, observed_command_calls=[])
    receipt = {
        "schema_version": 1,
        "source": {
            "path": str(CONTRADICTION_PACKET.relative_to(REPO_ROOT)),
            "sha256": _sha256_path(CONTRADICTION_PACKET),
        },
        "audit": audit,
        "non_holdout_canary": True,
        "formal_qualification_eligible": False,
        "denominator_member": False,
        "rejected_before_build_device_agent_runtime": audit["status"] == "pass",
    }
    _write_json(root / "contradiction-rejection.json", receipt)
    if (
        audit["status"] != "pass"
        or audit["rejection_boundary"] != CONTRADICTION_REJECTION_BOUNDARY
        or audit["command_calls"]
    ):
        raise M9RecoveryCanaryError(
            "contradiction packet was not rejected before external side effects"
        )
    return audit


def _inspect_source_input(variant: _Variant) -> dict[str, Any]:
    source = variant.source_input
    apk = source / APK_RELATIVE
    if not source.is_dir() or not apk.is_file():
        raise M9RecoveryCanaryError(f"recovered canary input is missing: {source}")
    patch = _git_patch(source)
    observed = {
        "origin": _git(source, "remote", "get-url", "origin"),
        "commit": _git(source, "rev-parse", "HEAD"),
        "tree": _git(source, "write-tree"),
        "patch_sha256": _sha256_bytes(patch),
        "apk_sha256": _sha256_path(apk),
        "apk_bytes": apk.stat().st_size,
    }
    expected = {
        "origin": SOURCE_ORIGIN,
        "commit": BASELINE_COMMIT,
        "tree": variant.expected_tree,
        "patch_sha256": variant.expected_patch_sha256,
        "apk_sha256": variant.expected_apk_sha256,
    }
    for field, expected_value in expected.items():
        if observed[field] != expected_value:
            raise M9RecoveryCanaryError(
                f"{variant.lane_id} recovered {field} drifted: "
                f"{observed[field]} != {expected_value}"
            )
    return {**observed, "path": str(source), "patch_bytes": len(patch)}


def _prepare_fixture(
    variant: _Variant,
    fixture_root: Path,
) -> tuple[Path, dict[str, Any]]:
    destination = fixture_root / variant.lane_id
    if destination.exists():
        raise M9RecoveryCanaryError(
            f"neutral canary fixture already exists: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    created = _command(
        [
            "git",
            "worktree",
            "add",
            "--detach",
            str(destination),
            variant.fixture_commit,
        ],
        cwd=variant.source_input,
        timeout=120,
    )
    if created["returncode"] != 0:
        raise M9RecoveryCanaryError(
            f"cannot create {variant.lane_id}: {created['stderr'].strip()}"
        )
    apk_source = variant.source_input / APK_RELATIVE
    apk_target = destination / APK_RELATIVE
    apk_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(apk_source, apk_target)
    observed_tree = _git(destination, "write-tree")
    observed_patch_sha = _sha256_bytes(_git_patch(destination))
    observed_apk_sha = _sha256_path(apk_target)
    if (
        observed_tree != variant.expected_tree
        or observed_patch_sha != EMPTY_SHA256
        or observed_apk_sha != variant.expected_apk_sha256
        or _git(destination, "rev-parse", "HEAD") != variant.fixture_commit
    ):
        raise M9RecoveryCanaryError(
            f"{variant.lane_id} neutral fixture identity drifted"
        )
    receipt = {
        "schema_version": 1,
        "lane_id": variant.lane_id,
        "neutral_worktree": str(destination),
        "source_origin": _git(destination, "remote", "get-url", "origin"),
        "source_commit": variant.fixture_commit,
        "source_tree": observed_tree,
        "fixture_patch_sha256": observed_patch_sha,
        "recovered_source_patch_sha256": variant.expected_patch_sha256,
        "apk": {
            "path": str(apk_target),
            "sha256": observed_apk_sha,
            "bytes": apk_target.stat().st_size,
        },
        "worktree_status": _git(
            destination, "status", "--porcelain=v1", "--untracked-files=all"
        ),
        "preparation": {
            "worktree_add": created,
            "patch_apply": None,
            "android_build_performed": False,
        },
        "known_canary_role_disclosed": False,
    }
    return destination, receipt


def _reset_package(lane_dir: Path, *, device: str) -> None:
    try:
        result = reset_package_data(
            controller=DeviceController(serial=device),
            device_serial=device,
            package=PACKAGE,
        )
    except PackageResetError as error:
        _write_json(lane_dir / "package-reset.json", error.result.to_dict())
        raise
    _write_json(lane_dir / "package-reset.json", result.to_dict())


def _configure_device_input(lane_dir: Path, *, device: str) -> None:
    """Freeze the emulator's hardware-text path to the enabled English US IME."""

    commands = (
        (
            "default_input_method",
            [
                "adb",
                "-s",
                device,
                "shell",
                "settings",
                "get",
                "secure",
                "default_input_method",
            ],
        ),
        (
            "enabled_input_methods",
            [
                "adb",
                "-s",
                device,
                "shell",
                "settings",
                "get",
                "secure",
                "enabled_input_methods",
            ],
        ),
        (
            "selected_subtype_before",
            [
                "adb",
                "-s",
                device,
                "shell",
                "settings",
                "get",
                "secure",
                "selected_input_method_subtype",
            ],
        ),
        (
            "select_english_us_subtype",
            [
                "adb",
                "-s",
                device,
                "shell",
                "settings",
                "put",
                "secure",
                "selected_input_method_subtype",
                ENGLISH_US_INPUT_SUBTYPE,
            ],
        ),
        (
            "selected_subtype_after",
            [
                "adb",
                "-s",
                device,
                "shell",
                "settings",
                "get",
                "secure",
                "selected_input_method_subtype",
            ],
        ),
    )
    operations = []
    for operation, args in commands:
        result = _command(args, timeout=30)
        operations.append({"operation": operation, **result})
    values = {
        item["operation"]: str(item["stdout"]).strip() for item in operations
    }
    status = (
        "passed"
        if all(item["returncode"] == 0 for item in operations)
        and values["default_input_method"] == LATIN_IME
        and ENGLISH_US_INPUT_SUBTYPE in values["enabled_input_methods"]
        and values["selected_subtype_after"] == ENGLISH_US_INPUT_SUBTYPE
        else "failed"
    )
    receipt = {
        "schema_version": 1,
        "status": status,
        "device": device,
        "expected_input_method": LATIN_IME,
        "expected_subtype": {
            "name": "English (US)",
            "hash": ENGLISH_US_INPUT_SUBTYPE,
        },
        "operations": operations,
    }
    _write_json(lane_dir / "device-input-setup.json", receipt)
    if status != "passed":
        raise M9RecoveryCanaryError(
            "device English US input subtype could not be frozen"
        )


def _pre_run_setup(lane_dir: Path, *, device: str) -> None:
    _reset_package(lane_dir, device=device)
    _configure_device_input(lane_dir, device=device)


def _canary_instruction_prefix(device: str) -> str:
    delete_keys = " ".join(["67"] * 32)
    return (
        build_instruction_prefix(device)
        + "\nCANARY BOUNDS AND TEXT-ENTRY RULES:\n"
        + "- Finish within seven minutes and at most 40 device commands. "
        + "After three unsuccessful correction cycles for one action, report "
        + "that action FAILED and return the complete five-action result.\n"
        + "- The harness has frozen the enabled English (US) input subtype. "
        + "Do not change keyboards or device language. The task tokens contain "
        + "no spaces; type them exactly as written with `adb shell input text`.\n"
        + "- To replace an editable field, tap it, then run "
        + f"`adb -s {device} shell input keyevent KEYCODE_MOVE_END`, followed "
        + f"by `adb -s {device} shell input keyevent {delete_keys}`, then type "
        + "the replacement once and verify it with one fresh layout.\n"
        + "- Before every tap on the Save task control, dismiss the on-screen "
        + f"keyboard once with `adb -s {device} shell input keyevent "
        + "KEYCODE_BACK`, take one fresh layout, locate Save task again, and "
        + "then tap its current center.\n"
        + "- Saving, navigating, and reopening are dispatch actions. If the "
        + "product displays the old title after an edit, still tap that same "
        + "unique task and mark the dispatch PASSED; the oracle, not the "
        + "driver, judges the observed title.\n"
        + "- Do not improvise alternate text values or repeatedly append "
        + "partial strings.\n\n"
    )


def _receipt_path(lane_dir: Path, ref: Mapping[str, Any]) -> Path:
    value = ref.get("path")
    if not isinstance(value, str):
        raise M9RecoveryCanaryError("role identity reference has no path")
    path = (lane_dir / value).resolve()
    try:
        path.relative_to(lane_dir.resolve())
    except ValueError as error:
        raise M9RecoveryCanaryError(
            "role identity reference escapes the lane"
        ) from error
    return path


def _assert_default_receipt(receipt: Mapping[str, Any]) -> None:
    command = receipt.get("command")
    argv = command.get("argv_without_prompt") if isinstance(command, Mapping) else None
    if (
        receipt.get("requested_model") is not None
        or not isinstance(receipt.get("effective_model"), str)
        or not receipt["effective_model"]
        or not isinstance(argv, list)
        or "--model" in argv
    ):
        raise M9RecoveryCanaryError(
            "Codex default-selection identity is missing or contradictory"
        )


def _write_effective_identity(
    lane_dir: Path,
    verdict: Mapping[str, Any],
) -> dict[str, Any]:
    provenance_path = lane_dir / "execution-provenance.json"
    if not provenance_path.is_file():
        payload = {
            "schema_version": 1,
            "status": "incomplete",
            "selection_policy": "codex_cli_default",
            "requested_model": None,
            "model_override_present": False,
            "reason": "execution provenance is unavailable",
            "verdict_execution": verdict.get("execution"),
        }
        _write_json(lane_dir / "effective-execution-identity.json", payload)
        return payload
    provenance = _read_json(provenance_path)
    roles = provenance.get("roles")
    if not isinstance(roles, Mapping):
        raise M9RecoveryCanaryError("execution provenance role set is missing")
    role_summaries: dict[str, Any] = {}
    production_invocation_id: str | None = None
    for role_name in ("journey_driver", "l3_semantic_judge"):
        role = roles.get(role_name)
        if not isinstance(role, Mapping):
            raise M9RecoveryCanaryError(f"missing role identity: {role_name}")
        if role.get("requested_model") is not None:
            raise M9RecoveryCanaryError(
                f"{role_name} did not request Codex CLI default selection"
            )
        invocations = []
        for ref in role.get("invocations", []):
            if not isinstance(ref, Mapping):
                raise M9RecoveryCanaryError("malformed role identity reference")
            receipt_path = _receipt_path(lane_dir, ref)
            receipt = _read_json(receipt_path)
            _assert_default_receipt(receipt)
            source = receipt["effective_model_source"]
            invocation_id = f"{source['thread_id']}:{source['turn_id']}"
            if role_name == "journey_driver" and production_invocation_id is None:
                production_invocation_id = invocation_id
            invocations.append(
                {
                    "identity_ref": str(receipt_path.relative_to(lane_dir)),
                    "identity_sha256": _sha256_path(receipt_path),
                    "effective_model": receipt["effective_model"],
                    "invocation_id": invocation_id,
                    "model_override_present": False,
                }
            )
        role_summaries[role_name] = {
            "status": role.get("status"),
            "selection_policy": "codex_cli_default",
            "requested_model": None,
            "model_override_present": False,
            "invocations": invocations,
            **(
                {"reason": role.get("reason")}
                if role.get("status") == "not_applicable"
                else {}
            ),
        }
    if (
        role_summaries["journey_driver"]["status"] != "invoked"
        or not role_summaries["journey_driver"]["invocations"]
        or production_invocation_id is None
    ):
        raise M9RecoveryCanaryError("journey driver identity is not accountable")
    payload = {
        "schema_version": 1,
        "status": "complete",
        "backend": BACKEND,
        "selection_policy": "codex_cli_default",
        "requested_model": None,
        "model_override_present": False,
        "production_invocation_id": production_invocation_id,
        "roles": role_summaries,
        "execution_provenance": {
            "ref": "execution-provenance.json",
            "sha256": _sha256_path(provenance_path),
        },
        "verdict_execution": verdict.get("execution"),
    }
    _write_json(lane_dir / "effective-execution-identity.json", payload)
    return payload


def _copy_raw_evidence(lane_dir: Path) -> tuple[str, ...]:
    refs: list[str] = []
    inventory = []
    for ref in ("verdict.json", "runner-setup.json", "live-validation-gate.json"):
        path = lane_dir / ref
        if not path.is_file():
            continue
        refs.append(ref)
        inventory.append(
            {"ref": ref, "sha256": _sha256_path(path), "bytes": path.stat().st_size}
        )
    for source in sorted((lane_dir / "artifacts").rglob("*")):
        if not source.is_file() or source.name not in {
            "screen.png",
            "layout.json",
            "logcat.txt",
            "commands.json",
            "event.json",
        }:
            continue
        relative = Path("raw") / source.relative_to(lane_dir / "artifacts")
        destination = lane_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        ref = relative.as_posix()
        refs.append(ref)
        inventory.append(
            {
                "ref": ref,
                "sha256": _sha256_path(destination),
                "bytes": destination.stat().st_size,
            }
        )
    if not refs:
        absence = lane_dir / "raw/absence.json"
        _write_json(
            absence,
            {
                "schema_version": 1,
                "status": "no_runtime_evidence",
            },
        )
        refs.append("raw/absence.json")
        inventory.append(
            {
                "ref": "raw/absence.json",
                "sha256": _sha256_path(absence),
                "bytes": absence.stat().st_size,
            }
        )
    _write_json(
        lane_dir / "raw-evidence-inventory.json",
        {"schema_version": 1, "artifacts": inventory},
    )
    return tuple(dict.fromkeys(refs))


def _oracle_conclusion(verdict: Mapping[str, Any]) -> str:
    execution = verdict.get("execution")
    if not (
        isinstance(execution, Mapping)
        and execution.get("status") == "completed"
        and execution.get("accounting_eligible") is True
    ):
        return "inconclusive"
    oracles = (verdict.get("l1"), verdict.get("l2"), verdict.get("l3"))
    if any(
        isinstance(item, Mapping) and item.get("outcome") == "fail"
        for item in oracles
    ):
        return "supported"
    l3 = verdict.get("l3")
    if isinstance(l3, Mapping):
        return "rejected" if l3.get("outcome") == "pass" else "inconclusive"
    l2 = verdict.get("l2")
    if isinstance(l2, Mapping) and l2.get("outcome") == "pass":
        return "rejected"
    return "inconclusive"


def _accountable(
    verdict: Mapping[str, Any],
    record: Mapping[str, Any],
) -> bool:
    return bool(
        record.get("lifecycle_state") == "completed"
        and isinstance(record.get("execution"), Mapping)
        and record["execution"].get("status") == "completed"
        and record["execution"].get("accounting_eligible") is True
        and isinstance(verdict.get("execution"), Mapping)
        and verdict["execution"].get("status") == "completed"
        and verdict["execution"].get("accounting_eligible") is True
    )


def _make_finding(
    lane_id: str,
    conclusion: str,
    raw_refs: tuple[str, ...],
) -> Finding:
    return Finding(
        finding_id=f"finding-{lane_id}",
        target_id=f"target-{lane_id}",
        hypothesis_id=f"hypothesis-{lane_id}",
        conclusion=conclusion,
        evidence_refs=raw_refs,
        impact=(
            "an edited task title may not remain visible across the admitted "
            "navigation and process boundary"
        ),
        claim_boundary=CLAIM_BOUNDARY,
        rationale=(
            "The candidate conclusion is derived only from this terminal runner "
            "record, oracle outputs, and checksum-bound runtime evidence."
        ),
    )


def _execute_runtime_lane(
    root: Path,
    variant: _Variant,
    worktree: Path,
    fixture_receipt: Mapping[str, Any],
    *,
    device: str,
) -> dict[str, Any]:
    lane_dir = root / "canary-artifacts" / variant.lane_id
    lane_dir.mkdir(parents=True, exist_ok=False)
    _write_json(lane_dir / "neutral-fixture-binding.json", fixture_receipt)
    spec_path = RUN_SPEC_ROOT / f"{variant.lane_id}.yaml"
    spec = load_run_spec(
        spec_path,
        environ={variant.environment_variable: str(worktree)},
    )
    artifact_dir = lane_dir / "artifacts"
    options = PlannedRunnerOptions(
        device=device,
        workdir=worktree,
        artifact_dir=artifact_dir,
        expected_source_commit=variant.fixture_commit,
        launch=True,
        requested_driver_model=None,
        requested_l3_model=None,
        backend=BACKEND,
        runner_policy_version=RUNNER_POLICY,
    )
    admission = admit_production_seam(spec, options)
    write_admission_receipt(
        admission,
        lane_dir / "production-seam-admission.json",
    )
    if not admission.admitted:
        raise M9RecoveryCanaryError(
            f"{variant.lane_id} production admission failed: "
            + "; ".join(admission.reasons)
        )
    started = time.monotonic()
    verdict = run_spec(
        spec,
        device=device,
        artifact_dir=artifact_dir,
        workdir=worktree,
        launch=True,
        model=None,
        l3_model=None,
        instruction_prefix=_canary_instruction_prefix(device),
        run_spec_path=spec_path,
        admission_required=True,
        admission_receipt=admission,
        admission_options=options,
        formal_one_attempt=True,
        pre_run_setup=lambda: _pre_run_setup(lane_dir, device=device),
    )
    duration = round(time.monotonic() - started, 3)
    record = load_execution_record(lane_dir / "execution-record.json")
    identity = _write_effective_identity(lane_dir, verdict)
    raw_refs = _copy_raw_evidence(lane_dir)
    conclusion = _oracle_conclusion(verdict)
    finding = _make_finding(variant.lane_id, conclusion, raw_refs)
    _write_json(lane_dir / "finding.json", finding.to_dict())
    accountable = _accountable(verdict, record)
    observation = {
        "schema_version": 1,
        "lane_id": variant.lane_id,
        "accountable": accountable,
        "candidate_finding_conclusion": conclusion,
        "duration_seconds": duration,
        "run_spec": {
            "path": str(spec_path.relative_to(REPO_ROOT)),
            "sha256": spec.source_sha256,
        },
        "execution_record_sha256": _sha256_path(
            lane_dir / "execution-record.json"
        ),
        "effective_identity_sha256": _sha256_path(
            lane_dir / "effective-execution-identity.json"
        ),
        "non_holdout_canary": True,
        "formal_qualification_eligible": False,
        "formal_qualification_one_attempt": False,
        "runner_single_invocation_mode": True,
        "canary_l3_retry_disabled": True,
    }
    _write_json(lane_dir / "lane-observation.json", observation)
    return {
        "lane_id": variant.lane_id,
        "role": variant.role,
        "lane_dir": lane_dir,
        "worktree": worktree,
        "verdict": verdict,
        "record": record,
        "identity": identity,
        "finding": finding,
        "raw_refs": raw_refs,
        "accountable": accountable,
        "finding_conclusion": conclusion,
        "duration_seconds": duration,
        "run_spec_sha256": spec.source_sha256,
        "source_commit": variant.fixture_commit,
    }


def _copy_peer_evidence(row: Mapping[str, Any], peer: Mapping[str, Any]) -> Path:
    lane_dir = Path(row["lane_dir"])
    peer_dir = Path(peer["lane_dir"])
    peer_root = lane_dir / "peer"
    peer_root.mkdir(parents=True, exist_ok=False)
    copies = []
    for name in (
        "verdict.json",
        "execution-record.json",
        "raw-evidence-inventory.json",
        "effective-execution-identity.json",
    ):
        source = peer_dir / name
        destination = peer_root / name
        shutil.copy2(source, destination)
        copies.append(
            {
                "ref": f"peer/{name}",
                "sha256": _sha256_path(destination),
                "bytes": destination.stat().st_size,
            }
        )
    path = lane_dir / "peer-evidence-index.json"
    _write_json(
        path,
        {
            "schema_version": 1,
            "peer_lane_id": peer["lane_id"],
            "artifacts": copies,
            "known_canary_role_disclosed": False,
            "expected_result_disclosed": False,
        },
    )
    return path


def _review_contract(
    row: Mapping[str, Any],
    peer_index: Path,
) -> tuple[
    FalsificationReviewContext,
    ProjectTarget,
    RiskHypothesis,
    AttackPlan,
]:
    lane_id = str(row["lane_id"])
    lane_dir = Path(row["lane_dir"])
    target = ProjectTarget(
        target_id=f"target-{lane_id}",
        source_origin=SOURCE_ORIGIN,
        source_commit=str(row["source_commit"]),
        worktree=str(Path(row["worktree"])),
        scope=SOURCE_SCOPE,
        discovery_budget=8,
    )
    hypothesis = RiskHypothesis(
        hypothesis_id=f"hypothesis-{lane_id}",
        target_id=target.target_id,
        quality_property="edited task persistence across a process boundary",
        assumptions=(
            "the recorded UI actions reached the declared task-state boundary",
        ),
        trigger="create and edit one uniquely named task",
        mechanism="repository refresh may replace the persisted local task state",
        consequence="the edited task title is absent after reopening",
        rationale=(
            "The source boundary and runtime journey make task persistence "
            "falsifiable with local evidence."
        ),
        required_evidence=(
            "terminal execution record",
            "runtime layout, screenshot, and log evidence",
            "agent and oracle identity",
        ),
        confidence=0.5,
        status="frozen",
        supporting_fact_ids=(
            "fact-task-repository",
            "fact-process-boundary",
            "fact-runtime-observation",
        ),
    )
    plan = AttackPlan(
        plan_id=f"plan-{lane_id}",
        target_id=target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        operator_id="operator-task-persistence-observation",
        trigger="enter the recorded task boundary once",
        observations=(
            "observe the edited title after navigation and process restoration",
        ),
        evidence_expectations=(
            "layout",
            "screenshot",
            "log output",
            "terminal execution identity",
        ),
        oracle="oracle-task-title-persistence-v1",
        abort_boundary="stop after the bounded terminal observation",
        claim_boundary=CLAIM_BOUNDARY,
        fixture_refs=("fixture:local-api35-emulator",),
        status="admitted",
    )
    source_path = lane_dir / "source-target.json"
    _write_json(source_path, target.to_dict())
    hypothesis_path = lane_dir / "risk-hypothesis.json"
    _write_json(hypothesis_path, hypothesis.to_dict())
    plan_path = lane_dir / "admitted-attack-plan.json"
    _write_json(plan_path, plan.to_dict())
    oracle_path = lane_dir / "oracle-contract.json"
    _write_json(
        oracle_path,
        {
            "schema_version": 1,
            "oracle_id": "oracle-task-title-persistence-v1",
            "correct_behavior": (
                "the uniquely edited task title remains visible after navigation, "
                "reopening, and the process boundary"
            ),
            "source_role_input": False,
        },
    )
    raw_artifacts = tuple(
        ImmutableArtifactRef(
            ref=ref,
            kind="raw-runtime-evidence",
            sha256=_sha256_path(lane_dir / ref),
        )
        for ref in row["raw_refs"]
    )
    context = FalsificationReviewContext(
        context_id=f"review-context-{lane_id}",
        target=target,
        source_refs=(
            ImmutableArtifactRef(
                ref="source-target.json",
                kind="source",
                sha256=_sha256_path(source_path),
            ),
        ),
        validated_fact_ids=hypothesis.supporting_fact_ids,
        hypothesis=hypothesis,
        admitted_attack_plan=plan,
        oracle_contract=ImmutableArtifactRef(
            ref="oracle-contract.json",
            kind="oracle-contract",
            sha256=_sha256_path(oracle_path),
        ),
        candidate_finding=row["finding"],
        execution_record=ImmutableArtifactRef(
            ref="execution-record.json",
            kind="execution-record",
            sha256=_sha256_path(lane_dir / "execution-record.json"),
        ),
        effective_identity=ImmutableArtifactRef(
            ref="effective-execution-identity.json",
            kind="effective-identity",
            sha256=_sha256_path(
                lane_dir / "effective-execution-identity.json"
            ),
        ),
        raw_evidence=raw_artifacts,
        control_evidence=(
            ImmutableArtifactRef(
                ref="peer-evidence-index.json",
                kind="peer-evidence-index",
                sha256=_sha256_path(peer_index),
            ),
        ),
        claim_boundary=CLAIM_BOUNDARY,
        production_invocation_id=str(
            row["identity"].get(
                "production_invocation_id",
                row["record"].get("attempt_id", "unavailable-production-invocation"),
            )
        ),
        production_provider_family="openai-codex-cli",
    )
    return context, target, hypothesis, plan


def _review_prompt(
    context: FalsificationReviewContext,
) -> str:
    refs = [
        item.ref
        for item in (
            *context.source_refs,
            context.oracle_contract,
            context.execution_record,
            context.effective_identity,
            *context.raw_evidence,
            *context.control_evidence,
        )
    ]
    return (
        "Independently challenge the candidate Finding in "
        "falsification-review-context.json. Work only from that context and "
        "the following checksum-bound files in the current directory; do not "
        "inspect parent directories or infer any source assignment:\n"
        + "\n".join(f"- {ref}" for ref in refs)
        + "\n\nAssess all six dimensions in this exact order: "
        + ", ".join(REVIEW_DIMENSIONS)
        + ". A dimension is supported only when the cited files support the "
        "candidate Finding against that challenge. Use only the listed refs in "
        "evidence_refs. If any dimension is challenged or inconclusive, add "
        "typed reasons whose codes match its reason_codes. Return only the JSON "
        "object required by the supplied output schema."
    )


def _review_input_audit(
    context: FalsificationReviewContext,
    prompt: str,
) -> dict[str, Any]:
    encoded = json.dumps(
        {"context": context.to_dict(), "prompt": prompt},
        ensure_ascii=False,
        sort_keys=True,
    )
    forbidden_fragments = {
        "role_assignment_control": '"role": "control"',
        "role_assignment_defect": '"role": "defect"',
        "external_first_input_path": str(DEFAULT_FIRST_INPUT),
        "external_second_input_path": str(DEFAULT_SECOND_INPUT),
        "expected_supported_label": '"expected_result": "supported"',
        "expected_rejected_label": '"expected_result": "rejected"',
    }
    found = [
        label for label, fragment in forbidden_fragments.items() if fragment in encoded
    ]
    return {
        "schema_version": 1,
        "status": "pass" if not found else "fail",
        "forbidden_disclosures": found,
        "context_sha256": context.context_sha256,
        "prompt_sha256": _sha256_bytes(prompt.encode("utf-8")),
        "auditor_mapping_persisted_before_review": False,
        "known_canary_role_disclosed": False if not found else None,
        "expected_result_disclosed": False if not found else None,
    }


def _run_review(
    row: Mapping[str, Any],
    peer: Mapping[str, Any],
) -> dict[str, Any]:
    lane_dir = Path(row["lane_dir"])
    peer_index = _copy_peer_evidence(row, peer)
    context, _, _, _ = _review_contract(row, peer_index)
    context_path = lane_dir / "falsification-review-context.json"
    _write_json(context_path, context.to_dict())
    prompt = _review_prompt(context)
    audit = _review_input_audit(context, prompt)
    _write_json(lane_dir / "falsification-review-input-audit.json", audit)
    if audit["status"] != "pass":
        raise M9RecoveryCanaryError("falsification review input leaked auditor data")
    review_artifacts = lane_dir / "review-invocation"
    provider = CodexCliProvider(
        workdir=lane_dir,
        model=None,
        timeout_seconds=900,
        artifact_dir=review_artifacts,
        role=FALSIFICATION_REVIEW_ROLE_ID,
        artifact_prefix="falsification-review-call",
        output_schema=REVIEW_SCHEMA,
    )
    completion = provider.complete(
        prompt,
        system=(
            "You are a clean-context falsification reviewer. You are separate "
            "from the production journey driver and semantic judge. You may "
            "challenge or block a candidate Finding, but never rewrite evidence."
        ),
    )
    raw_output = json.loads(completion.text)
    if len(provider.identity_receipts) != 1:
        raise M9RecoveryCanaryError(
            "falsification reviewer identity receipt is missing or duplicated"
        )
    native_identity_path = provider.identity_receipts[0]
    native_identity = _read_json(native_identity_path)
    _assert_default_receipt(native_identity)
    source = native_identity["effective_model_source"]
    invocation_id = f"{source['thread_id']}:{source['turn_id']}"
    if invocation_id == context.production_invocation_id:
        raise M9RecoveryCanaryError(
            "reviewer invocation duplicates the production invocation"
        )
    identity = FalsificationReviewerIdentity.capture(
        backend="codex_cli",
        requested_model=None,
        effective_model=native_identity["effective_model"],
        invocation_id=invocation_id,
        provider_family="openai-codex-cli",
        same_family_limitation=(
            "same provider family, but a separate read-only invocation, clean "
            "context, identity, prompt, output schema, and no production "
            "adjudication code path"
        ),
    )
    result = run_falsification_review(
        context,
        lambda _context: raw_output,
        identity,
    )
    if result.status != "complete" or result.review is None:
        raise M9RecoveryCanaryError(
            "falsification review was rejected: "
            + "; ".join(result.rejection_reasons)
        )
    reconciliation = reconcile_finding(row["finding"], result.review, context)
    payload = {
        "schema_version": 1,
        "clean_context_sha256": context.context_sha256,
        "input_audit": audit,
        "native_identity": {
            "ref": str(native_identity_path.relative_to(lane_dir)),
            "sha256": _sha256_path(native_identity_path),
            "requested_model": None,
            "selection_policy": "codex_cli_default",
            "model_override_present": False,
            "effective_model": native_identity["effective_model"],
        },
        "result": result.to_dict(),
        "reconciliation": reconciliation.to_dict(),
        "production_oracle_path_used": False,
    }
    _write_json(lane_dir / "falsification-review.json", payload)
    return {
        "status": result.status,
        "outcome": result.review.outcome,
        "context_sha256": context.context_sha256,
        "reviewer_identity_sha256": identity.identity_sha256,
        "requested_model": None,
        "effective_model": native_identity["effective_model"],
        "model_override_present": False,
        "separate_invocation": True,
    }


def _lane_chain_checks(row: Mapping[str, Any]) -> dict[str, bool]:
    lane_dir = Path(row["lane_dir"])
    reset = _read_json(lane_dir / "package-reset.json")
    device_input = _read_json(lane_dir / "device-input-setup.json")
    gate = _read_json(lane_dir / "live-validation-gate.json")
    provenance = _read_json(lane_dir / "execution-provenance.json")
    setup = _read_json(lane_dir / "runner-setup.json")
    verdict = row["verdict"]
    deployment = provenance.get("deployment", {})
    roles = provenance.get("roles", {})
    raw_inventory = _read_json(lane_dir / "raw-evidence-inventory.json")
    raw_refs = [
        item.get("ref")
        for item in raw_inventory.get("artifacts", [])
        if isinstance(item, Mapping)
    ]
    setup_operations = setup.get("operations", [])
    return {
        "package_reset": reset.get("status") in {"already_absent", "cleared"},
        "english_us_input_subtype": (
            device_input.get("status") == "passed"
            and isinstance(device_input.get("expected_subtype"), Mapping)
            and device_input["expected_subtype"].get("hash")
            == ENGLISH_US_INPUT_SUBTYPE
        ),
        "android_cli_install_deploy": (
            isinstance(deployment, Mapping)
            and isinstance(deployment.get("process"), Mapping)
            and deployment["process"].get("returncode") == 0
            and deployment["process"].get("args", [None, None])[:2]
            == ["android", "run"]
        ),
        "explicit_launch": any(
            isinstance(item, Mapping)
            and item.get("operation") == "explicit_launch"
            and item.get("returncode") == 0
            for item in setup_operations
        ),
        "live_validation": gate.get("status") == "passed",
        "codex_driver": (
            isinstance(roles, Mapping)
            and isinstance(roles.get("journey_driver"), Mapping)
            and roles["journey_driver"].get("status") == "invoked"
        ),
        "layout_evidence": any(
            isinstance(ref, str) and ref.endswith("/layout.json") for ref in raw_refs
        ),
        "screenshot_evidence": any(
            isinstance(ref, str) and ref.endswith("/screen.png") for ref in raw_refs
        ),
        "logcat_evidence": any(
            isinstance(ref, str) and ref.endswith("/logcat.txt") for ref in raw_refs
        ),
        "oracle_path": all(
            isinstance(verdict.get(level), Mapping) for level in ("l1", "l2")
        )
        and (
            isinstance(verdict.get("l3"), Mapping)
            or (
                isinstance(verdict.get("l1"), Mapping)
                and verdict["l1"].get("outcome") == "fail"
            )
            or (
                isinstance(verdict.get("l2"), Mapping)
                and verdict["l2"].get("outcome") == "fail"
            )
        ),
        "terminal_execution_record": row["accountable"],
        "default_model_identity": row["identity"].get("status") == "complete",
    }


def _reconcile_canary(
    rows: Sequence[Mapping[str, Any]],
    contradiction: Mapping[str, Any],
) -> dict[str, Any]:
    if len(rows) != 2 or {row["role"] for row in rows} != {"control", "defect"}:
        raise M9RecoveryCanaryError("R2 reconciliation requires one matched pair")
    defect = next(row for row in rows if row["role"] == "defect")
    control = next(row for row in rows if row["role"] == "control")
    chain_checks = {
        str(row["lane_id"]): dict(row["chain_checks"]) for row in rows
    }
    reviews_consistent = all(
        row["review"]["status"] == "complete"
        and row["review"]["outcome"] == "survived"
        and row["review"]["separate_invocation"] is True
        for row in rows
    )
    ready = bool(
        all(row["accountable"] for row in rows)
        and all(all(checks.values()) for checks in chain_checks.values())
        and defect["finding_conclusion"] == "supported"
        and control["finding_conclusion"] == "rejected"
        and reviews_consistent
        and contradiction.get("status") == "pass"
    )
    public_rows = []
    for row in rows:
        public_rows.append(
            {
                "lane_id": row["lane_id"],
                "accountable": row["accountable"],
                "finding_conclusion": row["finding_conclusion"],
                "duration_seconds": row["duration_seconds"],
                "run_spec_sha256": row["run_spec_sha256"],
                "review": row["review"],
                "chain_checks": row["chain_checks"],
            }
        )
    return {
        "schema_version": 1,
        "canary_result": (
            "ready_for_fresh_qualification_packet"
            if ready
            else "blocked_by_canary_evidence"
        ),
        "ready_for_r3": ready,
        "lanes": public_rows,
        "counts": {
            "lane_count": len(rows),
            "accountable": sum(bool(row["accountable"]) for row in rows),
            "expected_defect_supported": int(
                defect["finding_conclusion"] == "supported"
            ),
            "expected_control_rejected": int(
                control["finding_conclusion"] == "rejected"
            ),
            "independent_reviews_survived": sum(
                row["review"]["status"] == "complete"
                and row["review"]["outcome"] == "survived"
                for row in rows
            ),
        },
        "chain_checks": chain_checks,
        "contradiction_rejected_before_side_effect": (
            contradiction.get("status") == "pass"
        ),
        "non_holdout_canary": True,
        "formal_qualification_eligible": False,
        "formal_holdout_executed": False,
        "formal_denominator": False,
        "old_136_137_population_invoked": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "prohibited_interpretation": (
            "This result cannot support the M9 formal qualification conclusion."
        ),
    }


def _checksums(root: Path) -> None:
    entries = []
    for path in sorted(
        item
        for item in root.rglob("*")
        if item.is_file() and item.name != "checksums.sha256"
    ):
        entries.append(
            f"{_sha256_path(path)}  {path.relative_to(root).as_posix()}"
        )
    _write_text(root / "checksums.sha256", "\n".join(entries) + "\n")


def _finalize_failed_attempt(root: Path, error: BaseException) -> None:
    """Seal a failed create-only attempt without converting it into a result."""

    failure_path = root / "attempt-failure.json"
    if not failure_path.exists():
        _write_json(
            failure_path,
            {
                "schema_version": 1,
                "status": "terminal_failure",
                "error_type": type(error).__name__,
                "error_message": str(error),
                "ready_for_r3": False,
                "formal_qualification_eligible": False,
                "formal_denominator": False,
                "rerun_of_this_attempt_permitted": False,
            },
        )
    lane_root = root / "canary-artifacts"
    if lane_root.is_dir():
        for lane_dir in sorted(path for path in lane_root.iterdir() if path.is_dir()):
            if not (lane_dir / "checksums.sha256").exists():
                _checksums(lane_dir)
    if not (root / "checksums.sha256").exists():
        _checksums(root)


def execute_canary(
    *,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    first_input: Path = DEFAULT_FIRST_INPUT,
    second_input: Path = DEFAULT_SECOND_INPUT,
    device: str = "emulator-5554",
) -> dict[str, Any]:
    """Execute one numbered, non-formal R2 canary attempt."""

    root = artifact_root.resolve()
    if root.exists():
        raise M9RecoveryCanaryError(f"canary attempt already exists: {root}")
    root.mkdir(parents=True)
    started = time.monotonic()
    contradiction = _contradiction_gate(root)
    _write_json(
        root / "canary-declaration.json",
        {
            "schema_version": 1,
            "issue": 150,
            "stage": "M9-R2",
            "non_holdout_canary": True,
            "formal_qualification_eligible": False,
            "formal_denominator": False,
            "old_136_137_population_invoked": False,
            "requested_model_selection": "codex_cli_default",
            "requested_model_override": None,
            "device": device,
            "claim_boundary": CLAIM_BOUNDARY,
        },
    )
    variants = _variants(first_input, second_input)
    input_audits = {
        variant.lane_id: _inspect_source_input(variant) for variant in variants
    }
    runtime_rows = []
    for variant in variants:
        worktree, fixture_receipt = _prepare_fixture(variant, fixture_root.resolve())
        runtime_rows.append(
            _execute_runtime_lane(
                root,
                variant,
                worktree,
                fixture_receipt,
                device=device,
            )
        )
    for index, row in enumerate(runtime_rows):
        peer = runtime_rows[1 - index]
        row["review"] = _run_review(row, peer)
        row["chain_checks"] = _lane_chain_checks(row)
        _write_json(
            Path(row["lane_dir"]) / "lane-result.json",
            {
                "schema_version": 1,
                "lane_id": row["lane_id"],
                "accountable": row["accountable"],
                "finding_conclusion": row["finding_conclusion"],
                "review": row["review"],
                "chain_checks": row["chain_checks"],
                "non_holdout_canary": True,
                "formal_qualification_eligible": False,
            },
        )
        _checksums(Path(row["lane_dir"]))
    _write_json(
        root / "auditor-mapping-release.json",
        {
            "schema_version": 1,
            "released_after_both_reviews": True,
            "assignments": [
                {"lane_id": row["lane_id"], "role": row["role"]}
                for row in runtime_rows
            ],
            "review_contexts_contained_mapping": False,
        },
    )
    _write_json(
        root / "auditor-source-input-binding.json",
        {
            "schema_version": 1,
            "released_after_both_reviews": True,
            "inputs": [
                {
                    "lane_id": variant.lane_id,
                    "role": variant.role,
                    **input_audits[variant.lane_id],
                }
                for variant in variants
            ],
        },
    )
    reconciliation = _reconcile_canary(runtime_rows, contradiction)
    _write_json(root / "canary-reconciliation.json", reconciliation)
    _write_json(
        root / "canary-execution-summary.json",
        {
            "schema_version": 1,
            "duration_seconds": round(time.monotonic() - started, 3),
            "attempt_count_in_this_invocation": 1,
            "troubleshooting_retries_in_this_invocation": 0,
            "replacement_count": 0,
            "result": reconciliation["canary_result"],
            "ready_for_r3": reconciliation["ready_for_r3"],
            "non_holdout_canary": True,
            "formal_qualification_eligible": False,
            "artifact_root": str(root),
        },
    )
    _checksums(root)
    return reconciliation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--first-input", type=Path, default=DEFAULT_FIRST_INPUT)
    parser.add_argument("--second-input", type=Path, default=DEFAULT_SECOND_INPUT)
    parser.add_argument("--device", default="emulator-5554")
    args = parser.parse_args(argv)
    try:
        result = execute_canary(
            artifact_root=args.artifact_root,
            fixture_root=args.fixture_root,
            first_input=args.first_input,
            second_input=args.second_input,
            device=args.device,
        )
    except Exception as error:
        root = args.artifact_root.resolve()
        if root.is_dir():
            _finalize_failed_attempt(root, error)
        raise
    print(
        json.dumps(
            {
                "canary_result": result["canary_result"],
                "ready_for_r3": result["ready_for_r3"],
                "accountable": result["counts"]["accountable"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["ready_for_r3"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
