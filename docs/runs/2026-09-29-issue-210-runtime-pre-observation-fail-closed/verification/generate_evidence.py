"""Regenerate the issue-210 pre-observation fail-closed evidence.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python \
      docs/runs/2026-09-29-issue-210-runtime-pre-observation-fail-closed/\
verification/generate_evidence.py

The script drives the public lane seam (``execute_runtime_attempt``) once per
matrix case on the recording device with a pinned clock, re-runs the
independent verifier (``verify_runtime_attempt``) over each committed attempt
root, and rewrites ``pre-observation-matrix.json``.  Every case asserts the
reason, scope, and terminal phase it is expected to produce, so the committed
JSON can never silently drift from the frozen contract.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

from aiverify.bench import runtime_attempt as ra
from aiverify.runner.deterministic_backend import load_deterministic_driver_plan
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    RuntimePreparationReceipt,
    _canonical_bytes,
    _identity,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = REPO_ROOT / "docs/runs/2026-09-29-issue-210-runtime-pre-observation-fail-closed"
VERIFICATION = RUN_ROOT / "verification"
LANE_ROOT = (
    REPO_ROOT
    / "bench/runtime-calibration/opencalc-input-save-enabled-v1/runtime/lanes/lane-01"
)
LANE_ID = "ocrc-v1-lane-01"
RECORDING_SERIAL = "recording-device"
SEALED_APK_BYTES = b"sealed opencalc runtime apk bytes"
BASELINE_HEAD = "e2aee56"

CASES: tuple[tuple[str, str, str, str, ra.RecordingDevicePolicy, tuple[str, ...], bool], ...] = (
    (
        "session-probe-refused",
        "device_session_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "device-session",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"probe_session"})),
        (),
        False,
    ),
    (
        "session-serial-drift",
        "device_session_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "device-session",
        ra.RecordingDevicePolicy(reported_serial="emulator-9999"),
        (),
        False,
    ),
    (
        "session-required-field-missing",
        "device_session_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "device-session",
        ra.RecordingDevicePolicy(),
        ("boot_id",),
        False,
    ),
    (
        "session-settings-missing",
        "device_session_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "device-session",
        ra.RecordingDevicePolicy(),
        ("default_input_method",),
        False,
    ),
    (
        "sealed-apk-drifted-after-admission",
        "sealed_apk_bytes_drifted",
        ra.FAILURE_SCOPE_SHARED,
        "deploy-sealed-apk",
        ra.RecordingDevicePolicy(),
        (),
        True,
    ),
    (
        "deployment-refused",
        "sealed_apk_deployment_failed",
        ra.FAILURE_SCOPE_SHARED,
        "deploy-sealed-apk",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"deploy_apk"})),
        (),
        False,
    ),
    (
        "installed-read-refused",
        "sealed_apk_deployment_failed",
        ra.FAILURE_SCOPE_SHARED,
        "deploy-sealed-apk",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"read_installed_apk"})),
        (),
        False,
    ),
    (
        "installed-bytes-drifted",
        "sealed_apk_bytes_drifted",
        ra.FAILURE_SCOPE_SHARED,
        "deploy-sealed-apk",
        ra.RecordingDevicePolicy(installed_digest_override="f" * 64),
        (),
        False,
    ),
    (
        "package-clear-refused",
        "attempt_setup_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "attempt-setup",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"clear_package_data"})),
        (),
        False,
    ),
    (
        "package-clear-contradicted",
        "attempt_setup_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "attempt-setup",
        ra.RecordingDevicePolicy(clear_output="Failure"),
        (),
        False,
    ),
    (
        "target-process-residual",
        "attempt_setup_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "attempt-setup",
        ra.RecordingDevicePolicy(residual_target_process=True),
        (),
        False,
    ),
    (
        "setting-write-refused",
        "attempt_setup_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "attempt-setup",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"write_rotation_setting"})),
        (),
        False,
    ),
    (
        "rotation-read-refused",
        "attempt_setup_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "attempt-setup",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"read_rotation_state"})),
        (),
        False,
    ),
    (
        "portrait-contradicted",
        "attempt_setup_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "attempt-setup",
        ra.RecordingDevicePolicy(reported_rotation=ra.LANDSCAPE_ROTATION),
        (),
        False,
    ),
    (
        "log-clear-refused",
        "target_log_window_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "open-target-log-window",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"clear_log_buffers"})),
        (),
        False,
    ),
    (
        "start-marker-refused",
        "target_log_window_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "open-target-log-window",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"write_log_marker"})),
        (),
        False,
    ),
    (
        "canonical-launch-refused",
        "canonical_launch_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "canonical-launch",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"canonical_launch"})),
        (),
        False,
    ),
    (
        "foreground-read-refused",
        "canonical_launch_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "canonical-launch",
        ra.RecordingDevicePolicy(fail_operations=frozenset({"read_foreground_state"})),
        (),
        False,
    ),
    (
        "foreground-component-contradicted",
        "canonical_launch_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "canonical-launch",
        ra.RecordingDevicePolicy(reported_foreground_component="com.other/.Main"),
        (),
        False,
    ),
)


class _SealedApkDriftDevice:
    """Recording-device proxy that rewrites the sealed APK after admission."""

    def __init__(self, inner: object, *, apk_path: Path) -> None:
        self._inner = inner
        self._apk_path = apk_path

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def probe_session(self) -> object:
        receipt = self._inner.probe_session()
        self._apk_path.chmod(0o644)
        self._apk_path.write_bytes(SEALED_APK_BYTES + b"!")
        self._apk_path.chmod(0o444)
        return receipt


def _preparation_receipt(apk_path: Path) -> RuntimePreparationReceipt:
    payload = apk_path.read_bytes()
    document: dict[str, object] = {
        "schema_version": 1,
        "status": "prepared",
        "prepared": True,
        "rejection_code": None,
        "claim_boundary": "local_source_build_preparation_only",
        "build": {"returncode": 0, "retry": False, "test_substitutes": True},
        "sealed_apk": {
            "path": str(apk_path.resolve()),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "mode": "0444",
            "regular": True,
            "symlink": False,
            "hard_links": 1,
        },
        "runtime_effects": {
            "shell": False,
            "device": False,
            "android_deployment": False,
            "execution_record": False,
            "agent_or_model": False,
        },
    }
    document["receipt_identity_sha256"] = _identity(document)
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=True,
        receipt_bytes=encoded,
        receipt_sha256=hashlib.sha256(encoded).hexdigest(),
        rejection_code=None,
    )


def _lane_inputs() -> tuple[RunSpec, object]:
    spec = load_run_spec(LANE_ROOT / "run-spec.yaml")
    plan = load_deterministic_driver_plan(
        LANE_ROOT / "driver-plan.json",
        serialized_run_spec=(LANE_ROOT / "run-spec.yaml").read_bytes(),
        run_spec_path=LANE_ROOT / "run-spec.yaml",
        expected_actions=tuple(spec.scenario.user_actions),
    )
    return spec, plan


def _session_fields_without(spec: RunSpec, *drop: str) -> dict[str, object]:
    fields = dict(
        ra._session_fields(
            serial=RECORDING_SERIAL, package=spec.package, activity=spec.activity
        )
    )
    for name in drop:
        if name in ra.SESSION_IDENTITY_SETTINGS:
            settings = dict(fields["settings"])
            settings.pop(name)
            fields["settings"] = settings
            continue
        fields.pop(name)
    return fields


def _policy_document(policy: ra.RecordingDevicePolicy) -> dict[str, object]:
    document: dict[str, object] = {}
    for name, value in dataclasses.asdict(policy).items():
        document[name] = sorted(value) if isinstance(value, (set, frozenset)) else value
    return document


def _run_case(
    label: str,
    reason: str,
    scope: str,
    phase: str,
    policy: ra.RecordingDevicePolicy,
    session_drop: tuple[str, ...],
    drift: bool,
) -> dict[str, object]:
    attempt_root = VERIFICATION / "attempts" / label
    handoff_root = VERIFICATION / "handoffs" / label
    for path in (attempt_root, handoff_root):
        shutil.rmtree(path, ignore_errors=True)
    handoff_root.mkdir(parents=True, exist_ok=True)
    apk_path = handoff_root / "sealed-runtime.apk"
    apk_path.write_bytes(SEALED_APK_BYTES)
    apk_path.chmod(0o444)

    spec, plan = _lane_inputs()
    inner = ra.RecordingRuntimeDevice(
        policy=policy,
        package=spec.package,
        activity=spec.activity,
        session_fields=(
            _session_fields_without(spec, *session_drop) if session_drop else None
        ),
    )
    device: object = _SealedApkDriftDevice(inner, apk_path=apk_path) if drift else inner
    request = ra.RuntimeAttemptRequest(
        lane_id=LANE_ID,
        run_spec=spec,
        driver_plan=plan,
        setup_plan=ra.RuntimeAttemptSetupPlan(
            family_id=plan.family_id,
            family_version=plan.family_version,
            package=spec.package,
        ),
        preparation_receipt=_preparation_receipt(apk_path),
        device=device,
        output_root=attempt_root,
        started_at="2026-09-29T00:00:00Z",
        clock=lambda: 1_000.0,
        sleeper=lambda _seconds: None,
    )

    outcome = ra.execute_runtime_attempt(request)
    verified = ra.verify_runtime_attempt(attempt_root)
    record = load_execution_record(attempt_root / ra.RECORD_FILENAME)
    failure = outcome.document["failure"]

    assert outcome.terminal_state == ra.NON_ACCOUNTABLE, label
    assert outcome.reason == reason, (label, outcome.reason, reason)
    assert failure["scope"] == scope, (label, failure["scope"], scope)
    assert failure["phase"] == phase, (label, failure["phase"], phase)
    assert verified["verified"] is True, label
    assert "oracles" not in outcome.components, label
    assert record["process_outcome"] == {"exit_code": 2}, label
    assert record["lifecycle_state"] == "failed", label

    return {
        "label": label,
        "expected": {"reason": reason, "scope": scope, "phase": phase},
        "policy": _policy_document(policy),
        "session_drop": list(session_drop),
        "drifted_sealed_apk": drift,
        "terminal_state": outcome.terminal_state,
        "reason": outcome.reason,
        "verdict": outcome.verdict,
        "failure": dict(failure),
        "phases": [
            entry["phase"] for entry in outcome.document["phases"]
        ],
        "phase_statuses": {
            entry["phase"]: entry["status"] for entry in outcome.document["phases"]
        },
        "components": sorted(outcome.components),
        "dispatched_mutations": [
            operation for operation, _vector in device.mutation_operations()
        ],
        "dispatched_vectors": [
            list(vector) for _operation, vector in device.mutation_operations()
        ],
        "markers": list(device.markers()),
        "operation_counts": dict(device.operation_counts()),
        "record": {
            "lifecycle_state": record["lifecycle_state"],
            "process_outcome": record["process_outcome"],
            "execution": record["execution"],
            "phase_errors": record["phase_errors"],
            "attempt_artifacts": record["evidence_refs"]["attempt_artifacts"],
            "has_attempt_receipt_path": (
                "attempt_receipt_path" in record["evidence_refs"]
            ),
        },
        "verification": {
            "verified": verified["verified"],
            "checks": verified["checks"],
            "recomputed": verified["recomputed"],
        },
        "receipt": {
            "path": f"attempts/{label}/attempt-receipt.json",
            "bytes": len(outcome.payload),
            "sha256": outcome.sha256,
        },
    }


def main() -> None:
    (VERIFICATION / "attempts").mkdir(parents=True, exist_ok=True)
    rows = [_run_case(*case) for case in CASES]
    document = {
        "schema_version": 1,
        "seam": ra.SEAM,
        "claim_boundary": ra.CLAIM_BOUNDARY,
        "baseline_head": BASELINE_HEAD,
        "evidence_class": "recorded_simulation",
        "lane_id": LANE_ID,
        "device_serial": RECORDING_SERIAL,
        "frozen_phases": list(ra.FROZEN_PHASES),
        "failure_scopes": dict(ra.FAILURE_SCOPES),
        "case_count": len(rows),
        "cases": rows,
    }
    target = VERIFICATION / "pre-observation-matrix.json"
    target.write_text(json.dumps(document, indent=2) + "\n")
    print(f"wrote {target.relative_to(REPO_ROOT)} with {len(rows)} cases")


if __name__ == "__main__":
    main()
