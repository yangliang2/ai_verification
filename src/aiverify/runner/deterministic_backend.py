"""Least-authority deterministic Journey execution.

The deterministic backend is intentionally small.  Admission owns the exact
Run Spec and Driver Plan bytes; execution receives one opaque plan action, a
read-only resource-layout adapter, and an opaque evidence sink.  It cannot
inspect source meaning, an oracle, or a complete Run Spec through its request
type.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from aiverify.runner.command import CommandResult, CommandRunner, SubprocessCommandRunner
from aiverify.runner.execution_record import write_json_artifact
from aiverify.runner.journey_backend import (
    DETERMINISTIC_ANDROID_V1,
    JourneyExecutionResult,
)


_PLAN_FIELDS = {
    "schema_version",
    "document_kind",
    "family_id",
    "family_version",
    "lane_id",
    "plan_id",
    "run_spec_path",
    "run_spec_sha256",
    "actions",
}
_ACTION_FIELDS = {
    "action_id",
    "kind",
    "resource_id",
    "timeout_ms",
    "observation_interval_ms",
    "settle_ms",
}
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACTION_ID_RE = re.compile(r"^action-([0-9]{2})$")
_SAFE_RELATIVE_PATH_RE = re.compile(r"^[^\x00]+$")
_LAYOUT_READ_TIMEOUT_SECONDS = 5


class DeterministicDriverPlanError(ValueError):
    """Raised when a deterministic Driver Plan is not strictly admissible."""


class DeterministicDriverError(RuntimeError):
    """Raised when deterministic execution cannot close one Journey action."""

    def __init__(
        self,
        message: str,
        *,
        result_path: Path | None = None,
        events_path: Path | None = None,
        invocation_path: Path | None = None,
        command: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.result_path = result_path
        self.events_path = events_path
        self.invocation_path = invocation_path
        self.command = list(command) if command is not None else None


@dataclass(frozen=True)
class DeterministicPlanAction:
    """One admitted, opaque deterministic action."""

    action_id: str
    kind: str
    resource_id: str
    timeout_ms: int
    observation_interval_ms: int
    settle_ms: int

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "kind": self.kind,
            "resource_id": self.resource_id,
            "timeout_ms": self.timeout_ms,
            "observation_interval_ms": self.observation_interval_ms,
            "settle_ms": self.settle_ms,
        }


@dataclass(frozen=True)
class DeterministicDriverPlan:
    """Strict Driver Plan bytes and their parsed action commitments."""

    path: Path
    sha256: str
    bytes: int
    run_spec_path: str
    run_spec_sha256: str
    family_id: str
    family_version: str
    lane_id: str
    plan_id: str
    actions: tuple[DeterministicPlanAction, ...]

    @property
    def action(self) -> DeterministicPlanAction:
        """Return the sole action admitted by the current minimal slice."""
        if len(self.actions) != 1:
            raise DeterministicDriverPlanError(
                "Driver Plan action count must be exactly one"
            )
        return self.actions[0]

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "bytes": self.bytes,
            "run_spec_path": self.run_spec_path,
            "run_spec_sha256": self.run_spec_sha256,
            "family_id": self.family_id,
            "family_version": self.family_version,
            "lane_id": self.lane_id,
            "plan_id": self.plan_id,
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True)
class LayoutObservation:
    """One read-only Android CLI layout response."""

    command: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


class DeterministicLayoutAdapter(Protocol):
    """Narrow read-only device surface reachable by the deterministic driver."""

    def read_layout(self) -> LayoutObservation | CommandResult | str | list[object]:
        """Read one fresh device-scoped UI layout."""


class DeterministicEvidenceSink(Protocol):
    """Opaque append-only sink for backend-owned raw observations."""

    def record_observation(self, observation: dict[str, object]) -> None:
        """Retain one observation without exposing filesystem operations."""

    def persist(self) -> Path:
        """Finalize the retained observations and return their opaque reference."""


class AndroidLayoutDeviceAdapter:
    """Execute only the device-scoped Android CLI layout primitive."""

    __slots__ = ("_command", "_reader")

    def __init__(
        self,
        *,
        device: str,
        android_bin: str = "android",
        runner: CommandRunner | None = None,
    ) -> None:
        if not isinstance(device, str) or not device.strip():
            raise ValueError("deterministic device serial is required")
        self._command = (android_bin, "layout", f"--device={device}", "--pretty")
        command_runner = runner or SubprocessCommandRunner()

        def read() -> LayoutObservation:
            result = command_runner.run(
                list(self._command),
                timeout_seconds=_LAYOUT_READ_TIMEOUT_SECONDS,
            )
            return LayoutObservation(
                command=self._command,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
            )

        self._reader = read

    def read_layout(self) -> LayoutObservation:
        return self._reader()


class RecordingEvidenceSink:
    """Small recording sink useful for contract tests and local diagnostics."""

    def __init__(self, artifact_dir: Path) -> None:
        self._artifact_dir = Path(artifact_dir).resolve()
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[dict[str, object]] = []
        self._path = self._artifact_dir / "deterministic-observations.json"

    def record_observation(self, observation: dict[str, object]) -> None:
        self.records.append(dict(observation))

    def persist(self) -> Path:
        write_json_artifact(
            self._path,
            {
                "schema_version": 1,
                "backend": DETERMINISTIC_ANDROID_V1,
                "observations": self.records,
            },
        )
        return self._path


@dataclass(frozen=True)
class DeterministicDriverRequest:
    """Least-authority request for exactly one deterministic Journey action."""

    segment_id: str
    action_id: str
    plan_action: DeterministicPlanAction
    device: DeterministicLayoutAdapter
    evidence_sink: DeterministicEvidenceSink


def load_deterministic_driver_plan(
    path: Path,
    *,
    serialized_run_spec: bytes,
    run_spec_path: Path,
    expected_actions: Sequence[str],
    plan_bytes: bytes | None = None,
) -> DeterministicDriverPlan:
    """Parse and bind one strict plan to exact Run Spec bytes and actions.

    ``plan_bytes`` exists for callers that already hold an authoritative plan
    snapshot.  Normal callers omit it and this function reads ``path`` once.
    Duplicate JSON keys are rejected before any semantic validation.
    """

    plan_path = Path(path).expanduser().resolve()
    if plan_bytes is None:
        try:
            plan_bytes = plan_path.read_bytes()
        except OSError as error:
            raise DeterministicDriverPlanError(
                f"Driver Plan cannot be read: {plan_path}"
            ) from error
    if not isinstance(plan_bytes, bytes):
        raise DeterministicDriverPlanError("Driver Plan bytes must be bytes")
    try:
        text = plan_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DeterministicDriverPlanError("Driver Plan must be strict UTF-8") from error
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateJsonKeyError as error:
        raise DeterministicDriverPlanError(str(error)) from error
    except json.JSONDecodeError as error:
        raise DeterministicDriverPlanError(
            f"Driver Plan is not valid JSON: {error.msg}"
        ) from error
    if not isinstance(payload, dict):
        raise DeterministicDriverPlanError("Driver Plan top level must be an object")

    expected = tuple(expected_actions)

    _validate_exact_fields(payload, _PLAN_FIELDS, "Driver Plan")
    _require_int(payload, "schema_version", expected=1)
    _require_exact_string(payload, "document_kind", "deterministic_driver_plan")
    family_id = _require_nonempty_string(payload, "family_id")
    family_version = _require_nonempty_string(payload, "family_version")
    lane_id = _require_nonempty_string(payload, "lane_id")
    plan_id = _require_nonempty_string(payload, "plan_id")
    declared_run_spec_path = _require_relative_path(payload, "run_spec_path")
    declared_run_spec_sha256 = _require_sha256(payload, "run_spec_sha256")

    actions_value = payload["actions"]
    if not isinstance(actions_value, list) or len(actions_value) != 1:
        raise DeterministicDriverPlanError(
            "Driver Plan action count must be exactly one"
        )
    if len(actions_value) != len(expected):
        raise DeterministicDriverPlanError(
            "Driver Plan action count does not match the admitted Journey"
        )
    actions = tuple(
        _parse_action(item, expected_index=index)
        for index, item in enumerate(actions_value, start=1)
    )

    source_bytes = serialized_run_spec
    if not isinstance(source_bytes, bytes):
        raise DeterministicDriverPlanError("serialized Run Spec must be bytes")
    actual_run_spec_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if declared_run_spec_sha256 != actual_run_spec_sha256:
        raise DeterministicDriverPlanError(
            "Driver Plan Run Spec digest mismatch"
        )

    if not _declared_path_matches(
        plan_path,
        declared_run_spec_path,
        Path(run_spec_path),
    ):
        raise DeterministicDriverPlanError(
            "Driver Plan Run Spec path does not identify the exact Run Spec"
        )

    for index, (action, requested) in enumerate(zip(actions, expected, strict=True), start=1):
        if not isinstance(requested, str):
            raise DeterministicDriverPlanError(
                f"admitted Journey action {index} is not a string"
            )
        expected_kind, expected_resource = _parse_requested_action(requested)
        if action.kind != expected_kind or action.resource_id != expected_resource:
            raise DeterministicDriverPlanError(
                f"Driver Plan action {index} does not match the admitted Journey"
            )

    return DeterministicDriverPlan(
        path=plan_path,
        sha256=hashlib.sha256(plan_bytes).hexdigest(),
        bytes=len(plan_bytes),
        run_spec_path=declared_run_spec_path,
        run_spec_sha256=declared_run_spec_sha256,
        family_id=family_id,
        family_version=family_version,
        lane_id=lane_id,
        plan_id=plan_id,
        actions=actions,
    )


def validate_deterministic_driver_plan(
    path: Path,
    *,
    serialized_run_spec: bytes,
    run_spec_path: Path,
    expected_actions: Sequence[str],
    plan_bytes: bytes | None = None,
) -> DeterministicDriverPlan:
    """Named validation alias for admission callers."""

    return load_deterministic_driver_plan(
        path,
        serialized_run_spec=serialized_run_spec,
        run_spec_path=run_spec_path,
        expected_actions=expected_actions,
        plan_bytes=plan_bytes,
    )


class DeterministicAndroidBackend:
    """Execute the minimal fixed-bound resource wait primitive."""

    backend_id = DETERMINISTIC_ANDROID_V1

    def __init__(
        self,
        *,
        plan: DeterministicDriverPlan,
        device: str,
        android_bin: str = "android",
        command_runner: CommandRunner | None = None,
        device_adapter: DeterministicLayoutAdapter | None = None,
        evidence_sink_factory: Callable[[Path], DeterministicEvidenceSink] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(plan, DeterministicDriverPlan):
            raise DeterministicDriverPlanError("deterministic backend requires an admitted Driver Plan")
        if not isinstance(device, str) or not device.strip():
            raise DeterministicDriverError("deterministic device serial is required")
        self._plan = plan
        self._device = device
        self._device_adapter = device_adapter or AndroidLayoutDeviceAdapter(
            device=device,
            android_bin=android_bin,
            runner=command_runner,
        )
        self._evidence_sink_factory = evidence_sink_factory or RecordingEvidenceSink
        self._clock = clock
        self._sleeper = sleeper

    def build_request(
        self,
        *,
        segment_id: str,
        action_offset: int,
        action_count: int,
        artifact_dir: Path,
        device: str | None = None,
    ) -> DeterministicDriverRequest:
        """Build a request without passing Run Spec or source-rich data."""

        if not isinstance(segment_id, str) or not segment_id:
            raise DeterministicDriverPlanError("deterministic segment identity is required")
        if device is not None and device != self._device:
            raise DeterministicDriverError("deterministic request device contradicts selection")
        if type(action_offset) is not int or action_offset < 0:
            raise DeterministicDriverPlanError("deterministic action offset is invalid")
        if type(action_count) is not int or action_count != 1:
            raise DeterministicDriverPlanError(
                "deterministic_android_v1 currently admits one opaque Journey action"
            )
        if len(self._plan.actions) != 1 or action_offset != 0:
            raise DeterministicDriverPlanError("deterministic action slice is outside the Driver Plan")
        action = self._plan.actions[action_offset]
        if action.kind != "wait_for_resource_id":
            raise DeterministicDriverPlanError(
                "deterministic_android_v1 only admits wait_for_resource_id"
            )
        sink = self._evidence_sink_factory(Path(artifact_dir))
        return DeterministicDriverRequest(
            segment_id=segment_id,
            action_id=f"action-{action_offset + 1}",
            plan_action=action,
            device=self._device_adapter,
            evidence_sink=sink,
        )

    def execute(self, request: DeterministicDriverRequest) -> JourneyExecutionResult:
        """Run exactly one wait poll and persist raw backend evidence."""

        if not isinstance(request, DeterministicDriverRequest):
            raise DeterministicDriverError("deterministic request type is invalid")
        if (
            request.device is not self._device_adapter
            or len(self._plan.actions) != 1
            or request.plan_action != self._plan.action
            or request.action_id != "action-1"
        ):
            raise DeterministicDriverError(
                "deterministic request is not the admitted Driver Plan slice"
            )
        if request.plan_action.kind != "wait_for_resource_id":
            raise DeterministicDriverError(
                "deterministic_android_v1 only admits wait_for_resource_id"
            )
        observations: list[dict[str, object]] = []
        start = self._clock()
        deadline = start + request.plan_action.timeout_ms / 1000
        max_observations = (
            request.plan_action.timeout_ms
            // request.plan_action.observation_interval_ms
            + 1
        )
        command: list[str] = []

        while True:
            observation_index = len(observations) + 1
            try:
                read = request.device.read_layout()
                layout_read = _coerce_layout_observation(read)
                command = list(layout_read.command)
            except Exception as error:  # noqa: BLE001 - device interruption is evidence
                observation = {
                    "observation_index": observation_index,
                    "status": "interrupted",
                    "command": command,
                    "returncode": None,
                    "stdout": "",
                    "stderr": "",
                    "layout": None,
                    "match_count": None,
                    "error": f"{type(error).__name__}: {error}",
                }
                self._record(request.evidence_sink, observation, observations)
                return self._failed(
                    request,
                    observations,
                    f"deterministic layout observation interrupted: {error}",
                    command=command,
                )

            base = {
                "observation_index": observation_index,
                "command": list(layout_read.command),
                "returncode": layout_read.returncode,
                "stdout": layout_read.stdout,
                "stderr": layout_read.stderr,
            }
            if layout_read.returncode != 0:
                observation = {
                    **base,
                    "status": "command_failed",
                    "layout": None,
                    "match_count": None,
                }
                self._record(request.evidence_sink, observation, observations)
                return self._failed(
                    request,
                    observations,
                    "deterministic layout command failed",
                    command=command,
                )

            try:
                layout = _parse_layout(layout_read.stdout)
            except DeterministicDriverError as error:
                observation = {
                    **base,
                    "status": "malformed_layout",
                    "layout": None,
                    "match_count": None,
                    "error": str(error),
                }
                self._record(request.evidence_sink, observation, observations)
                return self._failed(
                    request,
                    observations,
                    str(error),
                    command=command,
                )

            matching = [
                node
                for node in layout
                if _resource_id_matches(node, request.plan_action.resource_id)
            ]
            status = (
                "resource_found"
                if len(matching) == 1
                else "resource_duplicate"
                if len(matching) > 1
                else "resource_missing"
            )
            observation = {
                **base,
                "status": status,
                "layout": layout,
                "match_count": len(matching),
            }
            self._record(request.evidence_sink, observation, observations)
            if len(matching) == 1:
                return self._succeeded(
                    request,
                    observations,
                    command=command,
                )
            if len(matching) > 1:
                return self._failed(
                    request,
                    observations,
                    f"resource id {request.plan_action.resource_id} is duplicated",
                    command=command,
                )

            now = self._clock()
            interval = request.plan_action.observation_interval_ms / 1000
            if len(observations) >= max_observations or now + interval > deadline:
                return self._failed(
                    request,
                    observations,
                    f"wait for resource id {request.plan_action.resource_id} timed out",
                    command=command,
                )
            try:
                self._sleeper(interval)
            except Exception as error:  # noqa: BLE001 - interruption is evidence
                interruption = {
                    "observation_index": len(observations) + 1,
                    "status": "interrupted",
                    "command": command,
                    "returncode": None,
                    "stdout": "",
                    "stderr": "",
                    "layout": None,
                    "match_count": None,
                    "error": f"{type(error).__name__}: {error}",
                }
                self._record(request.evidence_sink, interruption, observations)
                return self._failed(
                    request,
                    observations,
                    f"deterministic wait interrupted: {error}",
                    command=command,
                )

    def _record(
        self,
        sink: DeterministicEvidenceSink,
        observation: dict[str, object],
        observations: list[dict[str, object]],
    ) -> None:
        observations.append(observation)
        sink.record_observation(observation)

    def _succeeded(
        self,
        request: DeterministicDriverRequest,
        observations: list[dict[str, object]],
        *,
        command: list[str],
    ) -> JourneyExecutionResult:
        data = {
            "schema_version": 1,
            "journey": request.segment_id,
            "results": [
                {
                    "action_id": request.action_id,
                    "plan_action_id": request.plan_action.action_id,
                    "status": "PASSED",
                    "commands": [command] if command else [],
                    "comment": f"{request.plan_action.resource_id} was observed exactly once; dispatch only.",
                }
            ],
        }
        return self._persist_result(
            request,
            data,
            observations,
            command=command,
        )

    def _failed(
        self,
        request: DeterministicDriverRequest,
        observations: list[dict[str, object]],
        message: str,
        *,
        command: list[str],
    ) -> JourneyExecutionResult:
        data = {
            "schema_version": 1,
            "journey": request.segment_id,
            "results": [
                {
                    "action_id": request.action_id,
                    "plan_action_id": request.plan_action.action_id,
                    "status": "FAILED",
                    "commands": [command] if command else [],
                    "comment": message,
                }
            ],
        }
        result = self._persist_result(request, data, observations, command=command)
        raise DeterministicDriverError(
            message,
            result_path=result.raw_result_path or result.result_path,
            events_path=result.raw_events_path or result.events_path,
            invocation_path=Path(result.metadata["invocation_receipt_path"]),
            command=command,
        )

    def _persist_result(
        self,
        request: DeterministicDriverRequest,
        data: dict[str, object],
        observations: list[dict[str, object]],
        *,
        command: list[str],
    ) -> JourneyExecutionResult:
        sink = request.evidence_sink
        persist = getattr(sink, "persist", None)
        if not callable(persist):
            raise DeterministicDriverError("deterministic evidence sink cannot be finalized")
        events_path = Path(persist())
        result_path = events_path.parent / "deterministic-journey-result.json"
        invocation_path = events_path.parent / "deterministic-driver-invocation.json"
        write_json_artifact(result_path, data)
        result_sha256 = _sha256_file(result_path)
        events_sha256 = _sha256_file(events_path)
        write_json_artifact(
            invocation_path,
            {
                "schema_version": 1,
                "backend": DETERMINISTIC_ANDROID_V1,
                "role": "journey_driver",
                "journey": request.segment_id,
                "action_id": request.action_id,
                "plan_action_id": request.plan_action.action_id,
                "requested_model": None,
                "effective_model": None,
                "model_calls": 0,
                "command": command,
                "result_path": str(result_path),
                "events_path": str(events_path),
                "raw_result_sha256": result_sha256,
                "raw_events_sha256": events_sha256,
                "observation_count": len(observations),
            },
        )
        return JourneyExecutionResult(
            data=data,
            result_path=result_path,
            events_path=events_path,
            command=command,
            metadata={
                "backend": DETERMINISTIC_ANDROID_V1,
                "raw_result_path": str(result_path),
                "raw_events_path": str(events_path),
                "invocation_receipt_path": str(invocation_path),
            },
            backend=DETERMINISTIC_ANDROID_V1,
            raw_result_path=result_path,
            raw_events_path=events_path,
        )


def _parse_action(value: object, *, expected_index: int) -> DeterministicPlanAction:
    if not isinstance(value, dict):
        raise DeterministicDriverPlanError(
            f"Driver Plan action {expected_index} must be an object"
        )
    _validate_exact_fields(value, _ACTION_FIELDS, f"Driver Plan action {expected_index}")
    action_id = _require_nonempty_string(value, "action_id")
    match = _ACTION_ID_RE.fullmatch(action_id)
    if match is None or int(match.group(1)) != expected_index:
        raise DeterministicDriverPlanError(
            f"Driver Plan action {expected_index} has an invalid action_id"
        )
    kind = _require_nonempty_string(value, "kind")
    if kind != "wait_for_resource_id":
        raise DeterministicDriverPlanError(
            "deterministic_android_v1 only admits wait_for_resource_id"
        )
    resource_id = _require_nonempty_string(value, "resource_id")
    if _RESOURCE_ID_RE.fullmatch(resource_id) is None:
        raise DeterministicDriverPlanError(
            f"Driver Plan action {expected_index} resource_id is invalid"
        )
    timeout_ms = _require_int(value, "timeout_ms", minimum=0)
    interval_ms = _require_int(value, "observation_interval_ms", minimum=1)
    settle_ms = _require_int(value, "settle_ms", minimum=0)
    if timeout_ms != 5000 or interval_ms != 350 or settle_ms != 0:
        raise DeterministicDriverPlanError(
            "wait_for_resource_id is fixed at timeout 5000 ms, observation interval 350 ms, and settle 0 ms"
        )
    return DeterministicPlanAction(
        action_id=action_id,
        kind=kind,
        resource_id=resource_id,
        timeout_ms=timeout_ms,
        observation_interval_ms=interval_ms,
        settle_ms=settle_ms,
    )


def _parse_requested_action(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"wait for resource id ([A-Za-z][A-Za-z0-9_.:-]*)", value)
    if match is None:
        raise DeterministicDriverPlanError(
            "admitted Journey contains an action outside the deterministic wait contract"
        )
    return "wait_for_resource_id", match.group(1)


def _coerce_layout_observation(value: object) -> LayoutObservation:
    if isinstance(value, LayoutObservation):
        return value
    if isinstance(value, CommandResult):
        return LayoutObservation(
            command=tuple(value.args),
            stdout=value.stdout,
            stderr=value.stderr,
            returncode=value.returncode,
        )
    if isinstance(value, str):
        return LayoutObservation(stdout=value)
    if isinstance(value, list):
        return LayoutObservation(stdout=json.dumps(value, ensure_ascii=False))
    raise DeterministicDriverError("deterministic layout adapter returned an invalid observation")


def _parse_layout(raw: str) -> list[dict[str, object]]:
    if not isinstance(raw, str):
        raise DeterministicDriverError("deterministic layout is malformed")
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (_DuplicateJsonKeyError, json.JSONDecodeError) as error:
        raise DeterministicDriverError("deterministic layout is malformed") from error
    if not isinstance(value, list) or not all(isinstance(node, dict) for node in value):
        raise DeterministicDriverError("deterministic layout is malformed")
    return value


def _resource_id_matches(node: Mapping[str, object], expected: str) -> bool:
    actual = node.get("resource-id", node.get("resourceId"))
    return isinstance(actual, str) and (
        actual == expected or actual.endswith(f":id/{expected}")
    )


def _validate_exact_fields(value: Mapping[str, object], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    missing = allowed - set(value)
    if unknown:
        raise DeterministicDriverPlanError(
            f"{label} contains unknown field(s): {', '.join(sorted(unknown))}"
        )
    if missing:
        raise DeterministicDriverPlanError(
            f"{label} is missing field(s): {', '.join(sorted(missing))}"
        )


def _require_nonempty_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise DeterministicDriverPlanError(f"Driver Plan field {key} must be a non-empty string")
    return item


def _require_exact_string(value: Mapping[str, object], key: str, expected: str) -> str:
    item = _require_nonempty_string(value, key)
    if item != expected:
        raise DeterministicDriverPlanError(
            f"Driver Plan field {key} must be {expected!r}"
        )
    return item


def _require_int(
    value: Mapping[str, object],
    key: str,
    *,
    expected: int | None = None,
    minimum: int | None = None,
) -> int:
    item = value.get(key)
    if type(item) is not int:
        raise DeterministicDriverPlanError(f"Driver Plan field {key} must be an integer")
    if expected is not None and item != expected:
        raise DeterministicDriverPlanError(
            f"Driver Plan field {key} must be {expected}"
        )
    if minimum is not None and item < minimum:
        raise DeterministicDriverPlanError(
            f"Driver Plan field {key} must be at least {minimum}"
        )
    return item


def _require_sha256(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or _SHA256_RE.fullmatch(item) is None:
        raise DeterministicDriverPlanError(
            f"Driver Plan field {key} must be a lowercase SHA-256 digest"
        )
    return item


def _require_relative_path(value: Mapping[str, object], key: str) -> str:
    item = _require_nonempty_string(value, key)
    path = Path(item)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or _SAFE_RELATIVE_PATH_RE.fullmatch(item) is None
    ):
        raise DeterministicDriverPlanError(
            f"Driver Plan field {key} must be a safe relative path"
        )
    return path.as_posix()


def _declared_path_matches(plan_path: Path, declared: str, run_spec_path: Path) -> bool:
    expected = Path(run_spec_path).expanduser().resolve()
    current = plan_path.parent
    for _ in range(16):
        if (current / declared).resolve() == expected:
            return True
        if current.parent == current:
            break
        current = current.parent
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise DeterministicDriverError(
            f"deterministic evidence artifact cannot be hashed: {path}: {error}"
        ) from error
    return digest.hexdigest()


class _DuplicateJsonKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


__all__ = [
    "AndroidLayoutDeviceAdapter",
    "DeterministicAndroidBackend",
    "DeterministicDriverError",
    "DeterministicDriverPlan",
    "DeterministicDriverPlanError",
    "DeterministicDriverRequest",
    "DeterministicEvidenceSink",
    "DeterministicLayoutAdapter",
    "DeterministicPlanAction",
    "LayoutObservation",
    "RecordingEvidenceSink",
    "load_deterministic_driver_plan",
    "validate_deterministic_driver_plan",
]
