"""Recording-only, exactly-once execution of an admitted four-lane runtime family.

This stage preserves opaque lane observations, never computes a calibration state,
and does not provide a real device or model backend.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from aiverify.bench import runtime_attempt, runtime_calibration, runtime_family_preparation, runtime_mapping
from aiverify.runner.deterministic_backend import load_deterministic_driver_plan
from aiverify.runner.run_spec import load_run_spec
from aiverify.runtime_preparation import RuntimePreparationReceipt, _canonical_bytes as preparation_bytes

STAGE = "execute-family"
CLAIM_BOUNDARY = "recorded_simulation_family_execution_only"
LANE_ORDER = runtime_mapping.FROZEN_LANE_ORDER
_ALLOWED_OBSERVATIONS = frozenset({
    "save_enabled", "inject_target_crash", "restart_target_process",
    "residual_target_process", "boundary_layout_fault", "post_event_layout_fault",
    "log_dump_fault", "lifecycle_fault", "session_drift_fault", "fail_operations",
    "source_health_fault", "tool_health_fault", "log_health_fault",
})


class RuntimeFamilyExecutionError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bytes(document: Mapping[str, object]) -> bytes:
    return runtime_calibration.canonical_json_bytes(document)


def _stamp(document: dict[str, object], key: str = "identity_sha256") -> dict[str, object]:
    document[key] = runtime_calibration.canonical_sha256(document)
    return document


def _write(path: Path, document: Mapping[str, object]) -> str:
    if path.exists() or path.is_symlink():
        raise RuntimeFamilyExecutionError("family_stage_receipt_already_exists")
    payload = _bytes(document)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RuntimeFamilyExecutionError("family_stage_receipt_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
    return _sha(payload)


def _inventory(root: Path) -> list[dict[str, object]]:
    """Inventory only actual regular files, including partial abandoned attempts."""
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeFamilyExecutionError("family_artifact_symlink")
        if path.is_file():
            data = path.read_bytes()
            entries.append({"path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": _sha(data)})
    return entries


def _probe(device: runtime_attempt.RecordingRuntimeDevice, reference: Mapping[str, object]) -> dict[str, object]:
    try:
        observed = device.probe_session()
        fields = dict(observed.fields)
        settings = fields.get("settings")
        missing = [name for name in runtime_attempt.SESSION_REQUIRED_FIELDS if not fields.get(name)]
        missing += [
            f"settings.{name}" for name in runtime_attempt.SESSION_IDENTITY_SETTINGS
            if not isinstance(settings, Mapping) or name not in settings
        ]
        drift = runtime_attempt.session_identity_drift(reference, fields)
        expected_outputs = tuple(
            f"{settings.get(name[len('settings.'):], '')}\n"
            if name.startswith("settings.") and isinstance(settings, Mapping)
            else runtime_attempt._recorded_probe_output(name, fields)
            for _, name in runtime_attempt.session_probe_plan(device.serial)
        )
        checks = {
            "raw_outputs_match_fields": observed.outputs == expected_outputs,
            "probe_success": all(code == 0 for code in observed.returncodes),
            "probe_vectors_complete": observed.operation == "probe_session" and observed.commands == runtime_attempt.session_probe_vectors(device.serial) and len(observed.commands) == len(observed.returncodes) == len(observed.outputs),
            "serial_matches": fields.get("serial") == device.serial,
            "identity_complete": not missing,
            "reference_unchanged": not drift,
        }
        return {
            "closed": all(checks.values()), "checks": checks,
            "missing": missing, "drifted_fields": drift,
            "probe": observed.to_dict(), "fields": fields,
            "evidence_class": "recorded_simulation",
        }
    except Exception as error:  # noqa: BLE001 - preserve refusal without retry
        return {"closed": False, "error": getattr(error, "code", type(error).__name__), "evidence_class": "recorded_simulation"}


@dataclass(frozen=True)
class RecordingLaneObservation:
    device: runtime_attempt.RecordingDevicePolicy = field(default_factory=runtime_attempt.RecordingDevicePolicy)
    source_health_fault: bool = False
    tool_health_fault: bool = False
    log_health_fault: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.device, runtime_attempt.RecordingDevicePolicy):
            raise RuntimeFamilyExecutionError("family_observation_invalid")
        for key in ("source_health_fault", "tool_health_fault", "log_health_fault"):
            if type(getattr(self, key)) is not bool:
                raise RuntimeFamilyExecutionError("family_observation_invalid")


def _policy(value: Mapping[str, object]) -> RecordingLaneObservation:
    if set(value) - _ALLOWED_OBSERVATIONS:
        raise RuntimeFamilyExecutionError("family_observation_fields_invalid")
    for key in ("save_enabled", "inject_target_crash", "restart_target_process", "residual_target_process", "source_health_fault", "tool_health_fault", "log_health_fault"):
        if key in value and type(value[key]) is not bool:
            raise RuntimeFamilyExecutionError("family_observation_invalid")
    operations = value.get("fail_operations", [])
    if not isinstance(operations, list) or any(not isinstance(op, str) for op in operations):
        raise RuntimeFamilyExecutionError("family_observation_invalid")
    if set(operations) - set(runtime_attempt.EXPECTED_DEVICE_MUTATION_COUNTS) - set(runtime_attempt.EXPECTED_DEVICE_READ_COUNTS) - {"read_layout", "read_foreground_state", "tap"}:
        raise RuntimeFamilyExecutionError("family_observation_invalid")
    try:
        return RecordingLaneObservation(
            device=runtime_attempt.RecordingDevicePolicy(
                **{key: value[key] for key in (
                    "save_enabled", "inject_target_crash", "restart_target_process", "residual_target_process",
                    "boundary_layout_fault", "post_event_layout_fault", "log_dump_fault",
                    "lifecycle_fault", "session_drift_fault",
                ) if key in value},
                fail_operations=frozenset(operations),
            ),
            source_health_fault=value.get("source_health_fault", False),
            tool_health_fault=value.get("tool_health_fault", False),
            log_health_fault=value.get("log_health_fault", False),
        )
    except (TypeError, ValueError) as error:
        raise RuntimeFamilyExecutionError("family_observation_invalid") from error


def load_recording_observations(path: str | Path) -> tuple[RecordingLaneObservation, ...]:
    """Parse a bounded opaque policy; variant names and expected verdicts are forbidden."""
    raw = Path(path)
    try:
        document = json.loads(raw.read_bytes())
        if not isinstance(document, dict) or set(document) != {"schema_version", "evidence_class", "lanes"}:
            raise RuntimeFamilyExecutionError("family_observation_config_invalid")
        if document["schema_version"] != 1 or document["evidence_class"] != "recorded_simulation":
            raise RuntimeFamilyExecutionError("family_observation_config_invalid")
        lanes = document["lanes"]
        if not isinstance(lanes, list) or len(lanes) != 4 or any(not isinstance(row, dict) for row in lanes):
            raise RuntimeFamilyExecutionError("family_lane_order_mismatch")
        if tuple(row.get("lane_id") for row in lanes) != LANE_ORDER:
            raise RuntimeFamilyExecutionError("family_lane_order_mismatch")
        if any(set(row) != {"lane_id", "observations"} or not isinstance(row["observations"], dict) for row in lanes):
            raise RuntimeFamilyExecutionError("family_observation_config_invalid")
        return tuple(_policy(row["observations"]) for row in lanes)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeFamilyExecutionError("family_observation_config_unavailable") from error


@dataclass
class RecordingRuntimeFamilySession:
    """One explicit simulated boot; lane adapters carry forward actual device state."""

    serial: str = "recording-device"
    started: bool = False
    stopped: bool = False
    state: dict[str, object] | None = None
    last_device: runtime_attempt.RecordingRuntimeDevice | None = None
    lifecycle: list[dict[str, object]] = field(default_factory=list)
    source_sha256: str | None = None
    tool_version: str | None = None
    log_capture_fault: bool = False

    def start(self, package: str, activity: str) -> runtime_attempt.RecordingRuntimeDevice:
        if self.started or self.stopped or self.state is not None or self.last_device is not None or self.lifecycle:
            raise RuntimeFamilyExecutionError("family_session_already_exists")
        device = runtime_attempt.RecordingRuntimeDevice(
            policy=runtime_attempt.RecordingDevicePolicy(serial=self.serial),
            package=package, activity=activity,
        )
        self.started = True
        self.last_device = device
        self.state = device.session_state()
        self.lifecycle.append({
            "operation": "recording_cold_start", "command": ["recording-session", "start", self.serial],
            "returncode": 0, "stdout": f"started {self.serial}\n", "stderr": "",
            "status": "ok", "evidence_class": "recorded_simulation",
        })
        return device

    def adapter(self, policy: runtime_attempt.RecordingDevicePolicy, package: str, activity: str) -> runtime_attempt.RecordingRuntimeDevice:
        if not self.started or self.stopped or self.state is None:
            raise RuntimeFamilyExecutionError("family_session_unavailable")
        device = runtime_attempt.RecordingRuntimeDevice(
            policy=replace(policy, serial=self.serial), package=package, activity=activity, session_state=self.state,
        )
        self.last_device = device
        return device

    def checkpoint(self) -> None:
        if self.last_device is not None:
            self.state = self.last_device.session_state()

    def probe_dependency(self, name: str, reference: str) -> dict[str, object]:
        """Observe simulated dependency identity, not a host source/tool probe."""
        observed = self.source_sha256 if name == "source" else self.tool_version
        return {
            "closed": observed == reference,
            "operation": f"recording_{name}_health_probe",
            "command": ["recording-session", "probe", name, self.serial],
            "returncode": 0, "stdout": f"{observed}\n", "stderr": "",
            "reference": reference, "observed": observed,
            "evidence_class": "recorded_simulation",
            "claim_boundary": "simulated_dependency_identity_only",
        }

    def stop(self) -> dict[str, object]:
        if not self.started or self.stopped:
            raise RuntimeFamilyExecutionError("family_teardown_invalid")
        self.stopped = True
        receipt = {
            "operation": "recording_cold_stop", "command": ["recording-session", "stop", self.serial],
            "returncode": 0, "stdout": f"stopped {self.serial}\n", "stderr": "",
            "status": "ok", "evidence_class": "recorded_simulation",
        }
        self.lifecycle.append(receipt)
        return receipt


@dataclass(frozen=True)
class RuntimeFamilyExecutionReceipt:
    output_root: Path
    accepted: bool
    document: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.document)


def execute_runtime_family(
    *, candidate_root: str | Path, predecessor_root: str | Path,
    output_root: str | Path, observations: Sequence[RecordingLaneObservation],
    session: RecordingRuntimeFamilySession | None = None,
) -> RuntimeFamilyExecutionReceipt:
    """Admit exact prepared bytes, then execute four opaque lanes in one session."""
    candidate_path = Path(candidate_root).expanduser().resolve()
    predecessor = Path(predecessor_root).expanduser().resolve()
    raw_output = Path(output_root).expanduser()
    if raw_output.is_symlink():
        raise RuntimeFamilyExecutionError("family_output_root_symlink")
    output = raw_output.resolve()
    if output == candidate_path or output == predecessor or output in candidate_path.parents or output in predecessor.parents or candidate_path in output.parents or predecessor in output.parents:
        raise RuntimeFamilyExecutionError("family_output_root_location_invalid")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RuntimeFamilyExecutionError("family_output_root_not_empty")
    if session is not None and (session.started or session.stopped or session.state is not None or session.last_device is not None or session.lifecycle or session.source_sha256 is not None or session.tool_version is not None or session.log_capture_fault):
        raise RuntimeFamilyExecutionError("family_session_already_exists")
    if len(observations) != 4 or any(not isinstance(item, RecordingLaneObservation) for item in observations):
        raise RuntimeFamilyExecutionError("family_observations_invalid")
    try:
        candidate = runtime_calibration.verify_candidate_inputs(candidate_path)
        prepared = runtime_family_preparation.load_runtime_family_preparation(predecessor)
        runtime_family_preparation.verify_runtime_family_preparation(
            prepared, candidate_root=candidate_path,
        )
        if not prepared.accepted or runtime_family_preparation.stage_status(predecessor) != "accepted" or prepared.output_root != predecessor:
            raise RuntimeFamilyExecutionError("family_predecessor_not_accepted")
        if prepared.candidate_root != candidate.root or prepared.lane_ids != LANE_ORDER or any(row.status != "prepared" for row in prepared.rows):
            raise RuntimeFamilyExecutionError("family_predecessor_identity_mismatch")
        prep_receipts: list[RuntimePreparationReceipt] = []
        lane_inputs = []
        for index, row in enumerate(prepared.rows, start=1):
            lane_root = candidate.root / "runtime" / "lanes" / f"lane-{index:02d}"
            spec_path = lane_root / "run-spec.yaml"
            spec = load_run_spec(spec_path)
            plan = load_deterministic_driver_plan(
                lane_root / "driver-plan.json", serialized_run_spec=spec_path.read_bytes(),
                run_spec_path=spec_path, expected_actions=tuple(spec.scenario.user_actions),
            )
            projection = json.loads((lane_root / "projection.json").read_bytes())
            setup = runtime_attempt.RuntimeAttemptSetupPlan.from_document(
                projection["setup_plan"], family_id=plan.family_id,
                family_version=plan.family_version, package=spec.package,
            )
            if plan.lane_id != row.lane_id or projection["lane_id"] != row.lane_id:
                raise RuntimeFamilyExecutionError("family_lane_order_mismatch")
            raw_receipts = [entry for entry in row.artifacts if entry.get("kind") == "raw_preparation_receipt"]
            if len(raw_receipts) != 1:
                raise RuntimeFamilyExecutionError("family_preparation_raw_receipt_missing")
            raw_path = Path(str(raw_receipts[0]["path"]))
            receipt_bytes = raw_path.read_bytes()
            if preparation_bytes(json.loads(receipt_bytes)) != receipt_bytes or json.loads(receipt_bytes) != row.preparation_receipt:
                raise RuntimeFamilyExecutionError("family_preparation_raw_receipt_drifted")
            prep_receipt = RuntimePreparationReceipt(
                prepared=True, receipt_bytes=receipt_bytes, receipt_sha256=_sha(receipt_bytes), rejection_code=None,
            )
            if not runtime_attempt.runtime_preparation_uses_test_substitutes(prep_receipt):
                raise RuntimeFamilyExecutionError("family_recording_requires_test_substitutes")
            prep_receipts.append(prep_receipt)
            lane_inputs.append((spec, plan, setup))
        terminal_bytes = (predecessor / "stage-terminal.json").read_bytes()
        preparation_bytes_on_disk = (predecessor / runtime_family_preparation.RUNTIME_FAMILY_PREPARATION_FILENAME).read_bytes()
    except RuntimeFamilyExecutionError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        raise RuntimeFamilyExecutionError("family_predecessor_invalid") from error
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise RuntimeFamilyExecutionError("family_output_root_unavailable") from error
    if any(output.iterdir()):
        raise RuntimeFamilyExecutionError("family_output_root_not_empty")
    selected = session if session is not None else RecordingRuntimeFamilySession()
    source_reference = runtime_calibration.canonical_sha256([
        receipt.receipt["source"] for receipt in prep_receipts
    ])
    selected.source_sha256 = source_reference
    selected.tool_version = None
    started_at = datetime.now(UTC).isoformat()
    start = _stamp({
        "schema_version": 1, "stage": STAGE, "status": "started",
        "claim_boundary": CLAIM_BOUNDARY, "evidence_class": "recorded_simulation",
        "candidate_root": str(candidate.root), "candidate_identity_sha256": candidate.candidate_identity_sha256,
        "predecessor_root": str(predecessor), "predecessor_terminal_sha256": _sha(terminal_bytes),
        "preparation_receipt_sha256": _sha(preparation_bytes_on_disk),
        "lane_ids": list(LANE_ORDER), "output_root": str(output), "started_at": started_at,
        "invocations": {"model_calls": 0, "retries": 0, "replacements": 0},
    })
    start_sha = _write(output / "stage-start.json", start)
    rows: list[dict[str, object]] = []
    health: list[dict[str, object]] = []
    abort: str | None = None
    teardown: dict[str, object] = {"status": "not_started", "evidence_class": "recorded_simulation"}
    reference: Mapping[str, object] = {}
    session_probe: dict[str, object] | None = None
    abandoned = False
    try:
        try:
            first_spec = lane_inputs[0][0]
            bootstrap = selected.start(first_spec.package, first_spec.activity)
            # Family probes are outside each lane's exactly-once operation budget.
            session_probe = _probe(bootstrap, bootstrap.session_state()["session_fields"])
            reference = session_probe.get("fields", {})
            _write(output / "session-start.json", _stamp({
                "lifecycle": list(selected.lifecycle), "probe": session_probe,
                "source_reference_sha256": source_reference,
                "evidence_class": "recorded_simulation",
            }))
            selected.tool_version = str(reference.get("android_cli_version", ""))
            if not session_probe["closed"]:
                abort = "family_session_identity_unavailable"
            selected.checkpoint()
            for index, lane_id in enumerate(LANE_ORDER):
                if abort is not None:
                    rows.append({"lane_id": lane_id, "status": "not_attempted_due_to_family_abort"})
                    continue
                spec, plan, setup = lane_inputs[index]
                device = selected.adapter(observations[index].device, spec.package, spec.activity)
                before = _probe(device, reference)
                health.append({"lane_id": lane_id, "boundary": "before", "session": before})
                selected.checkpoint()
                if not before["closed"]:
                    abort = "family_session_identity_drifted"
                    rows.append({"lane_id": lane_id, "status": "not_attempted_due_to_family_abort"})
                    continue
                # Fresh adapter isolates attempt-local operation counters/probe ordinals.
                device = selected.adapter(observations[index].device, spec.package, spec.activity)
                lane_output = output / "lanes" / f"lane-{index + 1:02d}"
                try:
                    attempt = runtime_attempt.execute_runtime_attempt(runtime_attempt.RuntimeAttemptRequest(
                        lane_id=lane_id, run_spec=spec, driver_plan=plan, setup_plan=setup,
                        preparation_receipt=prep_receipts[index], device=device, output_root=lane_output,
                        sleeper=lambda _seconds: None,
                    ))
                    selected.checkpoint()
                    row = {
                        "lane_id": lane_id, "status": attempt.terminal_state,
                        "attempt_id": attempt.attempt_id, "receipt_path": str(attempt.path),
                        "receipt_sha256": attempt.sha256,
                        "record_path": str(attempt.execution_record_path),
                        "record_sha256": None,
                        "reason": attempt.reason,
                        "failure_scope": runtime_attempt.failure_scope(attempt.reason) if attempt.reason else None,
                    }
                    rows.append(row)
                    row["record_sha256"] = _sha(attempt.execution_record_path.read_bytes())
                    verified = runtime_attempt.verify_runtime_attempt(lane_output)
                    if verified["receipt_sha256"] != attempt.sha256 or verified["lane_id"] != lane_id:
                        raise RuntimeFamilyExecutionError("family_attempt_verification_failed")
                    after = _probe(device, reference)
                    selected.checkpoint()
                    health.append({"lane_id": lane_id, "boundary": "after", "session": after})
                    if not after["closed"]:
                        abort = "family_session_identity_drifted"
                    elif not attempt.accountable_concluded:
                        if runtime_attempt.failure_scope(attempt.reason) != runtime_attempt.FAILURE_SCOPE_LANE_LOCAL:
                            abort = attempt.reason or "family_failure_scope_unknown"
                        else:
                            # Independently recheck each shared dependency, never a caller-provided healthy flag.
                            checks: dict[str, object] = {}
                            for name, check in (
                                ("verifier", lambda: runtime_attempt.verify_runtime_attempt(lane_output)),
                                ("input", lambda: runtime_calibration.verify_candidate_inputs(candidate.root)),
                                ("preparation_integrity", lambda: runtime_family_preparation.verify_runtime_family_preparation(prepared, candidate_root=candidate.root)),
                            ):
                                try:
                                    check()
                                    checks[name] = {"closed": True, "operation": name, "evidence_class": "recorded_simulation"}
                                except Exception as error:  # noqa: BLE001 - terminal health evidence
                                    checks[name] = {"closed": False, "error": getattr(error, "code", type(error).__name__), "evidence_class": "recorded_simulation"}
                            checks["device_session"] = _probe(device, reference)
                            if observations[index].source_health_fault:
                                selected.source_sha256 = "recorded_drift"
                            if observations[index].tool_health_fault:
                                selected.tool_version = "recorded_drift"
                            checks["source"] = selected.probe_dependency("source", source_reference)
                            checks["tool"] = selected.probe_dependency("tool", str(reference.get("android_cli_version")))
                            selected.log_capture_fault = (
                                selected.log_capture_fault or observations[index].log_health_fault
                                or observations[index].device.log_dump_fault is not None
                                or "dump_all_buffers_epoch" in observations[index].device.fail_operations
                            )
                            selected.checkpoint()
                            log_adapter = selected.adapter(
                                runtime_attempt.RecordingDevicePolicy(
                                    fail_operations=frozenset({"dump_all_buffers_epoch"}) if selected.log_capture_fault else frozenset(),
                                ), spec.package, spec.activity,
                            )
                            try:
                                capture = log_adapter.dump_all_buffers_epoch()
                                checks["log_collection"] = {
                                    "closed": capture.returncode == 0 and bool(capture.stdout.strip()),
                                    "operation": capture.operation,
                                    "command": list(capture.command),
                                    "returncode": capture.returncode,
                                    "stdout": capture.stdout, "stderr": capture.stderr,
                                    "evidence_class": "recorded_simulation",
                                }
                            except Exception as error:  # noqa: BLE001 - record capture refusal
                                checks["log_collection"] = {
                                    "closed": False, "error": getattr(error, "code", type(error).__name__),
                                    "evidence_class": "recorded_simulation",
                                }
                            health.append({"lane_id": lane_id, "boundary": "continuation", "checks": checks})
                            selected.checkpoint()
                            if not all(item["closed"] for item in checks.values()):
                                abort = "family_shared_health_unclosed"
                except Exception as error:  # noqa: BLE001 - preserve actual partial files
                    selected.checkpoint()
                    abort = getattr(error, "code", "family_lane_execution_failed")
                    existing_row = next((item for item in rows if item["lane_id"] == lane_id), None)
                    if existing_row is not None:
                        existing_row["verification_error"] = abort
                        # Preserve returned terminal references even if their bytes
                        # cannot be verified. Such a stage cannot itself be sealed.
                        abandoned = True
                    elif lane_output.exists():
                        # Any partial attempt artifact is evidence of a started but
                        # unclosed lane, including corrupt/missing records. Never
                        # invent a terminal disposition to repair that evidence.
                        abandoned = True
                    else:
                        rows.append({"lane_id": lane_id, "status": "not_attempted_due_to_family_abort"})
                    _write(output / "family-abort.json", _stamp({
                        "lane_id": lane_id, "reason": abort,
                        "error_type": type(error).__name__, "error": str(error),
                        "abandoned": abandoned, "rows": rows,
                        "evidence_class": "recorded_simulation",
                    }))
                    health.append({"lane_id": lane_id, "boundary": "after_interruption", "session": _probe(device, reference)})
                    selected.checkpoint()
        except Exception as error:  # noqa: BLE001 - session startup is a handled failure
            abort = getattr(error, "code", "family_session_start_failed")
        finally:
            if selected.started:
                try:
                    teardown = selected.stop()
                except Exception as error:  # noqa: BLE001 - teardown has independent evidence
                    teardown = {"status": "failed", "error": getattr(error, "code", type(error).__name__), "evidence_class": "recorded_simulation"}
                    abort = abort or "family_teardown_failed"
            _write(output / "session-teardown.json", _stamp(dict(teardown)))
            _write(output / "family-progress.json", _stamp({
                "rows": rows, "health": health, "abort_reason": abort,
                "session_lifecycle": selected.lifecycle,
                "evidence_class": "recorded_simulation",
            }))
        if abandoned:
            raise RuntimeFamilyExecutionError("family_abandoned_nonterminal_attempt")
        existing = {row["lane_id"] for row in rows}
        rows.extend({"lane_id": lane_id, "status": "not_attempted_due_to_family_abort"} for lane_id in LANE_ORDER if lane_id not in existing)
        rows.sort(key=lambda row: LANE_ORDER.index(row["lane_id"]))
        accepted = abort is None and all(row["status"] == runtime_attempt.ACCOUNTABLE_CONCLUDED for row in rows) and teardown["status"] == "ok"
        receipt = _stamp({
            "schema_version": 1, "stage": STAGE, "status": "accepted" if accepted else "rejected",
            "claim_boundary": CLAIM_BOUNDARY, "evidence_class": "recorded_simulation",
            "candidate_identity_sha256": candidate.candidate_identity_sha256,
            "predecessor_terminal_sha256": _sha(terminal_bytes),
            "preparation_receipt_sha256": _sha(preparation_bytes_on_disk),
            "start_receipt_sha256": start_sha, "session": {"lifecycle": selected.lifecycle, "reference": session_probe},
            "rows": rows, "health": health, "abort_reason": abort, "teardown": teardown,
            "invocations": {"model_calls": 0, "retries": 0, "replacements": 0},
            "artifact_inventory": _inventory(output),
        })
        receipt_sha = _write(output / "family-execution.json", receipt)
        terminal = _stamp({
            "schema_version": 1, "stage": STAGE, "status": receipt["status"],
            "claim_boundary": CLAIM_BOUNDARY, "start_receipt_sha256": start_sha,
            "execution_identity_sha256": receipt["identity_sha256"],
            "execution_receipt_sha256": receipt_sha,
            "artifact_inventory_sha256": runtime_calibration.canonical_sha256(receipt["artifact_inventory"]),
        }, "terminal_identity_sha256")
        _write(output / "stage-terminal.json", terminal)
        return RuntimeFamilyExecutionReceipt(output_root=output, accepted=accepted, document=receipt)
    except BaseException:
        # A hard interruption (or failure to seal evidence) remains nonterminal.
        # Do not recover or repair this stage on a subsequent invocation.
        raise
