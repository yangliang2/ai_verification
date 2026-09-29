"""One accountable OpenCalc runtime attempt on the public single-lane seam.

This module owns step 5 of the ``opencalc-runtime-calibration-v1`` slicing
plan: the production-shaped runtime attempt for exactly one prepared lane.  It
takes the frozen public lane inputs (Run Spec, admitted Driver Plan, Attempt
Setup Plan), the Sealed Runtime APK preparation handoff, and a Runtime Attempt
Device, and it concludes one attempt as ``accountable_concluded`` or
``non_accountable``.

Design contracts owned here:

- One ExecutionRecord is established before the first external side effect and
  is finalized exactly once.  Every pre-record rejection raises before any
  device I/O, so no fabricated record and no placeholder attempt is created.
- The Target Log Window is cleared once and marker-bounded once.  Every
  runner-reachable terminal path after the start marker writes exactly one end
  marker and captures exactly one all-buffer epoch dump.  A failure before the
  start marker has no fabricated window receipt.
- The Lifecycle Transition Receipt binds the ordered destroy -> create ->
  resume signature, the relaunch tag, same task/PID, landscape resume at
  rotation 1, and the absence of target process start/death/restart.
- L1 is attribution-aware: only a crash/ANR signal attributable to the target
  package fails L1, an unresolvable attribution is non-accountable, and a
  complete attributable window without a signal is ``inconclusive`` -- never
  ``pass``.  The canonical ``L1Oracle`` verdict is recomputed over the same
  target-filtered evidence and recorded next to it.
- L2 evaluates one unique post-event ``input`` node: exact ``12+34`` passes,
  any other text fails with ``state_loss``, and a missing or duplicated node is
  an accountable ``inconclusive``.

Two device surfaces are provided:

- :class:`RecordingRuntimeDevice` is a bounded simulation used by contract and
  integration tests.  It reports ``device_kind = "recording"`` and the attempt
  receipt binds ``test_substitutes`` from the preparation handoff, so a
  simulated attempt can never be mistaken for device evidence.
- :class:`AdbRuntimeDevice` is the production adapter.  Its command vectors are
  admitted by contract tests, but real-device lifecycle attribution remains
  unverified until the nine-cycle Auditor Runtime Preflight runs on a real
  emulator.

Known gap, recorded with the attempt evidence: the frozen minimal lifecycle
signature is provisional.  ``docs/opencalc-runtime-calibration-v1.md`` freezes
it only after all nine auditor cycles agree, so this module binds the exact
predicate identity it judged under and marks it
``provisional_pending_nine_auditor_cycles``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import NoReturn, Protocol, Self, TypeVar

import yaml

from aiverify.agent.oracle import L1Oracle
from aiverify.bench import runtime_calibration
from aiverify.harness.device.logcat import LogcatAnalyzer, LogEvent
from aiverify.runner.command import (
    CommandResult,
    CommandRunner,
    SubprocessCommandRunner,
)
from aiverify.runner.deterministic_backend import (
    DeterministicAndroidBackend,
    DeterministicDriverError,
    DeterministicDriverPlan,
    DeterministicDriverPlanError,
    LayoutObservation,
)
from aiverify.runner.execution_record import (
    ArtifactStorageError,
    ExecutionRecordStorageError,
    ExecutionRecordStore,
    ExecutionRecordValidationError,
    load_execution_record,
    write_bytes_artifact,
)
from aiverify.runner.journey_backend import DETERMINISTIC_ANDROID_V1
from aiverify.runner.run_spec import RunSpec
from aiverify.runtime_preparation import (
    RuntimePreparationReceipt,
    runtime_preparation_uses_test_substitutes,
    sealed_apk_binding_from_receipt,
)

SCHEMA_VERSION = 1
SEAM = "runtime_attempt_v1"
CLAIM_BOUNDARY = "one_accountable_preserved_state_runtime_attempt"

ACCOUNTABLE_CONCLUDED = "accountable_concluded"
NON_ACCOUNTABLE = "non_accountable"

# Frozen Attempt Setup Plan (docs/opencalc-runtime-calibration-v1.md section 10).
ATTEMPT_SETUP_PLAN_ID = "attempt-setup-plan-v1"
ATTEMPT_SETUP_OPERATIONS = ("clear_package_data", "force_portrait")
ALLOWED_ROTATION_SETTINGS = ("accelerometer_rotation", "user_rotation")
PORTRAIT_ROTATION = 0
LANDSCAPE_ROTATION = 1
SETUP_SETTLE_SECONDS = 0.35
LAUNCH_SETTLE_SECONDS = 0.35

# Frozen Boundary Precondition and L2 contract (section 6).
INPUT_RESOURCE_ID = "input"
BOUNDARY_PRECONDITION_TEXT = "12+34"

# Bounded post-event read-only poll (section 6).
LIFECYCLE_POLL_BUDGET = 50
LIFECYCLE_POLL_INTERVAL_SECONDS = 0.1
LIFECYCLE_POLL_SECONDS = 5.0

# Target Log Window markers and dumps (section 6).
MARKER_TAG = "aiverify_attempt"
TARGET_WINDOW_START = "target-window-start"
TARGET_WINDOW_END = "target-window-end"
LIFECYCLE_START = "lifecycle-start"
LIFECYCLE_END = "lifecycle-end"
LOG_WINDOW_BUFFERS = ("all",)
LOG_WINDOW_FORMAT = "epoch"

# Provisional frozen lifecycle signature (section 6).  The identity below is
# bound by every receipt; a later freeze is a versioned change, never a silent
# predicate drift.
LIFECYCLE_SIGNATURE_ID = "opencalc-lifecycle-signature-v1"
LIFECYCLE_SIGNATURE_STATUS = "provisional_pending_nine_auditor_cycles"
LIFECYCLE_SIGNATURE_EVENTS = ("destroy", "create", "resume")
LIFECYCLE_EVENT_TERMS: Mapping[str, str] = {
    "destroy": "am_on_destroy_called",
    "create": "am_on_create_called",
    "resume": "am_on_resume_called",
}
LIFECYCLE_RELAUNCH_TAG = "Relaunching"
LIFECYCLE_EVENT_EXCERPT_CHARS = 160

# Target-scoped process facts used by the lifecycle receipt.
PROCESS_START_TEMPLATE = r"Start proc \d+:{package}\b"
PROCESS_DEATH_TEMPLATES = (
    r"Process {package} \(pid \d+\) has died",
    r"Killing \d+:{package}\b",
)

L1_OUTCOME_INCONCLUSIVE = "inconclusive"
L1_OUTCOME_FAIL = "fail"
L2_OUTCOME_PASS = "pass"
L2_OUTCOME_FAIL = "fail"
L2_OUTCOME_INCONCLUSIVE = "inconclusive"

# Frozen tap trajectory and exactly-once device mutation contract: the attempt
# has no retry, no compensation, and no command outside these tables.  The
# ordered mutation sequence is the strongest zero-retry proof the seam can
# bind, so it is declared once and compared against the recorded dispatch log.
FROZEN_TAP_TRAJECTORY = (
    "oneButton",
    "twoButton",
    "addButton",
    "threeButton",
    "fourButton",
)
EXPECTED_DEVICE_MUTATION_COUNTS: Mapping[str, int] = {
    "deploy_apk": 1,
    "clear_package_data": 1,
    "write_rotation_setting": 2,
    "clear_log_buffers": 1,
    "write_log_marker": 4,
    "canonical_launch": 1,
    "dispatch_orientation": 1,
}
EXPECTED_DEVICE_READ_COUNTS: Mapping[str, int] = {
    "probe_session": 1,
    "read_installed_apk": 1,
    "target_process_ids": 1,
    "read_rotation_state": 1,
    "dump_all_buffers_epoch": 1,
}
MINIMUM_TAP_COUNT = 5
MINIMUM_LAYOUT_READ_COUNT = 8


def expected_device_mutation_order(*, tap_count: int) -> tuple[str, ...]:
    """Return the frozen ordered mutation sequence for one attempt shape."""
    if type(tap_count) is not int or tap_count < MINIMUM_TAP_COUNT:
        raise RuntimeAttemptInputError("attempt_tap_budget_invalid")
    return (
        "deploy_apk",
        "clear_package_data",
        "write_rotation_setting",
        "write_rotation_setting",
        "clear_log_buffers",
        "write_log_marker",
        "canonical_launch",
        *("tap",) * tap_count,
        "write_log_marker",
        "dispatch_orientation",
        "write_log_marker",
        "write_log_marker",
    )


def expected_device_read_counts(
    *, layout_reads: int, foreground_reads: int
) -> Mapping[str, int]:
    """Return the frozen read contract for one attempt shape."""
    if type(layout_reads) is not int or layout_reads < MINIMUM_LAYOUT_READ_COUNT:
        raise RuntimeAttemptInputError("attempt_layout_read_budget_invalid")
    if type(foreground_reads) is not int or foreground_reads < 1:
        raise RuntimeAttemptInputError("attempt_foreground_read_budget_invalid")
    return {
        **EXPECTED_DEVICE_READ_COUNTS,
        "read_layout": layout_reads,
        "read_foreground_state": foreground_reads,
    }

SESSION_REQUIRED_FIELDS = (
    "boot_id",
    "android_cli_version",
    "emulator_version",
    "adb_version",
    "avd_name",
    "avd_config_sha256",
    "system_image_manifest_sha256",
    "api_level",
    "fingerprint",
    "abi",
    "model",
    "hardware",
    "display_size",
    "display_density",
)
SESSION_IDENTITY_SETTINGS = (
    "locale",
    "timezone",
    "font_scale",
    "window_animation_scale",
    "transition_animation_scale",
    "animator_duration_scale",
    "ui_night_mode",
    "navigation_mode",
    "default_input_method",
    "enabled_accessibility_services",
)

# Failure scope map.  Shared failures abort the rest of the family; lane-local
# failures may be followed by the prescribed shared-health checks.  Every
# non-accountable attempt binds exactly one reason from this vocabulary.
SHARED_FAILURE_REASONS = frozenset(
    {
        "device_session_unavailable",
        "sealed_apk_unavailable",
        "sealed_apk_bytes_drifted",
        "sealed_apk_deployment_failed",
        "installed_apk_read_failed",
        "attempt_setup_failed",
        "target_log_window_unavailable",
        "target_log_window_marker_error",
        "target_log_window_capture_failed",
        "canonical_launch_failed",
        "journey_driver_failed",
        "boundary_layout_unreadable",
        "orientation_dispatch_failed",
        "orientation_not_observed",
        "lifecycle_transition_unproven",
        "target_process_restarted",
        "post_event_layout_unreadable",
        "log_attribution_ambiguous",
        "device_operation_budget_violated",
        "attempt_artifact_write_failed",
        "attempt_receipt_write_failed",
        "device_io_failed",
    }
)

# Every phase that can reach the device owns one canonical failure reason, so a
# device exception is never reported as an untyped harness crash.
PHASE_FAILURE_REASONS: Mapping[str, str] = {
    "device-session": "device_session_unavailable",
    "deploy-sealed-apk": "sealed_apk_deployment_failed",
    "attempt-setup": "attempt_setup_failed",
    "open-target-log-window": "target_log_window_unavailable",
    "close-target-log-window": "target_log_window_capture_failed",
    "canonical-launch": "canonical_launch_failed",
    "journey": "journey_driver_failed",
    "boundary-precondition": "boundary_layout_unreadable",
    "lifecycle-rotation": "orientation_dispatch_failed",
    "collect-post-event-observation": "post_event_layout_unreadable",
    "finalize-receipt": "attempt_receipt_write_failed",
}

# Frozen artifact kinds: the verifier refuses an inventory that hides,
# drops, or duplicates one of them, so a shadowed capture can never be used to
# recompute another artifact's claim.
_FROZEN_ARTIFACT_KINDS = (
    "journey_result",
    "journey_events",
    "journey_invocation",
    "boundary_layout",
    "post_event_layout",
    "target_log_window",
    "lifecycle_window",
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class RuntimeAttemptError(RuntimeError):
    """Raised when one runtime attempt cannot close its own contract."""

    def __init__(self, code: str, message: str = "") -> None:
        if not isinstance(code, str) or not code:
            raise ValueError("runtime attempt error code is required")
        super().__init__(message or code)
        self.code = code


class RuntimeAttemptInputError(RuntimeAttemptError):
    """Raised before the record exists: no device I/O and no fabricated attempt."""


class RuntimeAttemptDeviceError(RuntimeAttemptError):
    """Raised when the Runtime Attempt Device cannot close one operation."""

    def __init__(self, operation: str, message: str = "") -> None:
        super().__init__(f"{operation}_failed", message or f"{operation} failed")
        self.operation = operation


class RuntimeAttemptVerificationError(RuntimeAttemptError):
    """Raised when committed attempt evidence no longer verifies."""


class _AttemptAbort(Exception):
    """Internal terminal signal carrying the canonical non-accountable reason."""

    def __init__(
        self,
        phase: str,
        kind: str,
        reason: str,
        message: str,
        *,
        scope: str,
    ) -> None:
        super().__init__(f"{phase}: {reason}: {message}")
        self.phase = phase
        self.kind = kind
        self.reason = reason
        self.message = message
        self.scope = scope


def canonical_sha256(value: object) -> str:
    """Return the repository-wide compact canonical JSON identity."""
    return runtime_calibration.canonical_sha256(value)


def canonical_bytes(value: object) -> bytes:
    """Return the canonical on-disk JSON bytes for one receipt document."""
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _stamp(document: dict[str, object]) -> dict[str, object]:
    """Bind one component document to its own canonical identity."""
    body = dict(document)
    body.pop("identity_sha256", None)
    document["identity_sha256"] = canonical_sha256(body)
    return document


def _require_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeAttemptError(code, code)
    return value


def _require_digest(value: object, code: str) -> str:
    text = _require_text(value, code)
    if _HEX_64.fullmatch(text) is None:
        raise RuntimeAttemptError(code, code)
    return text


def _require_int(value: object, code: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise RuntimeAttemptError(code, code)
    return value


def _read_json_object(path: Path, code: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeAttemptVerificationError(code, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeAttemptVerificationError(code, code) from error
    if not isinstance(value, dict):
        raise RuntimeAttemptVerificationError(code, code)
    return value


def attempt_marker(*, lane_id: str, attempt_id: str, kind: str) -> str:
    """Return one attempt-bound, whitespace-free log marker."""
    if not all(isinstance(item, str) and item for item in (lane_id, attempt_id, kind)):
        raise RuntimeAttemptInputError("attempt_marker_identity_invalid")
    return f"aiverify-attempt:{lane_id}:{attempt_id}:{kind}"


def _prepare_output_root(output_root: str | Path) -> Path:
    raw = Path(output_root).expanduser()
    if raw.is_symlink():
        raise RuntimeAttemptInputError("attempt_output_root_symlink")
    root = raw.resolve()
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            raise RuntimeAttemptInputError("attempt_output_root_not_empty")
    else:
        try:
            root.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise RuntimeAttemptInputError("attempt_output_root_unavailable") from error
    return root


def _write_json_exclusive(path: Path, document: Mapping[str, object]) -> tuple[str, str]:
    """Write one sealed receipt and return its file digest and identity."""
    if path.exists() or path.is_symlink():
        raise RuntimeAttemptError("attempt_receipt_already_exists")
    payload = canonical_bytes(document)
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
    except FileExistsError as error:
        raise RuntimeAttemptError("attempt_receipt_already_exists") from error
    except OSError as error:
        raise RuntimeAttemptError("attempt_receipt_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256_bytes(payload), _require_digest(
        document.get("identity_sha256"), "attempt_receipt_identity_invalid"
    )


@dataclass(frozen=True)
class RuntimeAttemptSetupPlan:
    """The strict, byte-identical Attempt Setup Plan for one family."""

    family_id: str
    family_version: str
    package: str
    plan_id: str = ATTEMPT_SETUP_PLAN_ID
    operations: tuple[str, ...] = ATTEMPT_SETUP_OPERATIONS

    def __post_init__(self) -> None:
        for name in ("family_id", "family_version", "package", "plan_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise RuntimeAttemptInputError("attempt_setup_plan_identity_invalid")
        if self.plan_id != ATTEMPT_SETUP_PLAN_ID:
            raise RuntimeAttemptInputError("attempt_setup_plan_id_invalid")
        if tuple(self.operations) != ATTEMPT_SETUP_OPERATIONS:
            raise RuntimeAttemptInputError("attempt_setup_plan_operations_invalid")

    @classmethod
    def from_document(
        cls,
        document: object,
        *,
        family_id: str,
        family_version: str,
        package: str,
    ) -> RuntimeAttemptSetupPlan:
        """Parse one strict projection ``setup_plan`` object and bind it."""
        if not isinstance(document, Mapping):
            raise RuntimeAttemptInputError("attempt_setup_plan_unavailable")
        if set(document) != {"id", "operations"}:
            raise RuntimeAttemptInputError("attempt_setup_plan_fields_invalid")
        plan_id = document["id"]
        operations = document["operations"]
        if not isinstance(plan_id, str):
            raise RuntimeAttemptInputError("attempt_setup_plan_id_invalid")
        if (
            not isinstance(operations, Sequence)
            or isinstance(operations, (str, bytes))
            or not all(isinstance(item, str) for item in operations)
        ):
            raise RuntimeAttemptInputError("attempt_setup_plan_operations_invalid")
        return cls(
            family_id=family_id,
            family_version=family_version,
            package=package,
            plan_id=plan_id,
            operations=tuple(operations),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.plan_id,
            "operations": list(self.operations),
            "family_id": self.family_id,
            "family_version": self.family_version,
            "package": self.package,
        }


@dataclass(frozen=True)
class DeviceCommandReceipt:
    """One recorded device command with its bounded raw output."""

    operation: str
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation:
            raise RuntimeAttemptError("device_command_operation_invalid")
        if not isinstance(self.command, tuple) or not self.command:
            raise RuntimeAttemptError("device_command_vector_invalid")
        if type(self.returncode) is not int:
            raise RuntimeAttemptError("device_command_returncode_invalid")
        if not isinstance(self.stdout, str) or not isinstance(self.stderr, str):
            raise RuntimeAttemptError("device_command_output_invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class DeviceProbeReceipt:
    """One recorded read-only device probe and its structured fields."""

    operation: str
    commands: tuple[tuple[str, ...], ...]
    returncodes: tuple[int, ...]
    outputs: tuple[str, ...]
    fields: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation:
            raise RuntimeAttemptError("device_probe_operation_invalid")
        if not isinstance(self.commands, tuple) or not self.commands:
            raise RuntimeAttemptError("device_probe_command_missing")
        if not (
            len(self.commands) == len(self.returncodes) == len(self.outputs)
        ):
            raise RuntimeAttemptError("device_probe_receipt_incomplete")
        if any(type(code) is not int for code in self.returncodes):
            raise RuntimeAttemptError("device_probe_returncode_invalid")
        if not isinstance(self.fields, Mapping):
            raise RuntimeAttemptError("device_probe_fields_invalid")

    def field(self, name: str) -> object:
        return self.fields.get(name)

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "commands": [list(command) for command in self.commands],
            "returncodes": list(self.returncodes),
            "outputs": list(self.outputs),
            "fields": dict(self.fields),
        }


class RuntimeAttemptDevice(Protocol):
    """The narrowed device surface one runtime attempt is admitted to use."""

    @property
    def serial(self) -> str:
        """Return the selected device serial."""

    @property
    def device_kind(self) -> str:
        """Return ``adb`` for production and ``recording`` for the fake."""

    @property
    def package(self) -> str:
        """Return the single target package this device is bound to."""

    @property
    def activity(self) -> str:
        """Return the single target launcher activity this device is bound to."""

    def probe_session(self) -> DeviceProbeReceipt:
        """Read the Runtime Device Session identity without launching the app."""

    def deploy_apk(
        self, *, apk_path: Path, package: str, activity: str
    ) -> DeviceCommandReceipt:
        """Deploy exactly the sealed APK through the Android CLI."""

    def read_installed_apk(self, package: str) -> DeviceProbeReceipt:
        """Read the installed APK path and bytes digest for one package."""

    def clear_package_data(self, package: str) -> DeviceCommandReceipt:
        """Clear one target package once and report the Android CLI result."""

    def target_process_ids(self, package: str) -> DeviceProbeReceipt:
        """Read the target package PIDs; ``fields['pids']`` is empty when absent."""

    def write_rotation_setting(self, *, name: str, value: int) -> DeviceCommandReceipt:
        """Write one allowed rotation setting exactly once."""

    def read_rotation_state(self) -> DeviceProbeReceipt:
        """Read the observed rotation state."""

    def clear_log_buffers(self) -> DeviceCommandReceipt:
        """Clear all log buffers once."""

    def write_log_marker(self, marker: str) -> DeviceCommandReceipt:
        """Write one attempt-bound marker line into the device log."""

    def dump_all_buffers_epoch(self) -> DeviceCommandReceipt:
        """Capture exactly one all-buffer epoch-formatted dump."""

    def canonical_launch(
        self, *, package: str, activity: str
    ) -> DeviceCommandReceipt:
        """Perform one serial-scoped canonical application launch."""

    def read_foreground_state(self) -> DeviceProbeReceipt:
        """Read the resumed foreground component, task, PID, and rotation."""

    def dispatch_orientation(self, rotation: int) -> DeviceCommandReceipt:
        """Dispatch exactly one orientation event."""

    def read_layout(self) -> LayoutObservation | CommandResult | str | list[object]:
        """Read one fresh device-scoped UI layout."""

    def tap(self, x: int, y: int) -> CommandResult:
        """Dispatch one tap at an already validated on-screen center."""

    def operation_counts(self) -> Mapping[str, int]:
        """Return per-operation invocation counts for the exactly-once proof."""

    def mutation_commands(self) -> Sequence[tuple[str, ...]]:
        """Return every recorded mutating command vector in dispatch order."""

    def mutation_operations(self) -> Sequence[tuple[str, tuple[str, ...]]]:
        """Return every mutating operation and vector in dispatch order."""


def _adb(serial: str, *args: str) -> tuple[str, ...]:
    return ("adb", "-s", serial, *args)


def session_probe_plan(
    serial: str,
) -> tuple[tuple[tuple[str, ...], str], ...]:
    """Return the admitted Runtime Device Session probes as (argv, field) pairs.

    The probe order is the recorded output order, so a recording device and the
    production adapter can never disagree about which value belongs to which
    identity field.
    """
    steps: list[tuple[tuple[str, ...], str]] = [
        (("android", "--version"), "android_cli_version"),
        (("adb", "version"), "adb_version"),
    ]
    props = (
        ("ro.boot.boot_id", "boot_id"),
        ("ro.build.version.sdk", "api_level"),
        ("ro.build.fingerprint", "fingerprint"),
        ("ro.product.cpu.abi", "abi"),
        ("ro.product.model", "model"),
        ("ro.product.hardware", "hardware"),
        ("ro.kernel.qemu.avd_name", "avd_name"),
        ("ro.boot.qemu.version", "emulator_version"),
        ("persist.sys.locale", "settings.locale"),
        ("persist.sys.timezone", "settings.timezone"),
    )
    steps.extend(
        (_adb(serial, "shell", "getprop", key), field) for key, field in props
    )
    for namespace, key in (
        ("system", "font_scale"),
        ("system", "ui_night_mode"),
        ("global", "window_animation_scale"),
        ("global", "transition_animation_scale"),
        ("global", "animator_duration_scale"),
        ("secure", "navigation_mode"),
        ("secure", "default_input_method"),
        ("secure", "enabled_accessibility_services"),
    ):
        steps.append(
            (
                _adb(serial, "shell", "settings", "get", namespace, key),
                f"settings.{key}",
            )
        )
    steps.append((_adb(serial, "shell", "wm", "size"), "display_size"))
    steps.append((_adb(serial, "shell", "wm", "density"), "display_density"))
    return tuple(steps)


def session_probe_vectors(serial: str) -> tuple[tuple[str, ...], ...]:
    """Return the admitted Runtime Device Session probe vectors."""
    return tuple(argv for argv, _ in session_probe_plan(serial))


def launch_component(package: str, activity: str) -> str:
    """Return the exact canonical component string used by every launch vector."""
    return f"{package}/{activity}"


def deployment_vector(
    serial: str, *, apk_path: Path, package: str, activity: str
) -> tuple[str, ...]:
    """Return the admitted Android CLI deployment vector for one sealed APK."""
    return (
        "android",
        "run",
        f"--device={serial}",
        f"--apks={apk_path}",
        f"--activity={launch_component(package, activity)}",
        "--type=ACTIVITY",
    )


def installed_apk_vectors(serial: str, package: str) -> tuple[tuple[str, ...], ...]:
    """Return the admitted installed-byte verification vectors."""
    return (
        _adb(serial, "shell", "pm", "path", package),
        _adb(serial, "shell", "pm", "list", "packages", "-f", package),
    )


def clear_package_data_vector(serial: str, package: str) -> tuple[str, ...]:
    return _adb(serial, "shell", "pm", "clear", package)


def target_process_vector(serial: str, package: str) -> tuple[str, ...]:
    return _adb(serial, "shell", "pidof", package)


def rotation_setting_vector(serial: str, name: str, value: int) -> tuple[str, ...]:
    return _adb(serial, "shell", "settings", "put", "system", name, str(value))


def rotation_state_vectors(serial: str) -> tuple[tuple[str, ...], ...]:
    return tuple(
        _adb(serial, "shell", "settings", "get", "system", name)
        for name in ALLOWED_ROTATION_SETTINGS
    ) + (_adb(serial, "shell", "dumpsys", "display"),)


def clear_log_buffers_vector(serial: str) -> tuple[str, ...]:
    return _adb(serial, "logcat", "-b", "all", "-c")


def log_marker_vector(serial: str, marker: str) -> tuple[str, ...]:
    return _adb(serial, "shell", "log", "-t", MARKER_TAG, marker)


def dump_all_buffers_vector(serial: str) -> tuple[str, ...]:
    return _adb(serial, "logcat", "-d", "-b", "all", "-v", LOG_WINDOW_FORMAT)


def canonical_launch_vector(serial: str, package: str, activity: str) -> tuple[str, ...]:
    return _adb(
        serial,
        "shell",
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.MAIN",
        "-c",
        "android.intent.category.LAUNCHER",
        "-n",
        f"{package}/{activity}",
    )


def foreground_state_vectors(
    serial: str, package: str
) -> tuple[tuple[str, ...], ...]:
    """Return the admitted foreground component, PID, and rotation vectors."""
    return (
        _adb(serial, "shell", "dumpsys", "activity", "activities"),
        _adb(serial, "shell", "pidof", package),
        _adb(serial, "shell", "dumpsys", "display"),
    )


def orientation_dispatch_vector(serial: str, rotation: int) -> tuple[str, ...]:
    return rotation_setting_vector(serial, "user_rotation", rotation)


def layout_vector(serial: str) -> tuple[str, ...]:
    return ("android", "layout", f"--device={serial}", "--pretty")


def tap_vector(serial: str, x: int, y: int) -> tuple[str, ...]:
    return _adb(serial, "shell", "input", "tap", str(x), str(y))


__all__ = [
    "ACCOUNTABLE_CONCLUDED",
    "ALLOWED_ROTATION_SETTINGS",
    "ARTIFACTS_DIRNAME",
    "ATTEMPT_SETUP_OPERATIONS",
    "ATTEMPT_SETUP_PLAN_ID",
    "BOUNDARY_LAYOUT_FILENAME",
    "BOUNDARY_PRECONDITION_TEXT",
    "CLAIM_BOUNDARY",
    "EXPECTED_DEVICE_MUTATION_COUNTS",
    "EXPECTED_DEVICE_READ_COUNTS",
    "EXPECTED_ORIENTATION",
    "EXPECTED_ORIENTATION_EVENT",
    "FROZEN_TAP_TRAJECTORY",
    "INPUT_RESOURCE_ID",
    "JOURNEY_ACTION_STATUS_PASSED",
    "JOURNEY_DIRNAME",
    "JOURNEY_SEGMENT_ID",
    "L1_OUTCOME_FAIL",
    "L1_OUTCOME_INCONCLUSIVE",
    "L2_OUTCOME_FAIL",
    "L2_OUTCOME_INCONCLUSIVE",
    "L2_OUTCOME_PASS",
    "LANDSCAPE_ROTATION",
    "LAUNCH_SETTLE_SECONDS",
    "LAUNCH_STATUS_TOKEN",
    "LIFECYCLE_END",
    "LIFECYCLE_EVENT_EXCERPT_CHARS",
    "LIFECYCLE_EVENT_TERMS",
    "LIFECYCLE_POLL_BUDGET",
    "LIFECYCLE_POLL_INTERVAL_SECONDS",
    "LIFECYCLE_POLL_SECONDS",
    "LIFECYCLE_RELAUNCH_TAG",
    "LIFECYCLE_SIGNATURE_EVENTS",
    "LIFECYCLE_SIGNATURE_ID",
    "LIFECYCLE_SIGNATURE_STATUS",
    "LIFECYCLE_START",
    "LIFECYCLE_WINDOW_FILENAME",
    "LOG_WINDOW_BUFFERS",
    "LOG_WINDOW_FORMAT",
    "MARKER_TAG",
    "MINIMUM_LAYOUT_READ_COUNT",
    "MINIMUM_TAP_COUNT",
    "NON_ACCOUNTABLE",
    "PHASE_FAILURE_REASONS",
    "PORTRAIT_ROTATION",
    "POST_EVENT_LAYOUT_FILENAME",
    "PROCESS_DEATH_TEMPLATES",
    "PROCESS_START_TEMPLATE",
    "PROVENANCE_KIND",
    "RECEIPT_FILENAME",
    "RECORD_FILENAME",
    "REPORTED_COMPONENT_PREFIX",
    "REQUIRED_ACCOUNTABLE_COMPONENTS",
    "SCHEMA_VERSION",
    "SEAM",
    "SESSION_IDENTITY_SETTINGS",
    "SESSION_REQUIRED_FIELDS",
    "SETUP_SETTLE_SECONDS",
    "SETUP_SUCCESS_TOKEN",
    "SHARED_FAILURE_REASONS",
    "TARGET_LOG_WINDOW_FILENAME",
    "TARGET_WINDOW_END",
    "TARGET_WINDOW_START",
    "AdbRuntimeDevice",
    "DeviceCommandReceipt",
    "DeviceProbeReceipt",
    "RecordingDevicePolicy",
    "RecordingRuntimeDevice",
    "RuntimeAttemptDevice",
    "RuntimeAttemptDeviceError",
    "RuntimeAttemptError",
    "RuntimeAttemptInputError",
    "RuntimeAttemptReceipt",
    "RuntimeAttemptRequest",
    "RuntimeAttemptSetupPlan",
    "RuntimeAttemptVerificationError",
    "attempt_marker",
    "canonical_bytes",
    "canonical_launch_vector",
    "canonical_sha256",
    "clear_log_buffers_vector",
    "clear_package_data_vector",
    "component_matches",
    "component_parts",
    "deployment_vector",
    "display_device_info",
    "display_size",
    "dump_all_buffers_vector",
    "execute_runtime_attempt",
    "expected_device_mutation_order",
    "expected_device_read_counts",
    "foreground_state_vectors",
    "input_nodes",
    "installed_apk_vectors",
    "launch_component",
    "layout_command",
    "layout_nodes",
    "layout_stdout",
    "layout_vector",
    "log_marker_vector",
    "node_bounds",
    "node_center",
    "node_contains",
    "node_is_clickable",
    "node_resource_id",
    "node_text",
    "orientation_dispatch_vector",
    "resource_id_matches",
    "rotation_setting_vector",
    "rotation_state_vectors",
    "session_probe_plan",
    "session_probe_vectors",
    "tap_vector",
    "target_process_vector",
    "verify_runtime_attempt",
]

# ---------------------------------------------------------------------------
# Layout parsing
# ---------------------------------------------------------------------------


class _DuplicateJsonKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_layout_text(text: str) -> list[dict[str, object]]:
    if not isinstance(text, str):
        raise RuntimeAttemptError("layout_response_invalid")
    try:
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (_DuplicateJsonKeyError, json.JSONDecodeError) as error:
        raise RuntimeAttemptError("layout_malformed") from error
    if not isinstance(value, list) or not all(
        isinstance(node, dict) for node in value
    ):
        raise RuntimeAttemptError("layout_malformed")
    return value


def layout_nodes(raw: object) -> list[dict[str, object]]:
    """Parse one read-only layout response into JSON nodes."""
    if isinstance(raw, LayoutObservation):
        if raw.returncode != 0:
            raise RuntimeAttemptError("layout_command_failed")
        return _parse_layout_text(raw.stdout)
    if isinstance(raw, CommandResult):
        if raw.returncode != 0:
            raise RuntimeAttemptError("layout_command_failed")
        return _parse_layout_text(raw.stdout)
    if isinstance(raw, str):
        return _parse_layout_text(raw)
    if isinstance(raw, list):
        if not all(isinstance(node, dict) for node in raw):
            raise RuntimeAttemptError("layout_malformed")
        return [dict(node) for node in raw]
    raise RuntimeAttemptError("layout_response_invalid")


def layout_command(raw: object) -> tuple[str, ...]:
    """Return the exact command of one read-only layout response."""
    if isinstance(raw, LayoutObservation):
        return tuple(raw.command)
    if isinstance(raw, CommandResult):
        return tuple(raw.args)
    return ()


def layout_stdout(raw: object) -> str:
    """Return the exact stdout bytes identity of one layout response."""
    if isinstance(raw, (LayoutObservation, CommandResult)):
        return raw.stdout
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return json.dumps(raw, ensure_ascii=False)
    raise RuntimeAttemptError("layout_response_invalid")


def node_resource_id(node: Mapping[str, object]) -> str:
    """Return one node's resource ID in its short or fully qualified form."""
    value = node.get("resource-id", node.get("resourceId"))
    return value if isinstance(value, str) else ""


def resource_id_matches(node: Mapping[str, object], expected: str) -> bool:
    actual = node_resource_id(node)
    return bool(actual) and (
        actual == expected or actual.endswith(f":id/{expected}")
    )


def node_text(node: Mapping[str, object]) -> str:
    """Return the node text; an omitted key is Android CLI's empty text."""
    value = node.get("text")
    return value if isinstance(value, str) else ""


def node_bounds(node: Mapping[str, object]) -> tuple[int, int, int, int] | None:
    value = node.get("bounds")
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\[\s*(\d+)\s*,\s*(\d+)\s*\]\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]",
        value.strip(),
    )
    if match is None:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    if left > right or top > bottom:
        return None
    return left, top, right, bottom


def node_center(node: Mapping[str, object]) -> tuple[int, int] | None:
    value = node.get("center")
    if isinstance(value, str):
        match = re.fullmatch(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]", value.strip())
        if match is None:
            return None
        return int(match.group(1)), int(match.group(2))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        x, y = value
        if type(x) is int and type(y) is int and x >= 0 and y >= 0:
            return x, y
    return None


def node_is_clickable(node: Mapping[str, object]) -> bool:
    interactions = node.get("interactions")
    return isinstance(interactions, list) and "clickable" in interactions


def node_contains(node: Mapping[str, object], x: int, y: int) -> bool:
    bounds = node_bounds(node)
    if bounds is None:
        return False
    left, top, right, bottom = bounds
    return left <= x <= right and top <= y <= bottom


def input_nodes(nodes: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Return every layout node carrying the frozen input resource ID."""
    return [node for node in nodes if resource_id_matches(node, INPUT_RESOURCE_ID)]


# ---------------------------------------------------------------------------
# Exactly-once device bookkeeping
# ---------------------------------------------------------------------------


class _DeviceOperationLog:
    """Shared invocation accounting for Runtime Attempt Devices."""

    def __init__(self, *, fail_operations: frozenset[str] = frozenset()) -> None:
        self._counts: dict[str, int] = {}
        self._mutations: list[tuple[str, tuple[str, ...]]] = []
        self._operations: list[str] = []
        self._failures = frozenset(fail_operations)

    def check(self, operation: str) -> None:
        """Refuse a simulated failure before the operation has any effect."""
        if operation in self._failures:
            raise RuntimeAttemptDeviceError(
                operation, f"{operation} is not available on this device"
            )

    def count(self, operation: str) -> None:
        self._counts[operation] = self._counts.get(operation, 0) + 1
        self._operations.append(operation)

    def record_mutation(self, operation: str, command: Sequence[str]) -> None:
        self._mutations.append((operation, tuple(command)))

    def begin(self, operation: str, *, mutation: Sequence[str] | None = None) -> None:
        self.check(operation)
        self.count(operation)
        if mutation is not None:
            self.record_mutation(operation, mutation)

    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def mutations(self) -> tuple[tuple[str, ...], ...]:
        return tuple(command for _, command in self._mutations)

    def mutation_log(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return tuple(self._mutations)

    def operations(self) -> tuple[str, ...]:
        return tuple(self._operations)


# ---------------------------------------------------------------------------
# Recording device
# ---------------------------------------------------------------------------

_KEYPAD_ROWS: tuple[tuple[str, ...], ...] = (
    ("clearButton", "percentButton", "deleteButton", "divideButton"),
    ("sevenButton", "eightButton", "nineButton", "multiplyButton"),
    ("fourButton", "fiveButton", "sixButton", "subtractButton"),
    ("oneButton", "twoButton", "threeButton", "addButton"),
    ("zeroButton", "decimalButton", "parenthesesButton", "equalsButton"),
)
_KEY_TEXT: Mapping[str, str] = {
    "zeroButton": "0",
    "oneButton": "1",
    "twoButton": "2",
    "threeButton": "3",
    "fourButton": "4",
    "fiveButton": "5",
    "sixButton": "6",
    "sevenButton": "7",
    "eightButton": "8",
    "nineButton": "9",
    "decimalButton": ".",
    "addButton": "+",
    "subtractButton": "-",
    "multiplyButton": "*",
    "divideButton": "/",
    "percentButton": "%",
    "parenthesesButton": "(",
}
_KEY_COMMANDS = frozenset({"clearButton", "deleteButton", "equalsButton"})
_INPUT_MAX_LENGTH = 128
_DISPLAY_PORTRAIT = (1080, 2400)
_DISPLAY_LANDSCAPE = (2400, 1080)
_REPLAY_PID = 4321


def display_size(landscape: bool) -> tuple[int, int]:
    """Return the recorded display size for one orientation."""
    return _DISPLAY_LANDSCAPE if landscape else _DISPLAY_PORTRAIT


def display_device_info(*, rotation: int, landscape: bool) -> str:
    """Return one recorded ``dumpsys display`` device line for one rotation."""
    width, height = display_size(landscape)
    return (
        'DisplayDeviceInfo{"Built-in Screen": uniqueId="local:0", '
        f"{width} x {height}, modeId 1, renderFrameRate 60.0, "
        f"rotation {rotation}, density 420, state ON, type INTERNAL}}"
    )


def _keypad_nodes(*, landscape: bool, input_text: str) -> list[dict[str, object]]:
    """Build the recorded OpenCalc surface for one orientation."""
    width, height = display_size(landscape)
    margin = 40
    gutter = 16
    input_top = int(height * 0.04)
    input_bottom = int(height * 0.12)
    input_node: dict[str, object] = {
        "resource-id": INPUT_RESOURCE_ID,
        "center": f"[{width // 2},{(input_top + input_bottom) // 2}]",
        "bounds": f"[{margin},{input_top}][{width - margin},{input_bottom}]",
        "interactions": [],
    }
    if input_text:
        input_node["text"] = input_text
    rows = len(_KEYPAD_ROWS)
    columns = len(_KEYPAD_ROWS[0])
    area_top = int(height * 0.18)
    area_bottom = int(height * 0.96)
    column_width = (width - 2 * margin) / columns
    row_height = (area_bottom - area_top) / rows
    nodes: list[dict[str, object]] = [input_node]
    for row_index, row in enumerate(_KEYPAD_ROWS):
        for column_index, resource_id in enumerate(row):
            left = int(margin + column_index * column_width)
            right = int(left + column_width - gutter)
            top = int(area_top + row_index * row_height)
            bottom = int(top + row_height - gutter)
            nodes.append(
                {
                    "resource-id": resource_id,
                    "center": f"[{(left + right) // 2},{(top + bottom) // 2}]",
                    "bounds": f"[{left},{top}][{right},{bottom}]",
                    "interactions": ["clickable"],
                }
            )
    return nodes


def _abbreviate_component(package: str, activity: str) -> str:
    if activity.startswith(f"{package}."):
        return f"{package}/{activity[len(package):]}"
    return f"{package}/{activity}"


def component_parts(value: object) -> tuple[str, str] | None:
    """Expand one reported component into its exact package and activity."""
    if not isinstance(value, str) or "/" not in value:
        return None
    package, activity = value.split("/", 1)
    if not package or not activity:
        return None
    if activity.startswith("."):
        activity = f"{package}{activity}"
    return package, activity


def component_matches(value: object, *, package: str, activity: str) -> bool:
    """Return whether one reported component is the exact frozen component."""
    parts = component_parts(value)
    return parts == (package, activity)


@dataclass(frozen=True)
class RecordingDevicePolicy:
    """Bounded, explicit simulation policy for the recording device."""

    serial: str = "recording-device"
    save_enabled: bool = True
    orientation_settle_polls: int = 2
    inject_target_crash: bool = False
    restart_target_process: bool = False
    clear_output: str = "Success"
    installed_digest_override: str | None = None
    fail_operations: frozenset[str] = frozenset()
    pid: int = 4501
    task_id: int = 7

    def __post_init__(self) -> None:
        if not isinstance(self.serial, str) or not self.serial:
            raise RuntimeAttemptError("recording_device_serial_invalid")
        if self.orientation_settle_polls < 1:
            raise RuntimeAttemptError("recording_device_settle_invalid")
        if self.installed_digest_override is not None:
            _require_digest(
                self.installed_digest_override, "recording_device_digest_invalid"
            )


class RecordingRuntimeDevice:
    """Bounded recording simulation of one OpenCalc runtime attempt device.

    The recording device is test and diagnostics infrastructure.  Its layout,
    log, and lifecycle lines are recorded simulation text, not device
    evidence: ``device_kind`` is ``recording`` and the attempt receipt binds the
    preparation handoff's ``test_substitutes`` marker next to it.
    """

    device_kind = "recording"

    def __init__(
        self,
        *,
        policy: RecordingDevicePolicy | None = None,
        package: str = "",
        activity: str = "",
        session_fields: Mapping[str, object] | None = None,
    ) -> None:
        self.policy = policy or RecordingDevicePolicy()
        self._operations = _DeviceOperationLog(
            fail_operations=self.policy.fail_operations
        )
        if session_fields is not None:
            self._session_fields = dict(session_fields)
            if package:
                self._session_fields["package"] = package
            if activity:
                self._session_fields["activity"] = activity
        else:
            self._session_fields = _session_fields(
                serial=self.policy.serial, package=package, activity=activity
            )
        self._session_fields["serial"] = self.policy.serial
        self._launched = False
        self._pid: int | None = None
        self._installed_digest: str | None = None
        self._installed_bytes = 0
        self._input: list[str] = []
        self._settings: dict[str, int] = {
            "accelerometer_rotation": 1,
            "user_rotation": 0,
        }
        self._rotation = PORTRAIT_ROTATION
        self._landscape = False
        self._settle_pending = 0
        self._log: list[str] = []
        self._epoch = 1783693058.0
        self._markers: list[str] = []

    # -- identity -----------------------------------------------------------

    @property
    def serial(self) -> str:
        return self.policy.serial

    @property
    def package(self) -> str:
        return str(self._session_fields.get("package", ""))

    @property
    def activity(self) -> str:
        return str(self._session_fields.get("activity", ""))

    def operation_counts(self) -> Mapping[str, int]:
        return self._operations.counts()

    def mutation_commands(self) -> Sequence[tuple[str, ...]]:
        return self._operations.mutations()

    def mutation_operations(self) -> Sequence[tuple[str, tuple[str, ...]]]:
        return self._operations.mutation_log()

    def operations(self) -> Sequence[str]:
        return self._operations.operations()

    def _check_package(self, operation: str, package: str) -> None:
        if package != self.package:
            raise RuntimeAttemptDeviceError(
                operation, f"{package!r} is not the bound target package"
            )

    def _check_target(self, operation: str, package: str, activity: str) -> None:
        self._check_package(operation, package)
        if activity != self.activity:
            raise RuntimeAttemptDeviceError(
                operation, f"{activity!r} is not the bound target activity"
            )

    def log_lines(self) -> tuple[str, ...]:
        return tuple(self._log)

    def markers(self) -> tuple[str, ...]:
        return tuple(self._markers)

    # -- recorded surface ---------------------------------------------------

    def _tick(self, seconds: float = 0.05) -> str:
        self._epoch += seconds
        return f"{self._epoch:.3f}"

    def _append(self, level: str, tag: str, message: str) -> None:
        pid = self._pid if self._pid is not None else _REPLAY_PID
        self._log.append(f"{self._tick()}  {pid}  {pid} {level} {tag}: {message}")

    def _input_text(self) -> str:
        return "".join(self._input)

    def _layout(self) -> list[dict[str, object]]:
        if not self._launched:
            return []
        return _keypad_nodes(landscape=self._landscape, input_text=self._input_text())

    def _node_at(self, x: int, y: int) -> Mapping[str, object] | None:
        matches = [
            node
            for node in self._layout()
            if node_resource_id(node) != INPUT_RESOURCE_ID
            and node_contains(node, x, y)
        ]
        return matches[0] if len(matches) == 1 else None

    def _apply_key(self, resource_id: str) -> None:
        if resource_id == "clearButton":
            self._input.clear()
            return
        if resource_id == "deleteButton":
            if self._input:
                self._input.pop()
            return
        if resource_id in _KEY_COMMANDS:
            return
        key = _KEY_TEXT.get(resource_id)
        if key is None or len(self._input) >= _INPUT_MAX_LENGTH:
            return
        self._input.append(key)

    # -- protocol -----------------------------------------------------------

    def probe_session(self) -> DeviceProbeReceipt:
        self._operations.begin("probe_session")
        plan = session_probe_plan(self.serial)
        fields = dict(self._session_fields)
        settings = fields.get("settings")
        recorded = dict(settings) if isinstance(settings, Mapping) else {}
        outputs: list[str] = []
        for _, field_name in plan:
            if field_name.startswith("settings."):
                outputs.append(f"{recorded.get(field_name[len('settings.'):], '')}\n")
                continue
            outputs.append(_recorded_probe_output(field_name, fields))
        return DeviceProbeReceipt(
            operation="probe_session",
            commands=tuple(argv for argv, _ in plan),
            returncodes=tuple(0 for _ in plan),
            outputs=tuple(outputs),
            fields=fields,
        )

    def deploy_apk(
        self, *, apk_path: Path, package: str, activity: str
    ) -> DeviceCommandReceipt:
        self._check_target("deploy_apk", package, activity)
        vector = deployment_vector(
            self.serial, apk_path=apk_path, package=package, activity=activity
        )
        self._operations.begin("deploy_apk", mutation=vector)
        try:
            payload = Path(apk_path).read_bytes()
        except OSError as error:
            raise RuntimeAttemptDeviceError("deploy_apk", str(error)) from error
        self._installed_bytes = len(payload)
        self._installed_digest = _sha256_bytes(payload)
        self._launched = True
        self._pid = _REPLAY_PID
        self._append(
            "I",
            "ActivityTaskManager",
            "START u0 {act=android.intent.action.MAIN "
            'cat=[android.intent.category.LAUNCHER] flg=0x10200000 '
            f"cmp={_abbreviate_component(package, activity)}}} from uid 2000",
        )
        self._append(
            "I",
            "ActivityManager",
            f"Start proc {self._pid}:{package}/u0a123 for activity "
            f"{{{_abbreviate_component(package, activity)}}}",
        )
        return DeviceCommandReceipt(
            operation="deploy_apk",
            command=vector,
            returncode=0,
            stdout="Success\n",
        )

    def read_installed_apk(self, package: str) -> DeviceProbeReceipt:
        self._check_package("read_installed_apk", package)
        self._operations.begin("read_installed_apk")
        vectors = installed_apk_vectors(self.serial, package)
        install_path = f"/data/app/~~recording/{package}-recording/base.apk"
        digest = self.policy.installed_digest_override or self._installed_digest
        if digest is None:
            raise RuntimeAttemptDeviceError(
                "read_installed_apk", "no installed APK bytes were recorded"
            )
        return DeviceProbeReceipt(
            operation="read_installed_apk",
            commands=vectors,
            returncodes=(0, 0),
            outputs=(f"package:{install_path}", f"package:{install_path}"),
            fields={
                "paths": [install_path],
                "sha256": digest,
                "bytes": self._installed_bytes,
            },
        )

    def clear_package_data(self, package: str) -> DeviceCommandReceipt:
        self._check_package("clear_package_data", package)
        vector = clear_package_data_vector(self.serial, package)
        self._operations.begin("clear_package_data", mutation=vector)
        self._launched = False
        self._pid = None
        self._input.clear()
        self._landscape = False
        self._rotation = PORTRAIT_ROTATION
        self._settle_pending = 0
        return DeviceCommandReceipt(
            operation="clear_package_data",
            command=vector,
            returncode=0,
            stdout=f"{self.policy.clear_output}\n",
        )

    def target_process_ids(self, package: str) -> DeviceProbeReceipt:
        self._check_package("target_process_ids", package)
        self._operations.begin("target_process_ids")
        vector = target_process_vector(self.serial, package)
        pids = () if self._pid is None else (self._pid,)
        return DeviceProbeReceipt(
            operation="target_process_ids",
            commands=(vector,),
            returncodes=(0 if pids else 1,),
            outputs=(" ".join(str(pid) for pid in pids),),
            fields={"pids": list(pids)},
        )

    def write_rotation_setting(self, *, name: str, value: int) -> DeviceCommandReceipt:
        if name not in ALLOWED_ROTATION_SETTINGS:
            raise RuntimeAttemptDeviceError(
                "write_rotation_setting", f"setting {name} is not allowed"
            )
        if value not in (PORTRAIT_ROTATION, LANDSCAPE_ROTATION):
            raise RuntimeAttemptDeviceError(
                "write_rotation_setting", f"rotation value {value} is not allowed"
            )
        vector = rotation_setting_vector(self.serial, name, value)
        self._operations.begin("write_rotation_setting", mutation=vector)
        self._settings[name] = value
        return DeviceCommandReceipt(
            operation="write_rotation_setting", command=vector, returncode=0
        )

    def read_rotation_state(self) -> DeviceProbeReceipt:
        self._operations.begin("read_rotation_state")
        vectors = rotation_state_vectors(self.serial)
        width, height = display_size(self._landscape)
        return DeviceProbeReceipt(
            operation="read_rotation_state",
            commands=vectors,
            returncodes=tuple(0 for _ in vectors),
            outputs=(
                str(self._settings["accelerometer_rotation"]),
                str(self._settings["user_rotation"]),
                display_device_info(rotation=self._rotation, landscape=self._landscape),
            ),
            fields={
                "accelerometer_rotation": self._settings["accelerometer_rotation"],
                "user_rotation": self._settings["user_rotation"],
                "rotation": self._rotation,
                "portrait": not self._landscape,
                "display_size": f"{width}x{height}",
            },
        )

    def clear_log_buffers(self) -> DeviceCommandReceipt:
        vector = clear_log_buffers_vector(self.serial)
        self._operations.begin("clear_log_buffers", mutation=vector)
        self._log.clear()
        self._markers.clear()
        return DeviceCommandReceipt(
            operation="clear_log_buffers", command=vector, returncode=0
        )

    def write_log_marker(self, marker: str) -> DeviceCommandReceipt:
        vector = log_marker_vector(self.serial, marker)
        self._operations.begin("write_log_marker", mutation=vector)
        self._markers.append(marker)
        self._append("I", MARKER_TAG, marker)
        return DeviceCommandReceipt(
            operation="write_log_marker", command=vector, returncode=0
        )

    def dump_all_buffers_epoch(self) -> DeviceCommandReceipt:
        vector = dump_all_buffers_vector(self.serial)
        self._operations.begin("dump_all_buffers_epoch")
        payload = "\n".join(self._log)
        return DeviceCommandReceipt(
            operation="dump_all_buffers_epoch",
            command=vector,
            returncode=0,
            stdout=f"{payload}\n" if payload else "",
        )

    def canonical_launch(
        self, *, package: str, activity: str
    ) -> DeviceCommandReceipt:
        self._check_target("canonical_launch", package, activity)
        vector = canonical_launch_vector(self.serial, package, activity)
        self._operations.begin("canonical_launch", mutation=vector)
        self._launched = True
        self._pid = self.policy.pid
        self._append(
            "I",
            "ActivityManager",
            f"Start proc {self._pid}:{package}/u0a123 for activity "
            f"{{{_abbreviate_component(package, activity)}}}",
        )
        self._append(
            "I",
            "ActivityTaskManager",
            f"Displayed {_abbreviate_component(package, activity)}: +412ms",
        )
        if self.policy.inject_target_crash:
            self._append("E", "AndroidRuntime", "FATAL EXCEPTION: main")
            self._append(
                "E", "AndroidRuntime", f"Process: {package}, PID: {self._pid}"
            )
            self._append(
                "E",
                "AndroidRuntime",
                "java.lang.IllegalStateException: recorded target crash",
            )
            self._append(
                "E",
                "AndroidRuntime",
                f"\tat {package}.activities.MainActivity.onCreate(MainActivity.kt:1)",
            )
        abbreviated = _abbreviate_component(package, activity)
        return DeviceCommandReceipt(
            operation="canonical_launch",
            command=vector,
            returncode=0,
            stdout=(
                "Starting: Intent { act=android.intent.action.MAIN "
                f"cat=[android.intent.category.LAUNCHER] cmp={abbreviated} }}\n"
                "Status: ok\n"
                "LaunchState: COLD\n"
                f"Activity: {abbreviated}\n"
                "TotalTime: 412\n"
                "WaitTime: 430\n"
            ),
        )

    def read_foreground_state(self) -> DeviceProbeReceipt:
        self._operations.begin("read_foreground_state")
        vectors = foreground_state_vectors(self.serial, self.package)
        if self._settle_pending:
            self._settle_pending -= 1
            if not self._settle_pending:
                self._settle_landscape()
        width, height = display_size(self._landscape)
        component = (
            _abbreviate_component(self.package, self.activity)
            if self.package and self.activity
            else ""
        )
        pids = () if self._pid is None else (self._pid,)
        return DeviceProbeReceipt(
            operation="read_foreground_state",
            commands=vectors,
            returncodes=(0, 0 if pids else 1, 0),
            outputs=(
                f"mResumedActivity: ActivityRecord{{{component} t{self.policy.task_id}}}",
                " ".join(str(pid) for pid in pids),
                display_device_info(rotation=self._rotation, landscape=self._landscape),
            ),
            fields={
                "component": component,
                "task_id": self.policy.task_id,
                "pid": self._pid,
                "rotation": self._rotation,
                "landscape": self._landscape,
                "display_size": f"{width}x{height}",
                "resumed": self._launched,
            },
        )

    def dispatch_orientation(self, rotation: int) -> DeviceCommandReceipt:
        if rotation != LANDSCAPE_ROTATION:
            raise RuntimeAttemptDeviceError(
                "dispatch_orientation", "only one landscape dispatch is admitted"
            )
        vector = orientation_dispatch_vector(self.serial, rotation)
        self._operations.begin("dispatch_orientation", mutation=vector)
        self._settings["user_rotation"] = rotation
        self._settle_pending = self.policy.orientation_settle_polls
        return DeviceCommandReceipt(
            operation="dispatch_orientation", command=vector, returncode=0
        )

    def _settle_landscape(self) -> None:
        package = self.package
        activity = self.activity
        component = _abbreviate_component(package, activity)
        token = "2a4b1c"
        self._append(
            "I",
            "ActivityTaskManager",
            f"Config changes=480 {{1.0 1.5 1.0}} for ActivityRecord{{{token} u0 "
            f"{component} t{self.policy.task_id}}}",
        )
        self._append(
            "I",
            "ActivityTaskManager",
            f"Relaunching ActivityRecord{{{token} u0 {component} "
            f"t{self.policy.task_id}}} due to config changes",
        )
        self._append("I", "am_on_destroy_called", f"[0,{component},performDestroy,126]")
        self._append("I", "am_on_create_called", f"[0,{component},performCreate,254]")
        self._append("I", "am_on_resume_called", f"[0,{component},RESUME_ACTIVITY,80]")
        if self.policy.restart_target_process and self._pid is not None:
            self._append(
                "I", "ActivityManager", f"Process {package} (pid {self._pid}) has died"
            )
            self._pid = self.policy.pid + 1
            self._append(
                "I",
                "ActivityManager",
                f"Start proc {self._pid}:{package}/u0a123 for activity {{{component}}}",
            )
        if not self.policy.save_enabled:
            self._input.clear()
        self._rotation = LANDSCAPE_ROTATION
        self._landscape = True

    def read_layout(self) -> LayoutObservation:
        self._operations.begin("read_layout")
        vector = layout_vector(self.serial)
        nodes = self._layout()
        return LayoutObservation(
            command=vector,
            stdout=json.dumps(nodes, ensure_ascii=False),
        )

    def tap(self, x: int, y: int) -> CommandResult:
        if type(x) is not int or type(y) is not int or x < 0 or y < 0:
            raise RuntimeAttemptDeviceError("tap", "tap coordinates are invalid")
        vector = tap_vector(self.serial, x, y)
        self._operations.begin("tap", mutation=vector)
        node = self._node_at(x, y)
        if node is not None:
            self._apply_key(node_resource_id(node))
        return CommandResult(
            args=list(vector), stdout="", stderr="", returncode=0
        )

    def set_installed_digest(self, digest: str) -> None:
        """Bind the digest the recording device reports for its installed APK."""
        self._installed_digest = _require_digest(
            digest, "recording_device_digest_invalid"
        )


def _recorded_probe_output(field_name: str, fields: Mapping[str, object]) -> str:
    """Return the recorded probe output for one session identity field."""
    if field_name == "android_cli_version":
        return "Android CLI 1.0.15498356\n"
    if field_name == "adb_version":
        return (
            "Android Debug Bridge version 1.0.41\n"
            "Version 35.0.2-android-tools\n"
        )
    if field_name == "display_size":
        return f"Physical size: {fields.get('display_size', '')}\n"
    if field_name == "display_density":
        return f"Physical density: {fields.get('display_density', '')}\n"
    return f"{fields.get(field_name, '')}\n"


def _session_fields(
    *,
    serial: str = "recording-device",
    package: str = "",
    activity: str = "",
) -> dict[str, object]:
    """Return one complete recorded Runtime Device Session identity."""
    return {
        "serial": serial,
        "package": package,
        "activity": activity,
        "boot_id": "8f4d1f2c-6c1f-4a4a-9a2b-4e6a9a24d1f0",
        "android_cli_version": "1.0.15498356",
        "emulator_version": "35.6.10 (stable)",
        "adb_version": "1.0.41 (35.0.2-android-tools)",
        "avd_name": "aiverify_api35",
        "avd_config_sha256": "1" * 64,
        "system_image_manifest_sha256": "2" * 64,
        "api_level": 35,
        "fingerprint": (
            "google/sdk_gphone64_arm64/emu64a:15/AP3A.241005.015/"
            "12313591:userdebug/dev-keys"
        ),
        "abi": "arm64-v8a",
        "model": "sdk_gphone64_arm64",
        "hardware": "ranchu",
        "display_size": "1080x2400",
        "display_density": "420",
        "settings": {
            "locale": "en-US",
            "timezone": "UTC",
            "font_scale": "1.0",
            "window_animation_scale": "1.0",
            "transition_animation_scale": "1.0",
            "animator_duration_scale": "1.0",
            "ui_night_mode": "1",
            "navigation_mode": "0",
            "default_input_method": (
                "com.google.android.inputmethod.latin/.LatinIME"
            ),
            "enabled_accessibility_services": "",
        },
    }


# ---------------------------------------------------------------------------
# Production device adapter
# ---------------------------------------------------------------------------

_PROP_LINE = re.compile(r"^\[(?P<key>[^\]]+)\]:\s*\[(?P<value>.*)\]\s*$")
_VERSION_TOKEN = re.compile(r"\d+\.\d+[0-9A-Za-z.\-]*")
_RESUMED_LINE = re.compile(r"mResumedActivity|topResumedActivity|mFocusedApp")
_COMPONENT_TOKEN = re.compile(r"([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)")
_TASK_TOKEN = re.compile(r"\bt(\d+)\b")
_SIZE_TOKEN = re.compile(r"(\d+)\s*x\s*(\d+)")
_DENSITY_TOKEN = re.compile(r"(?:density|dpi)\s+(\d+)")
_ROTATION_TOKEN = re.compile(r"\brotation\s+(\d)\b")
_DISPLAY_DEVICE_TOKEN = "DisplayDeviceInfo{"
_DISPLAY_DEVICE_WINDOW = 1000


def _getprop_value(output: str, key: str) -> str:
    """Return one ``getprop`` value or the empty string when it is absent."""
    for line in output.splitlines():
        match = _PROP_LINE.match(line.strip())
        if match is not None and match.group("key") == key:
            return match.group("value").strip()
    return ""


def _version_token(output: str) -> str:
    """Return the first dotted version token of one tool version output."""
    match = _VERSION_TOKEN.search(output)
    return match.group(0) if match is not None else ""


def _setting_value(output: str) -> str:
    """Return one ``settings get`` value; ``null`` and blanks are empty."""
    value = output.strip()
    return "" if value in {"", "null"} else value


def _display_device_window(output: str) -> str:
    """Return the bounded ``DisplayDeviceInfo`` window of one display dump."""
    index = output.find(_DISPLAY_DEVICE_TOKEN)
    if index < 0:
        return ""
    return output[index : index + _DISPLAY_DEVICE_WINDOW]


def _display_rotation_value(output: str) -> int | None:
    """Return the reported surface rotation, or ``None`` when unreported."""
    match = _ROTATION_TOKEN.search(_display_device_window(output))
    if match is None:
        return None
    return int(match.group(1))


def _display_size_value(output: str) -> str:
    """Return the reported ``WxH`` display size, or the empty string."""
    window = _display_device_window(output)
    match = _SIZE_TOKEN.search(window)
    if match is None:
        return ""
    return f"{match.group(1)}x{match.group(2)}"


def _display_density_value(output: str) -> str:
    """Return the reported display density, or the empty string."""
    window = _display_device_window(output)
    match = _DENSITY_TOKEN.search(window)
    if match is None:
        return ""
    return match.group(1)


def _wm_size_value(output: str) -> str:
    """Return the ``wm size`` physical size, or the empty string."""
    match = re.search(r"(?:Physical|Override) size:\s*(\d+x\d+)", output)
    return match.group(1) if match is not None else ""


def _wm_density_value(output: str) -> str:
    """Return the ``wm density`` physical density, or the empty string."""
    match = re.search(r"(?:Physical|Override) density:\s*(\d+)", output)
    return match.group(1) if match is not None else ""


def _pid_values(output: str) -> tuple[int, ...]:
    """Return every numeric PID token of one ``pidof`` output."""
    return tuple(int(token) for token in output.split() if token.isdigit())


def _resumed_component(output: str) -> tuple[str, int | None]:
    """Return the reported resumed component and task, if one is reported."""
    for line in output.splitlines():
        if _RESUMED_LINE.search(line) is None:
            continue
        match = _COMPONENT_TOKEN.search(line)
        if match is None:
            continue
        task = _TASK_TOKEN.search(line)
        return match.group(1), int(task.group(1)) if task is not None else None
    return "", None


def _installed_paths(output: str) -> list[str]:
    """Return every absolute installed APK path reported by ``pm``."""
    paths: list[str] = []
    for line in output.splitlines():
        value = line.strip()
        if value.startswith("package:"):
            value = value[len("package:") :].strip()
        if value.startswith("/") and value.endswith(".apk") and value not in paths:
            paths.append(value)
    return paths


class AdbRuntimeDevice:
    """Production Runtime Attempt Device for one serialised Android target.

    Every admitted operation is counted exactly once, the same unit the
    Recording Runtime Device counts, even when one logical operation expands
    into several command vectors (a session probe, an installed-byte read, or a
    rotation/foreground read).  The frozen exactly-once budget is expressed in
    admitted operations, so per-vector accounting would reject every real
    attempt.  The two host identity files (the AVD configuration and the system
    image manifest) are declared explicitly: without them the Runtime Device
    Session cannot bind the emulator and system image identity, so
    ``probe_session`` fails closed instead of recording a partial session.

    Installed-byte verification pulls the reported installed APK into a private
    staging directory, hashes it, and removes the staging copy.  The digest is
    the device-reported installed artifact, not the preparation handoff bytes.
    """

    device_kind = "adb"

    def __init__(
        self,
        serial: str,
        *,
        package: str,
        activity: str,
        runner: CommandRunner | None = None,
        avd_config_path: Path | None = None,
        system_image_manifest_path: Path | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        for name, value in (
            ("serial", serial),
            ("package", package),
            ("activity", activity),
        ):
            if not isinstance(value, str) or not value.strip():
                raise RuntimeAttemptInputError(f"adb_device_{name}_invalid")
        if type(timeout_seconds) is not int or timeout_seconds < 1:
            raise RuntimeAttemptInputError("adb_device_timeout_invalid")
        self._serial = serial
        self._package = package
        self._activity = activity
        self._runner = runner or SubprocessCommandRunner()
        self._avd_config_path = (
            Path(avd_config_path) if avd_config_path is not None else None
        )
        self._system_image_manifest_path = (
            Path(system_image_manifest_path)
            if system_image_manifest_path is not None
            else None
        )
        self._timeout = timeout_seconds
        self._operations = _DeviceOperationLog()

    # -- identity -----------------------------------------------------------

    @property
    def serial(self) -> str:
        return self._serial

    @property
    def package(self) -> str:
        return self._package

    @property
    def activity(self) -> str:
        return self._activity

    def operation_counts(self) -> Mapping[str, int]:
        return self._operations.counts()

    def mutation_commands(self) -> Sequence[tuple[str, ...]]:
        return self._operations.mutations()

    def mutation_operations(self) -> Sequence[tuple[str, tuple[str, ...]]]:
        return self._operations.mutation_log()

    def operations(self) -> Sequence[str]:
        return self._operations.operations()

    # -- command plumbing ---------------------------------------------------

    def _run(
        self,
        operation: str,
        argv: Sequence[str],
        *,
        expect_success: bool = False,
    ) -> CommandResult:
        try:
            result = self._runner.run(list(argv), timeout_seconds=self._timeout)
        except (OSError, RuntimeError, TypeError, ValueError) as error:
            raise RuntimeAttemptDeviceError(operation, str(error)) from error
        if not isinstance(result, CommandResult):
            raise RuntimeAttemptDeviceError(
                operation, "command runner returned an invalid result"
            )
        if expect_success and result.returncode != 0:
            raise RuntimeAttemptDeviceError(
                operation,
                f"{operation} exited with {result.returncode}: "
                f"{(result.stderr or result.stdout).strip()[:200]}",
            )
        return result

    def _receipt(
        self, operation: str, argv: Sequence[str], result: CommandResult
    ) -> DeviceCommandReceipt:
        return DeviceCommandReceipt(
            operation=operation,
            command=tuple(argv),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    def _identity_file_sha256(self, path: Path | None) -> str:
        if path is None:
            return ""
        try:
            return _file_sha256(path)
        except OSError as error:
            raise RuntimeAttemptDeviceError(
                "probe_session", f"identity file {path} is unreadable: {error}"
            ) from error

    # -- protocol -----------------------------------------------------------

    def probe_session(self) -> DeviceProbeReceipt:
        self._operations.begin("probe_session")
        plan = session_probe_plan(self._serial)
        outputs: list[str] = []
        returncodes: list[int] = []
        readings: dict[str, str] = {}
        for argv, field_name in plan:
            result = self._run("probe_session", argv)
            outputs.append(result.stdout)
            returncodes.append(result.returncode)
            readings[field_name] = result.stdout
        return DeviceProbeReceipt(
            operation="probe_session",
            commands=tuple(argv for argv, _ in plan),
            returncodes=tuple(returncodes),
            outputs=tuple(outputs),
            fields=self._session_fields(readings),
        )

    def _session_fields(self, readings: Mapping[str, str]) -> dict[str, object]:
        """Derive the Runtime Device Session identity from raw probe output."""
        props: dict[str, str] = {
            "boot_id": "",
            "emulator_version": "",
            "api_level": "",
            "fingerprint": "",
            "abi": "",
            "model": "",
            "hardware": "",
            "avd_name": "",
        }
        settings = {name: "" for name in SESSION_IDENTITY_SETTINGS}
        for argv, field_name in session_probe_plan(self._serial):
            output = readings.get(field_name, "")
            if field_name == "android_cli_version":
                props[field_name] = _version_token(output)
                continue
            if field_name == "adb_version":
                props[field_name] = _version_token(output)
                continue
            if field_name == "display_size":
                props[field_name] = _wm_size_value(output)
                continue
            if field_name == "display_density":
                props[field_name] = _wm_density_value(output)
                continue
            if field_name.startswith("settings."):
                settings[field_name[len("settings.") :]] = _setting_value(output)
                continue
            props[field_name] = _getprop_value(output, str(argv[-1]))
        api_level = props.get("api_level", "")
        return {
            "serial": self._serial,
            "package": self._package,
            "activity": self._activity,
            "boot_id": props.get("boot_id", ""),
            "android_cli_version": props.get("android_cli_version", ""),
            "emulator_version": props.get("emulator_version", ""),
            "adb_version": props.get("adb_version", ""),
            "avd_name": props.get("avd_name", ""),
            "avd_config_sha256": self._identity_file_sha256(self._avd_config_path),
            "system_image_manifest_sha256": self._identity_file_sha256(
                self._system_image_manifest_path
            ),
            "api_level": int(api_level) if api_level.isdigit() else 0,
            "fingerprint": props.get("fingerprint", ""),
            "abi": props.get("abi", ""),
            "model": props.get("model", ""),
            "hardware": props.get("hardware", ""),
            "display_size": props.get("display_size", ""),
            "display_density": props.get("display_density", ""),
            "settings": settings,
        }

    def deploy_apk(
        self, *, apk_path: Path, package: str, activity: str
    ) -> DeviceCommandReceipt:
        self._check_target("deploy_apk", package, activity)
        argv = deployment_vector(
            self._serial, apk_path=Path(apk_path), package=package, activity=activity
        )
        self._operations.begin("deploy_apk", mutation=argv)
        result = self._run("deploy_apk", argv)
        return self._receipt("deploy_apk", argv, result)

    def read_installed_apk(self, package: str) -> DeviceProbeReceipt:
        self._check_package("read_installed_apk", package)
        self._operations.begin("read_installed_apk")
        commands: list[tuple[str, ...]] = []
        outputs: list[str] = []
        returncodes: list[int] = []
        paths: list[str] = []
        for argv in installed_apk_vectors(self._serial, package):
            result = self._run("read_installed_apk", argv)
            commands.append(argv)
            outputs.append(result.stdout)
            returncodes.append(result.returncode)
            for path in _installed_paths(result.stdout):
                if path not in paths:
                    paths.append(path)
        digest = ""
        size = 0
        if paths:
            with tempfile.TemporaryDirectory() as staging:
                staged = Path(staging) / "installed.apk"
                pull = _adb(self._serial, "pull", paths[0], str(staged))
                result = self._run("read_installed_apk", pull)
                commands.append(pull)
                outputs.append(result.stdout)
                returncodes.append(result.returncode)
                if result.returncode == 0 and staged.is_file():
                    digest = _file_sha256(staged)
                    size = staged.stat().st_size
        return DeviceProbeReceipt(
            operation="read_installed_apk",
            commands=tuple(commands),
            returncodes=tuple(returncodes),
            outputs=tuple(outputs),
            fields={"paths": paths, "sha256": digest, "bytes": size},
        )

    def clear_package_data(self, package: str) -> DeviceCommandReceipt:
        self._check_package("clear_package_data", package)
        argv = clear_package_data_vector(self._serial, package)
        self._operations.begin("clear_package_data", mutation=argv)
        result = self._run("clear_package_data", argv)
        return self._receipt("clear_package_data", argv, result)

    def target_process_ids(self, package: str) -> DeviceProbeReceipt:
        self._check_package("target_process_ids", package)
        argv = target_process_vector(self._serial, package)
        self._operations.begin("target_process_ids")
        result = self._run("target_process_ids", argv)
        return DeviceProbeReceipt(
            operation="target_process_ids",
            commands=(argv,),
            returncodes=(result.returncode,),
            outputs=(result.stdout,),
            fields={"pids": list(_pid_values(result.stdout))},
        )

    def write_rotation_setting(self, *, name: str, value: int) -> DeviceCommandReceipt:
        self._check_rotation_setting(name, value)
        argv = rotation_setting_vector(self._serial, name, value)
        self._operations.begin("write_rotation_setting", mutation=argv)
        result = self._run("write_rotation_setting", argv)
        return self._receipt("write_rotation_setting", argv, result)

    def read_rotation_state(self) -> DeviceProbeReceipt:
        self._operations.begin("read_rotation_state")
        commands: list[tuple[str, ...]] = []
        outputs: list[str] = []
        returncodes: list[int] = []
        settings: dict[str, str] = {}
        display = ""
        for argv in rotation_state_vectors(self._serial):
            result = self._run("read_rotation_state", argv)
            commands.append(argv)
            outputs.append(result.stdout)
            returncodes.append(result.returncode)
            for name in ALLOWED_ROTATION_SETTINGS:
                if str(argv[-1]) == name:
                    settings[name] = _setting_value(result.stdout)
            if "display" in argv:
                display = result.stdout
        accelerometer = settings.get("accelerometer_rotation", "")
        user_rotation = settings.get("user_rotation", "")
        rotation = _display_rotation_value(display)
        return DeviceProbeReceipt(
            operation="read_rotation_state",
            commands=tuple(commands),
            returncodes=tuple(returncodes),
            outputs=tuple(outputs),
            fields={
                "accelerometer_rotation": (
                    int(accelerometer) if accelerometer.isdigit() else None
                ),
                "user_rotation": int(user_rotation) if user_rotation.isdigit() else None,
                "rotation": rotation,
                "portrait": None if rotation is None else rotation == PORTRAIT_ROTATION,
                "display_size": _display_size_value(display),
            },
        )

    def clear_log_buffers(self) -> DeviceCommandReceipt:
        argv = clear_log_buffers_vector(self._serial)
        self._operations.begin("clear_log_buffers", mutation=argv)
        result = self._run("clear_log_buffers", argv, expect_success=True)
        return self._receipt("clear_log_buffers", argv, result)

    def write_log_marker(self, marker: str) -> DeviceCommandReceipt:
        if not isinstance(marker, str) or not marker.strip():
            raise RuntimeAttemptDeviceError(
                "write_log_marker", "attempt marker text is required"
            )
        argv = log_marker_vector(self._serial, marker)
        self._operations.begin("write_log_marker", mutation=argv)
        result = self._run("write_log_marker", argv)
        return self._receipt("write_log_marker", argv, result)

    def dump_all_buffers_epoch(self) -> DeviceCommandReceipt:
        argv = dump_all_buffers_vector(self._serial)
        self._operations.begin("dump_all_buffers_epoch")
        result = self._run("dump_all_buffers_epoch", argv)
        return self._receipt("dump_all_buffers_epoch", argv, result)

    def canonical_launch(
        self, *, package: str, activity: str
    ) -> DeviceCommandReceipt:
        self._check_target("canonical_launch", package, activity)
        argv = canonical_launch_vector(self._serial, package, activity)
        self._operations.begin("canonical_launch", mutation=argv)
        result = self._run("canonical_launch", argv)
        return self._receipt("canonical_launch", argv, result)

    def read_foreground_state(self) -> DeviceProbeReceipt:
        self._operations.begin("read_foreground_state")
        commands: list[tuple[str, ...]] = []
        outputs: list[str] = []
        returncodes: list[int] = []
        readings: dict[str, str] = {}
        for argv in foreground_state_vectors(self._serial, self._package):
            result = self._run("read_foreground_state", argv)
            commands.append(argv)
            outputs.append(result.stdout)
            returncodes.append(result.returncode)
            if "activity" in argv:
                readings["activity"] = result.stdout
            elif argv[-1] == "pidof":
                readings["pidof"] = result.stdout
            else:
                readings["display"] = result.stdout
        component, task_id = _resumed_component(readings.get("activity", ""))
        pids = _pid_values(readings.get("pidof", ""))
        rotation = _display_rotation_value(readings.get("display", ""))
        return DeviceProbeReceipt(
            operation="read_foreground_state",
            commands=tuple(commands),
            returncodes=tuple(returncodes),
            outputs=tuple(outputs),
            fields={
                "component": component,
                "task_id": task_id,
                "pid": pids[0] if len(pids) == 1 else None,
                "rotation": rotation,
                "landscape": None if rotation is None else rotation != PORTRAIT_ROTATION,
                "display_size": _display_size_value(readings.get("display", "")),
                "resumed": bool(component) and bool(pids),
            },
        )

    def dispatch_orientation(self, rotation: int) -> DeviceCommandReceipt:
        if rotation != LANDSCAPE_ROTATION:
            raise RuntimeAttemptDeviceError(
                "dispatch_orientation", "only one landscape dispatch is admitted"
            )
        argv = orientation_dispatch_vector(self._serial, rotation)
        self._operations.begin("dispatch_orientation", mutation=argv)
        result = self._run("dispatch_orientation", argv)
        return self._receipt("dispatch_orientation", argv, result)

    def read_layout(self) -> LayoutObservation | CommandResult | str | list[object]:
        argv = layout_vector(self._serial)
        self._operations.begin("read_layout")
        result = self._run("read_layout", argv)
        return LayoutObservation(
            command=argv,
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    def tap(self, x: int, y: int) -> CommandResult:
        if type(x) is not int or type(y) is not int or x < 0 or y < 0:
            raise RuntimeAttemptDeviceError("tap", "tap coordinates are invalid")
        argv = tap_vector(self._serial, x, y)
        self._operations.begin("tap", mutation=argv)
        return self._run("tap", argv)

    # -- guards -------------------------------------------------------------

    def _check_package(self, operation: str, package: str) -> None:
        if package != self._package:
            raise RuntimeAttemptDeviceError(
                operation, f"{package!r} is not the bound target package"
            )

    def _check_target(self, operation: str, package: str, activity: str) -> None:
        self._check_package(operation, package)
        if activity != self._activity:
            raise RuntimeAttemptDeviceError(
                operation, f"{activity!r} is not the bound target activity"
            )

    def _check_rotation_setting(self, name: str, value: int) -> None:
        if name not in ALLOWED_ROTATION_SETTINGS:
            raise RuntimeAttemptDeviceError(
                "write_rotation_setting", f"setting {name} is not allowed"
            )
        if value not in (PORTRAIT_ROTATION, LANDSCAPE_ROTATION):
            raise RuntimeAttemptDeviceError(
                "write_rotation_setting", f"rotation value {value} is not allowed"
            )


# ---------------------------------------------------------------------------
# Phase timing and terminal signals
# ---------------------------------------------------------------------------


class _Phase:
    """Record one bounded phase duration and raise the canonical abort."""

    def __init__(
        self,
        name: str,
        *,
        clock: Callable[[], float],
        phases: list[dict[str, object]],
    ) -> None:
        self.name = name
        self.status = "ok"
        self._clock = clock
        self._phases = phases
        self._started = 0.0

    def __enter__(self) -> Self:
        self._started = self._clock()
        return self

    def __exit__(
        self, kind: object, value: object, traceback: object
    ) -> None:
        seconds = max(0.0, self._clock() - self._started)
        self._phases.append(
            {"phase": self.name, "status": self.status, "seconds": round(seconds, 6)}
        )

    def fail(self, reason: str, message: str, *, kind: str = "evidence") -> NoReturn:
        """Abort this attempt with the canonical reason and phase identity."""
        self.status = "failed"
        raise _AttemptAbort(self.name, kind, reason, message, scope="attempt")

    def reason(self) -> str:
        """Return this phase's canonical device failure reason."""
        return PHASE_FAILURE_REASONS.get(self.name, "device_io_failed")


@dataclass(frozen=True)
class RuntimeAttemptReceipt:
    """One sealed runtime attempt receipt bound to its ExecutionRecord."""

    output_root: Path
    path: Path
    payload: bytes
    sha256: str
    attempt_id: str
    scenario: str
    terminal_state: str
    reason: str | None
    execution_record_path: Path

    def __post_init__(self) -> None:
        if self.terminal_state not in {ACCOUNTABLE_CONCLUDED, NON_ACCOUNTABLE}:
            raise RuntimeAttemptError("attempt_terminal_state_invalid")
        if self.terminal_state == NON_ACCOUNTABLE and not self.reason:
            raise RuntimeAttemptError("attempt_terminal_reason_invalid")
        _require_digest(self.sha256, "attempt_receipt_digest_invalid")
        _require_text(self.attempt_id, "attempt_receipt_attempt_invalid")

    @property
    def document(self) -> dict[str, object]:
        """Decode a fresh copy so callers cannot mutate the sealed outcome."""
        try:
            value = json.loads(self.payload)
        except (TypeError, json.JSONDecodeError) as error:
            raise RuntimeAttemptError("attempt_receipt_identity_invalid") from error
        if not isinstance(value, dict):
            raise RuntimeAttemptError("attempt_receipt_identity_invalid")
        return value

    @property
    def accountable_concluded(self) -> bool:
        return self.terminal_state == ACCOUNTABLE_CONCLUDED

    @property
    def verdict(self) -> str | None:
        value = self.document.get("verdict")
        return value if isinstance(value, str) else None

    @property
    def components(self) -> Mapping[str, object]:
        value = self.document.get("components")
        return value if isinstance(value, Mapping) else {}

    @property
    def relative_path(self) -> str:
        """Return the portable evidence path of this receipt."""
        try:
            return self.path.relative_to(self.output_root).as_posix()
        except ValueError as error:
            raise RuntimeAttemptError("attempt_receipt_identity_invalid") from error


@dataclass(frozen=True)
class RuntimeAttemptRequest:
    """Every admitted input for exactly one runtime attempt."""

    lane_id: str
    run_spec: RunSpec
    driver_plan: DeterministicDriverPlan
    setup_plan: RuntimeAttemptSetupPlan
    preparation_receipt: RuntimePreparationReceipt
    device: RuntimeAttemptDevice
    output_root: Path
    started_at: str | None = None
    clock: Callable[[], float] = time.monotonic
    sleeper: Callable[[float], None] = time.sleep

# ---------------------------------------------------------------------------
# Accountable attempt pipeline
# ---------------------------------------------------------------------------

RECORD_FILENAME = "execution-record.json"
RECEIPT_FILENAME = "attempt-receipt.json"
ARTIFACTS_DIRNAME = "artifacts"
JOURNEY_DIRNAME = "journey"
TARGET_LOG_WINDOW_FILENAME = "target-log-window.log"
LIFECYCLE_WINDOW_FILENAME = "lifecycle-window.log"
BOUNDARY_LAYOUT_FILENAME = "boundary-layout.json"
POST_EVENT_LAYOUT_FILENAME = "post-event-layout.json"

JOURNEY_SEGMENT_ID = "runtime-attempt-journey"
JOURNEY_ACTION_STATUS_PASSED = "PASSED"
EXPECTED_ORIENTATION_EVENT = "rotate"
EXPECTED_ORIENTATION = "landscape"
LAUNCH_STATUS_TOKEN = "Status: ok"
SETUP_SUCCESS_TOKEN = "Success"
REPORTED_COMPONENT_PREFIX = "Activity:"
PROVENANCE_KIND = "runtime_attempt_receipt_v1"

# Every accountable component that must exist before the receipt is sealed.
REQUIRED_ACCOUNTABLE_COMPONENTS = (
    "identity",
    "device_session",
    "sealed_apk",
    "attempt_setup",
    "target_log_window",
    "canonical_launch",
    "journey",
    "boundary_precondition",
    "lifecycle_transition",
    "post_event_observation",
    "oracles",
    "device_operations",
)


def _marker_indexes(text: str, marker: str) -> list[int]:
    """Return the 1-based line numbers carrying one exact attempt marker."""
    suffix = f"{MARKER_TAG}: {marker}"
    return [
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if line.rstrip().endswith(suffix)
    ]


def _window_slice(text: str, start_line: int, end_line: int) -> str:
    """Return the inclusive marker-bounded window as canonical text."""
    lines = text.splitlines()
    return "".join(f"{line}\n" for line in lines[start_line - 1 : end_line])


def _terminated(text: str) -> str:
    """Return one bounded capture as newline-terminated evidence text."""
    if not text:
        return ""
    return text if text.endswith("\n") else f"{text}\n"


def _status_token(stdout: str) -> str:
    """Return the canonical ``Status:`` launch token, or the empty string."""
    for line in stdout.splitlines():
        token = line.strip()
        if token.startswith("Status:"):
            return token
    return ""


def _reported_component(stdout: str) -> str:
    """Return the reported launch component, or the empty string."""
    for line in stdout.splitlines():
        token = line.strip()
        if token.startswith(REPORTED_COMPONENT_PREFIX):
            return token[len(REPORTED_COMPONENT_PREFIX) :].strip()
    return ""


def _excerpt(line: str) -> str:
    """Return the bounded excerpt of one lifecycle evidence line."""
    value = line.strip()
    if len(value) <= LIFECYCLE_EVENT_EXCERPT_CHARS:
        return value
    return value[:LIFECYCLE_EVENT_EXCERPT_CHARS]


def _lines_matching(text: str, term: str) -> list[dict[str, object]]:
    """Return every 1-based line carrying one lifecycle term."""
    return [
        {"line": index, "excerpt": _excerpt(line)}
        for index, line in enumerate(text.splitlines(), start=1)
        if term in line
    ]


def _line_number(item: Mapping[str, object]) -> int:
    """Return one recorded evidence line number, or -1 when unusable."""
    value = item.get("line")
    return value if type(value) is int else -1


def _target_process_patterns(package: str) -> tuple[str, ...]:
    """Return the target-scoped process start and death patterns."""
    escaped = re.escape(package)
    return (
        PROCESS_START_TEMPLATE.format(package=escaped),
        *(template.format(package=escaped) for template in PROCESS_DEATH_TEMPLATES),
    )


def _event_process(event: LogEvent) -> str:
    """Return one analysed log event's normalised process identity."""
    return event.process.rstrip(",:").strip()


def _event_is_target(event: LogEvent, package: str) -> bool:
    """Return whether one analysed log event belongs to the target package."""
    process = _event_process(event)
    if not process:
        return False
    return process == package or process.startswith(f"{package}:")


def _reduce_verdict(*, l1_outcome: str, l2_outcome: str) -> str:
    """Reduce the attributed L1 signal and the L2 evaluation to one verdict."""
    if L1_OUTCOME_FAIL in (l1_outcome, l2_outcome):
        return L1_OUTCOME_FAIL
    return L1_OUTCOME_INCONCLUSIVE


def _l2_evaluation(
    *, input_node_count: int, input_valid: bool, input_text: str
) -> tuple[str, str]:
    """Return the L2 outcome and its bounded detail for one observation."""
    if input_node_count == 0:
        return L2_OUTCOME_INCONCLUSIVE, "post_event_input_missing"
    if input_node_count > 1:
        return L2_OUTCOME_INCONCLUSIVE, "post_event_input_duplicated"
    if not input_valid:
        return L2_OUTCOME_INCONCLUSIVE, "post_event_input_unusable"
    if input_text == BOUNDARY_PRECONDITION_TEXT:
        return L2_OUTCOME_PASS, "preserved_state"
    return L2_OUTCOME_FAIL, "state_loss"


_ResultT = TypeVar("_ResultT")


class _AttemptRun:
    """The exactly-once pipeline behind :func:`execute_runtime_attempt`."""

    def __init__(self, request: RuntimeAttemptRequest) -> None:
        self.request = request
        self.lane_id = request.lane_id
        self.run_spec = request.run_spec
        self.driver_plan = request.driver_plan
        self.setup_plan = request.setup_plan
        self.preparation = request.preparation_receipt
        self.device = request.device
        self.clock = request.clock
        self.sleeper = request.sleeper
        self.started_at = request.started_at or _now()
        self.started_clock = request.clock()
        self.finished_at: str | None = None
        self.finished_clock: float | None = None
        self.scenario = ""
        self.evidence_class = ""
        self.tap_count = 0
        self.poll_count = 0
        self.phases: list[dict[str, object]] = []
        self.components: dict[str, dict[str, object]] = {}
        self.artifacts: list[dict[str, object]] = []
        self.markers: dict[str, str] = {}
        self.failure: dict[str, object] | None = None
        self.verdict: str | None = None
        self.exit_code: int | None = None
        self.store: ExecutionRecordStore | None = None
        self.attempt_id = ""
        self.root: Path | None = None
        self.artifacts_dir: Path | None = None
        self.journey_dir: Path | None = None
        self.sealed_apk_path: Path | None = None
        self.sealed_apk_bytes = 0
        self.sealed_apk_sha256 = ""
        self.window_text = ""
        self.window_opened = False
        self.window_closed = False
        self.window_start_line = 0
        self.window_end_line = 0
        self.foreground_before: Mapping[str, object] = {}
        self.foreground_after: Mapping[str, object] = {}
        self.lifecycle_observations: list[dict[str, object]] = []

    # -- shared plumbing ----------------------------------------------------

    @property
    def output_dir(self) -> Path:
        if self.root is None:
            raise RuntimeAttemptError("attempt_output_root_unavailable")
        return self.root

    @property
    def record_store(self) -> ExecutionRecordStore:
        if self.store is None:
            raise RuntimeAttemptError("attempt_record_establish_failed")
        return self.store

    @property
    def package(self) -> str:
        return self.setup_plan.package

    @property
    def activity(self) -> str:
        value = self.run_spec.activity
        return value if isinstance(value, str) else ""

    def _phase(self, name: str) -> _Phase:
        return _Phase(name, clock=self.clock, phases=self.phases)

    def _marker(self, kind: str) -> str:
        return attempt_marker(
            lane_id=self.lane_id, attempt_id=self.attempt_id, kind=kind
        )

    def _device_call(
        self, phase: _Phase, call: Callable[[], _ResultT]
    ) -> _ResultT:
        """Run one admitted device operation and abort on a device refusal."""
        try:
            return call()
        except RuntimeAttemptDeviceError as error:
            phase.fail(phase.reason(), str(error), kind="device")

    def _read_layout(
        self, phase: _Phase, reason: str
    ) -> tuple[list[dict[str, object]], str, tuple[str, ...]]:
        """Read one layout and return its nodes, raw text, and exact vector."""
        try:
            raw = self.device.read_layout()
        except RuntimeAttemptDeviceError as error:
            phase.fail(reason, str(error), kind="device")
        try:
            return layout_nodes(raw), layout_stdout(raw), layout_command(raw)
        except RuntimeAttemptError as error:
            phase.fail(reason, error.code)

    def _relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.output_dir).as_posix()
        except ValueError as error:
            raise RuntimeAttemptError("attempt_artifact_path_invalid") from error

    def _artifact_path(self, filename: str) -> Path:
        if self.artifacts_dir is None:
            raise RuntimeAttemptError("attempt_artifact_write_failed")
        return self.artifacts_dir / filename

    def _register_file(self, *, kind: str, path: Path) -> dict[str, object]:
        try:
            size = path.stat().st_size
            digest = _file_sha256(path)
        except OSError as error:
            raise RuntimeAttemptError(
                "attempt_artifact_write_failed", str(error)
            ) from error
        entry: dict[str, object] = {
            "kind": kind,
            "path": self._relative(path),
            "sha256": digest,
            "bytes": size,
        }
        self.artifacts.append(entry)
        return entry

    def _write_artifact_json(
        self,
        phase: _Phase,
        *,
        filename: str,
        kind: str,
        document: Mapping[str, object],
    ) -> dict[str, object]:
        """Write one stamped JSON artifact and register it in the inventory."""
        path = self._artifact_path(filename)
        stamped = _stamp({**document, "kind": kind})
        try:
            sha256, _ = _write_json_exclusive(path, stamped)
        except RuntimeAttemptError as error:
            phase.fail("attempt_artifact_write_failed", error.code)
        entry: dict[str, object] = {
            "kind": kind,
            "path": self._relative(path),
            "sha256": sha256,
            "bytes": len(canonical_bytes(stamped)),
        }
        self.artifacts.append(entry)
        return entry

    def _write_artifact_bytes(
        self, phase: _Phase, *, filename: str, kind: str, payload: bytes
    ) -> dict[str, object]:
        """Write one opaque evidence artifact and register it in the inventory."""
        path = self._artifact_path(filename)
        try:
            write_bytes_artifact(path, payload)
        except (ArtifactStorageError, OSError) as error:
            phase.fail(
                "attempt_artifact_write_failed", f"{type(error).__name__}: {error}"
            )
        entry: dict[str, object] = {
            "kind": kind,
            "path": self._relative(path),
            "sha256": _sha256_bytes(payload),
            "bytes": len(payload),
        }
        self.artifacts.append(entry)
        return entry

    def _register_journey_file(self, phase: _Phase, *, kind: str, path: Path) -> None:
        """Register one backend-owned Journey artifact in the inventory."""
        try:
            self._register_file(kind=kind, path=path)
        except RuntimeAttemptError as error:
            phase.fail("attempt_artifact_write_failed", error.code)

    def _foreground_is_target(
        self, fields: Mapping[str, object], *, landscape: bool
    ) -> bool:
        """Return whether one foreground read proves the resumed target."""
        if not component_matches(
            fields.get("component"), package=self.package, activity=self.activity
        ):
            return False
        expected = LANDSCAPE_ROTATION if landscape else PORTRAIT_ROTATION
        if fields.get("rotation") != expected:
            return False
        if bool(fields.get("landscape")) is not landscape:
            return False
        return bool(fields.get("resumed"))

    # -- pipeline -----------------------------------------------------------

    def run_pipeline(self) -> None:
        """Verify inputs, establish the record, and run every phase once."""
        self._prepare_inputs()
        self._establish_record()
        try:
            self._run_phases()
        except _AttemptAbort:
            raise
        except RuntimeAttemptError as error:
            reason = (
                error.code
                if error.code in SHARED_FAILURE_REASONS
                else "device_io_failed"
            )
            raise _AttemptAbort(
                "attempt", "harness", reason, str(error), scope="attempt"
            ) from error

    def _run_phases(self) -> None:
        with self._phase("device-session") as phase:
            self._probe_session(phase)
        with self._phase("deploy-sealed-apk") as phase:
            self._deploy_sealed_apk(phase)
        with self._phase("attempt-setup") as phase:
            self._attempt_setup(phase)
        with self._phase("open-target-log-window") as phase:
            self._open_target_log_window(phase)
        with self._phase("canonical-launch") as phase:
            self._canonical_launch(phase)
        with self._phase("journey") as phase:
            self._drive_journey(phase)
        with self._phase("boundary-precondition") as phase:
            self._prove_boundary_precondition(phase)
        with self._phase("lifecycle-rotation") as phase:
            self._dispatch_orientation(phase)
        with self._phase("collect-post-event-observation") as phase:
            self._collect_post_event_observation(phase)
        with self._phase("close-target-log-window") as phase:
            self._close_target_log_window(phase)
        with self._phase("prove-lifecycle-transition") as phase:
            self._prove_lifecycle_transition(phase)
        with self._phase("evaluate-oracles") as phase:
            self._evaluate_oracles(phase)
        with self._phase("finalize-receipt") as phase:
            self._require_accountable_evidence(phase)

    # -- phase 0/1: frozen inputs and record establishment ------------------

    def _prepare_inputs(self) -> None:
        """Reject every non-frozen input before any device side effect."""
        with self._phase("prepare-inputs"):
            self._check_frozen_inputs()
            self.root = _prepare_output_root(self.request.output_root)

    def _check_frozen_inputs(self) -> None:
        plan = self.driver_plan
        setup = self.setup_plan
        spec = self.run_spec
        scenario = spec.scenario
        if not isinstance(self.lane_id, str) or not self.lane_id.strip():
            raise RuntimeAttemptInputError("attempt_lane_identity_invalid")
        if not isinstance(plan, DeterministicDriverPlan):
            raise RuntimeAttemptInputError("attempt_driver_plan_unavailable")
        if plan.lane_id != self.lane_id:
            raise RuntimeAttemptInputError("attempt_lane_identity_mismatch")
        if plan.plan_id != f"{self.lane_id}-driver-plan":
            raise RuntimeAttemptInputError("attempt_driver_plan_identity_invalid")
        if (
            setup.family_id != plan.family_id
            or setup.family_version != plan.family_version
        ):
            raise RuntimeAttemptInputError("attempt_family_identity_mismatch")
        if setup.package != spec.package:
            raise RuntimeAttemptInputError("attempt_setup_package_mismatch")
        activity = spec.activity
        if not isinstance(activity, str) or not activity:
            raise RuntimeAttemptInputError("attempt_activity_identity_invalid")
        if self.device.package != setup.package:
            raise RuntimeAttemptInputError("attempt_device_package_mismatch")
        if self.device.activity != activity:
            raise RuntimeAttemptInputError("attempt_device_activity_mismatch")
        self._check_run_spec_binding()
        self._check_actions()
        self._check_system_events()
        self.scenario = f"{self.lane_id}:{scenario.id}"
        self.evidence_class = self._evidence_class()
        self.sealed_apk_path, self.sealed_apk_bytes, self.sealed_apk_sha256 = (
            self._sealed_apk_binding()
        )
        self.components["identity"] = self._identity_component()

    def _check_run_spec_binding(self) -> None:
        """Bind the admitted Driver Plan to the exact frozen Run Spec bytes."""
        source = self.run_spec.source_path
        if source is None or not isinstance(self.run_spec.source_sha256, str):
            raise RuntimeAttemptInputError("attempt_run_spec_source_unavailable")
        try:
            source_bytes = Path(source).read_bytes()
        except OSError as error:
            raise RuntimeAttemptInputError(
                "attempt_run_spec_source_unavailable"
            ) from error
        if _sha256_bytes(source_bytes) != self.run_spec.source_sha256:
            raise RuntimeAttemptInputError("attempt_run_spec_bytes_drifted")
        try:
            document = yaml.safe_load(source_bytes.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as error:
            raise RuntimeAttemptInputError(
                "attempt_run_spec_source_invalid"
            ) from error
        if self.driver_plan.run_spec_sha256 != canonical_sha256(document):
            raise RuntimeAttemptInputError("attempt_run_spec_binding_mismatch")

    def _check_actions(self) -> None:
        """Require the frozen wait-plus-trajectory action shape."""
        actions = tuple(self.driver_plan.actions)
        expected: list[tuple[str, str]] = [
            ("wait_for_resource_id", FROZEN_TAP_TRAJECTORY[0]),
        ]
        expected.extend(("tap_resource_id", name) for name in FROZEN_TAP_TRAJECTORY)
        if tuple((action.kind, action.resource_id) for action in actions) != tuple(
            expected
        ):
            raise RuntimeAttemptInputError("attempt_driver_plan_shape_invalid")
        expected_user_actions = (
            f"wait for resource id {FROZEN_TAP_TRAJECTORY[0]}",
            *(f"tap resource id {name}" for name in FROZEN_TAP_TRAJECTORY),
        )
        if tuple(self.run_spec.scenario.user_actions) != expected_user_actions:
            raise RuntimeAttemptInputError("attempt_run_spec_actions_mismatch")
        self.tap_count = sum(
            1 for action in actions if action.kind == "tap_resource_id"
        )

    def _check_system_events(self) -> None:
        """Require exactly one landscape rotation at the Journey boundary."""
        events = tuple(self.run_spec.scenario.system_events)
        if len(events) != 1:
            raise RuntimeAttemptInputError("attempt_system_events_invalid")
        event = events[0]
        if event.event != EXPECTED_ORIENTATION_EVENT:
            raise RuntimeAttemptInputError("attempt_system_events_invalid")
        if event.args.get("orientation") != EXPECTED_ORIENTATION:
            raise RuntimeAttemptInputError("attempt_system_events_invalid")
        if event.step_index != self.tap_count:
            raise RuntimeAttemptInputError("attempt_system_events_invalid")

    def _test_substitutes(self) -> bool:
        try:
            return runtime_preparation_uses_test_substitutes(self.preparation)
        except ValueError as error:
            raise RuntimeAttemptInputError(
                "attempt_preparation_receipt_invalid"
            ) from error

    def _evidence_class(self) -> str:
        """Bind simulation honesty: only a recording device admits substitutes."""
        substitutes = self._test_substitutes()
        if self.device.device_kind == "recording":
            if not substitutes:
                raise RuntimeAttemptInputError("attempt_evidence_class_mismatch")
            return "recorded_simulation"
        if substitutes:
            raise RuntimeAttemptInputError("attempt_evidence_class_mismatch")
        return "device"

    def _sealed_apk_binding(self) -> tuple[Path, int, str]:
        """Re-verify the Sealed Runtime APK handoff bytes before deployment."""
        try:
            binding = sealed_apk_binding_from_receipt(self.preparation)
        except ValueError as error:
            raise RuntimeAttemptInputError(
                "attempt_sealed_apk_binding_invalid"
            ) from error
        if binding is None:
            raise RuntimeAttemptInputError("sealed_apk_unavailable")
        path, size, sha256 = binding
        target = Path(path)
        if not target.is_file():
            raise RuntimeAttemptInputError("sealed_apk_unavailable")
        if target.stat().st_size != size or _file_sha256(target) != sha256:
            raise RuntimeAttemptInputError("sealed_apk_bytes_drifted")
        return target, size, sha256

    def _identity_component(self) -> dict[str, object]:
        plan = self.driver_plan
        spec = self.run_spec
        return {
            "schema_version": SCHEMA_VERSION,
            "seam": SEAM,
            "claim_boundary": CLAIM_BOUNDARY,
            "lane_id": self.lane_id,
            "scenario": self.scenario,
            "evidence_class": self.evidence_class,
            "family": {
                "id": self.setup_plan.family_id,
                "version": self.setup_plan.family_version,
            },
            "setup_plan": self.setup_plan.to_dict(),
            "driver_plan": {
                "path": str(plan.path),
                "sha256": plan.sha256,
                "bytes": plan.bytes,
                "plan_id": plan.plan_id,
                "run_spec_path": plan.run_spec_path,
                "run_spec_sha256": plan.run_spec_sha256,
            },
            "run_spec": {
                "path": str(spec.source_path),
                "sha256": spec.source_sha256,
                "canonical_sha256": plan.run_spec_sha256,
            },
            "preparation": {
                "prepared": self.preparation.prepared,
                "receipt_sha256": self.preparation.receipt_sha256,
                "rejection_code": self.preparation.rejection_code,
                "test_substitutes": self._test_substitutes(),
            },
            "device": {
                "serial": self.device.serial,
                "kind": self.device.device_kind,
                "package": self.device.package,
                "activity": self.device.activity,
            },
            "sealed_apk": {
                "path": str(self.sealed_apk_path),
                "sha256": self.sealed_apk_sha256,
                "bytes": self.sealed_apk_bytes,
            },
            "started_at": self.started_at,
        }

    def _establish_record(self) -> None:
        """Create the one ExecutionRecord before the first device side effect."""
        with self._phase("establish-execution-record"):
            try:
                store = ExecutionRecordStore.establish(
                    self.output_dir,
                    artifact_dir=self.output_dir / ARTIFACTS_DIRNAME,
                    scenario=self.scenario,
                    started_at=self.started_at,
                )
                self.artifacts_dir = self.output_dir / ARTIFACTS_DIRNAME
                self.journey_dir = self.artifacts_dir / JOURNEY_DIRNAME
                self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            except (ExecutionRecordStorageError, OSError) as error:
                raise RuntimeAttemptError(
                    "attempt_record_establish_failed", str(error)
                ) from error
            self.store = store
            self.attempt_id = store.attempt_id

    # -- phase 3: device session -------------------------------------------

    def _probe_session(self, phase: _Phase) -> None:
        receipt = self._device_call(phase, self.device.probe_session)
        if any(code != 0 for code in receipt.returncodes):
            phase.fail(
                "device_session_unavailable",
                "the session probe returned a non-zero code",
            )
        fields = receipt.fields
        if fields.get("serial") != self.device.serial:
            phase.fail(
                "device_session_unavailable",
                "the session serial contradicts the selected device",
            )
        missing = [name for name in SESSION_REQUIRED_FIELDS if not fields.get(name)]
        if missing:
            phase.fail(
                "device_session_unavailable",
                f"missing identity fields: {','.join(missing)}",
            )
        settings = fields.get("settings")
        if not isinstance(settings, Mapping):
            phase.fail("device_session_unavailable", "the session settings are missing")
        missing_settings = [
            name for name in SESSION_IDENTITY_SETTINGS if name not in settings
        ]
        if missing_settings:
            phase.fail(
                "device_session_unavailable",
                f"missing identity settings: {','.join(missing_settings)}",
            )
        self.components["device_session"] = {
            "operation": receipt.operation,
            "device_kind": self.device.device_kind,
            "serial": self.device.serial,
            "commands": [list(command) for command in receipt.commands],
            "returncodes": list(receipt.returncodes),
            "fields": dict(fields),
        }

    # -- phase 4: sealed deployment ----------------------------------------

    def _deploy_sealed_apk(self, phase: _Phase) -> None:
        path = self.sealed_apk_path
        if path is None or not path.is_file():
            phase.fail("sealed_apk_unavailable", "the sealed APK is missing")
        if path.stat().st_size != self.sealed_apk_bytes:
            phase.fail("sealed_apk_bytes_drifted", "the sealed APK size changed")
        if _file_sha256(path) != self.sealed_apk_sha256:
            phase.fail("sealed_apk_bytes_drifted", "the sealed APK bytes changed")
        package = self.package
        deployed = self._device_call(
            phase,
            lambda: self.device.deploy_apk(
                apk_path=path, package=package, activity=self.activity
            ),
        )
        if deployed.returncode != 0:
            phase.fail(
                "sealed_apk_deployment_failed",
                "the deployment returned a non-zero code",
            )
        installed = self._device_call(
            phase, lambda: self.device.read_installed_apk(package)
        )
        paths = installed.fields.get("paths")
        digest = installed.fields.get("sha256")
        if not isinstance(paths, (list, tuple)) or not paths:
            phase.fail(
                "installed_apk_read_failed", "the installed APK path is missing"
            )
        if not isinstance(digest, str) or digest != self.sealed_apk_sha256:
            phase.fail(
                "sealed_apk_bytes_drifted",
                "the installed APK bytes contradict the preparation handoff",
            )
        installed_bytes = installed.fields.get("bytes")
        if (
            type(installed_bytes) is int
            and installed_bytes != self.sealed_apk_bytes
        ):
            phase.fail(
                "sealed_apk_bytes_drifted",
                "the installed APK size contradicts the preparation handoff",
            )
        self.components["sealed_apk"] = {
            "path": str(path),
            "sha256": self.sealed_apk_sha256,
            "bytes": self.sealed_apk_bytes,
            "deploy_operation": deployed.operation,
            "deploy_command": list(deployed.command),
            "deploy_stdout": deployed.stdout,
            "installed_paths": [str(item) for item in paths],
            "installed_sha256": digest,
            "installed_bytes": installed_bytes,
            "installed_commands": [list(command) for command in installed.commands],
        }

    # -- phase 5: attempt setup plan ---------------------------------------

    def _attempt_setup(self, phase: _Phase) -> None:
        package = self.package
        cleared = self._device_call(
            phase, lambda: self.device.clear_package_data(package)
        )
        if cleared.returncode != 0:
            phase.fail(
                "attempt_setup_failed", "the package clear returned a non-zero code"
            )
        if cleared.stdout.strip() != SETUP_SUCCESS_TOKEN:
            phase.fail(
                "attempt_setup_failed", "the package clear did not report Success"
            )
        presence = self._device_call(
            phase, lambda: self.device.target_process_ids(package)
        )
        pids = presence.fields.get("pids")
        if not isinstance(pids, (list, tuple)):
            phase.fail(
                "attempt_setup_failed", "the target process probe is unreadable"
            )
        if list(pids):
            phase.fail(
                "attempt_setup_failed", "target processes survived the package clear"
            )
        writes: list[dict[str, object]] = []
        for name in ALLOWED_ROTATION_SETTINGS:
            written = self._device_call(
                phase,
                partial(
                    self.device.write_rotation_setting,
                    name=name,
                    value=PORTRAIT_ROTATION,
                ),
            )
            if written.returncode != 0:
                phase.fail(
                    "attempt_setup_failed", f"the {name} write returned a non-zero code"
                )
            writes.append(
                {
                    "name": name,
                    "value": PORTRAIT_ROTATION,
                    "command": list(written.command),
                    "returncode": written.returncode,
                }
            )
        self.sleeper(SETUP_SETTLE_SECONDS)
        state = self._device_call(phase, self.device.read_rotation_state)
        rotation = state.fields.get("rotation")
        if rotation != PORTRAIT_ROTATION or not state.fields.get("portrait"):
            phase.fail("attempt_setup_failed", "portrait state was not proven")
        self.components["attempt_setup"] = {
            "plan": self.setup_plan.to_dict(),
            "package": package,
            "clear": {
                "command": list(cleared.command),
                "stdout": cleared.stdout,
                "returncode": cleared.returncode,
            },
            "absence": {
                "pids": [int(pid) for pid in pids],
                "command": [list(command) for command in presence.commands],
            },
            "writes": writes,
            "settle_seconds": SETUP_SETTLE_SECONDS,
            "rotation": dict(state.fields),
        }

    # -- phase 6: open the target log window -------------------------------

    def _open_target_log_window(self, phase: _Phase) -> None:
        cleared = self._device_call(phase, self.device.clear_log_buffers)
        if cleared.returncode != 0:
            phase.fail(
                "target_log_window_unavailable",
                "the log clear returned a non-zero code",
            )
        marker = self._marker(TARGET_WINDOW_START)
        self.markers[TARGET_WINDOW_START] = marker
        written = self._device_call(
            phase, lambda: self.device.write_log_marker(marker)
        )
        if written.returncode != 0:
            phase.fail(
                "target_log_window_unavailable", "the start marker was not written"
            )
        self.window_opened = True
        self.components["target_log_window"] = {
            "markers": dict(self.markers),
            "clear_command": list(cleared.command),
            "start_marker_command": list(written.command),
            "buffers": list(LOG_WINDOW_BUFFERS),
            "format": LOG_WINDOW_FORMAT,
            "started_at": _now(),
            "closed": False,
        }

    # -- phase 7: canonical application launch -----------------------------

    def _canonical_launch(self, phase: _Phase) -> None:
        package = self.package
        launched = self._device_call(
            phase,
            lambda: self.device.canonical_launch(
                package=package, activity=self.activity
            ),
        )
        if launched.returncode != 0:
            phase.fail(
                "canonical_launch_failed", "the launch returned a non-zero code"
            )
        status = _status_token(launched.stdout)
        if status != LAUNCH_STATUS_TOKEN:
            phase.fail(
                "canonical_launch_failed", "the launch did not report Status: ok"
            )
        reported = _reported_component(launched.stdout)
        if not component_matches(
            reported, package=package, activity=self.activity
        ):
            phase.fail(
                "canonical_launch_failed", "the launch reported another component"
            )
        self.sleeper(LAUNCH_SETTLE_SECONDS)
        foreground = self._device_call(phase, self.device.read_foreground_state)
        fields = dict(foreground.fields)
        if not self._foreground_is_target(fields, landscape=False):
            phase.fail(
                "canonical_launch_failed",
                "the foreground read did not prove the resumed target",
            )
        self.foreground_before = fields
        self.components["canonical_launch"] = {
            "command": list(launched.command),
            "status_token": status,
            "reported_component": reported,
            "settle_seconds": LAUNCH_SETTLE_SECONDS,
            "foreground": fields,
        }

    # -- phase 8: deterministic journey ------------------------------------

    def _drive_journey(self, phase: _Phase) -> None:
        plan = self.driver_plan
        directory = self.journey_dir
        if directory is None:
            phase.fail(
                "attempt_artifact_write_failed", "the journey directory is missing"
            )
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            phase.fail(
                "attempt_artifact_write_failed", f"{type(error).__name__}: {error}"
            )
        backend = DeterministicAndroidBackend(
            plan=plan,
            device=self.device.serial,
            device_adapter=self.device,
            clock=self.clock,
            sleeper=self.sleeper,
        )
        try:
            request = backend.build_request(
                segment_id=JOURNEY_SEGMENT_ID,
                action_offset=0,
                action_count=len(plan.actions),
                artifact_dir=directory,
                device=self.device.serial,
            )
            result = backend.execute(request)
        except (DeterministicDriverError, DeterministicDriverPlanError) as error:
            phase.fail(
                "journey_driver_failed",
                f"{type(error).__name__}: {error}",
                kind="device",
            )
        if result.backend != DETERMINISTIC_ANDROID_V1:
            phase.fail(
                "journey_driver_failed", "the journey backend identity is invalid"
            )
        results = result.data.get("results")
        if not isinstance(results, list) or len(results) != len(plan.actions):
            phase.fail(
                "journey_driver_failed", "the journey action list is incomplete"
            )
        statuses: list[str] = []
        for entry in results:
            status = entry.get("status") if isinstance(entry, Mapping) else None
            if status != JOURNEY_ACTION_STATUS_PASSED:
                phase.fail(
                    "journey_driver_failed", "a journey action did not pass"
                )
            statuses.append(str(status))
        invocation_path = result.metadata.get("invocation_receipt_path")
        if not isinstance(invocation_path, str) or not invocation_path:
            phase.fail(
                "journey_driver_failed",
                "the journey invocation receipt reference is missing",
            )
        self._register_journey_file(
            phase, kind="journey_result", path=Path(result.result_path)
        )
        self._register_journey_file(
            phase, kind="journey_events", path=Path(result.events_path)
        )
        self._register_journey_file(
            phase, kind="journey_invocation", path=Path(invocation_path)
        )
        self.components["journey"] = {
            "segment_id": JOURNEY_SEGMENT_ID,
            "backend": result.backend,
            "plan": {
                "path": str(plan.path),
                "sha256": plan.sha256,
                "bytes": plan.bytes,
                "plan_id": plan.plan_id,
                "lane_id": plan.lane_id,
            },
            "action_count": len(plan.actions),
            "action_ids": [action.action_id for action in plan.actions],
            "resource_ids": [action.resource_id for action in plan.actions],
            "kinds": [action.kind for action in plan.actions],
            "settle_ms": [action.settle_ms for action in plan.actions],
            "statuses": statuses,
            "tap_count": self.tap_count,
            "result_path": self._relative(Path(result.result_path)),
            "events_path": self._relative(Path(result.events_path)),
            "invocation_path": self._relative(Path(invocation_path)),
            "primary_command": list(result.command),
        }

    # -- phase 9: boundary precondition ------------------------------------

    def _prove_boundary_precondition(self, phase: _Phase) -> None:
        nodes, stdout, command = self._read_layout(
            phase, "boundary_layout_unreadable"
        )
        matches = input_nodes(nodes)
        if len(matches) != 1:
            phase.fail(
                "boundary_layout_unreadable",
                f"the input node is not unique: {len(matches)}",
            )
        node = matches[0]
        center = node_center(node)
        text = node_text(node)
        if (
            node_bounds(node) is None
            or center is None
            or not node_contains(node, *center)
        ):
            phase.fail(
                "boundary_layout_unreadable", "the input node geometry is invalid"
            )
        if text != BOUNDARY_PRECONDITION_TEXT:
            phase.fail(
                "boundary_layout_unreadable",
                f"the boundary input text is not {BOUNDARY_PRECONDITION_TEXT}",
            )
        entry = self._write_artifact_json(
            phase,
            filename=BOUNDARY_LAYOUT_FILENAME,
            kind="boundary_layout",
            document={
                "phase": "boundary-precondition",
                "command": list(command),
                "stdout": stdout,
                "input_node_count": len(matches),
                "input_text": text,
                "nodes": nodes,
            },
        )
        self.components["boundary_precondition"] = {
            "input_node_count": 1,
            "input_text": text,
            "center": list(center),
            "command": list(command),
            "artifact": entry["path"],
            "artifact_sha256": entry["sha256"],
        }

    # -- phase 10: lifecycle rotation --------------------------------------

    def _dispatch_orientation(self, phase: _Phase) -> None:
        start_marker = self._marker(LIFECYCLE_START)
        self.markers[LIFECYCLE_START] = start_marker
        written = self._device_call(
            phase, lambda: self.device.write_log_marker(start_marker)
        )
        if written.returncode != 0:
            phase.fail(
                "orientation_dispatch_failed",
                "the lifecycle start marker was not written",
            )
        dispatched = self._device_call(
            phase, lambda: self.device.dispatch_orientation(LANDSCAPE_ROTATION)
        )
        if dispatched.returncode != 0:
            phase.fail(
                "orientation_dispatch_failed",
                "the orientation dispatch returned a non-zero code",
            )
        deadline = self.clock() + LIFECYCLE_POLL_SECONDS
        observations: list[dict[str, object]] = []
        settled = False
        for index in range(LIFECYCLE_POLL_BUDGET):
            state = self._device_call(phase, self.device.read_foreground_state)
            self.poll_count += 1
            fields = dict(state.fields)
            observations.append({"poll": index + 1, "fields": fields})
            if self._foreground_is_target(fields, landscape=True):
                settled = True
                break
            if self.clock() >= deadline:
                break
            self.sleeper(LIFECYCLE_POLL_INTERVAL_SECONDS)
        end_marker = self._marker(LIFECYCLE_END)
        self.markers[LIFECYCLE_END] = end_marker
        closed = self._device_call(
            phase, lambda: self.device.write_log_marker(end_marker)
        )
        if closed.returncode != 0:
            phase.fail(
                "orientation_dispatch_failed",
                "the lifecycle end marker was not written",
            )
        if not settled:
            phase.fail(
                "orientation_not_observed",
                "the landscape resume was not observed within the poll budget",
            )
        self.lifecycle_observations = observations
        final_fields = observations[-1].get("fields")
        self.foreground_after = (
            dict(final_fields) if isinstance(final_fields, Mapping) else {}
        )
        self.components["lifecycle_transition"] = {
            "signature_id": LIFECYCLE_SIGNATURE_ID,
            "signature_status": LIFECYCLE_SIGNATURE_STATUS,
            "signature_events": list(LIFECYCLE_SIGNATURE_EVENTS),
            "dispatch_command": list(dispatched.command),
            "markers": {
                LIFECYCLE_START: start_marker,
                LIFECYCLE_END: end_marker,
            },
            "poll_budget": LIFECYCLE_POLL_BUDGET,
            "poll_interval_seconds": LIFECYCLE_POLL_INTERVAL_SECONDS,
            "poll_seconds": LIFECYCLE_POLL_SECONDS,
            "poll_count": len(observations),
            "observations": observations,
            "before": dict(self.foreground_before),
            "after": dict(self.foreground_after),
        }

    # -- phase 11: post-event observation ----------------------------------

    def _collect_post_event_observation(self, phase: _Phase) -> None:
        self.sleeper(SETUP_SETTLE_SECONDS)
        nodes, stdout, command = self._read_layout(
            phase, "post_event_layout_unreadable"
        )
        matches = input_nodes(nodes)
        count = len(matches)
        valid = False
        text = ""
        if count == 1:
            node = matches[0]
            center = node_center(node)
            valid = (
                node_bounds(node) is not None
                and center is not None
                and node_contains(node, *center)
            )
            text = node_text(node)
        outcome, detail = _l2_evaluation(
            input_node_count=count, input_valid=valid, input_text=text
        )
        entry = self._write_artifact_json(
            phase,
            filename=POST_EVENT_LAYOUT_FILENAME,
            kind="post_event_layout",
            document={
                "phase": "collect-post-event-observation",
                "command": list(command),
                "stdout": stdout,
                "input_node_count": count,
                "input_text": text,
                "input_valid": valid,
                "l2_outcome": outcome,
                "l2_detail": detail,
                "nodes": nodes,
            },
        )
        self.components["post_event_observation"] = {
            "input_node_count": count,
            "input_text": text,
            "input_valid": valid,
            "l2_outcome": outcome,
            "l2_detail": detail,
            "command": list(command),
            "artifact": entry["path"],
            "artifact_sha256": entry["sha256"],
        }

    # -- phase 12: close the target log window -----------------------------

    def _close_target_log_window(self, phase: _Phase) -> None:
        self._finalize_window(phase)

    def _finalize_window(self, phase: _Phase) -> None:
        """Write exactly one end marker and capture exactly one all-buffer dump."""
        if self.window_closed:
            return
        if not self.window_opened:
            phase.fail(
                "target_log_window_unavailable", "the target window was never opened"
            )
        end_marker = self._marker(TARGET_WINDOW_END)
        self.markers[TARGET_WINDOW_END] = end_marker
        written = self._device_call(
            phase, lambda: self.device.write_log_marker(end_marker)
        )
        if written.returncode != 0:
            phase.fail(
                "target_log_window_capture_failed", "the end marker was not written"
            )
        dump = self._device_call(phase, self.device.dump_all_buffers_epoch)
        if dump.returncode != 0:
            phase.fail(
                "target_log_window_capture_failed", "the all-buffer dump failed"
            )
        self.window_closed = True
        text = _terminated(dump.stdout)
        self.window_text = text
        starts = _marker_indexes(text, self.markers[TARGET_WINDOW_START])
        ends = _marker_indexes(text, end_marker)
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            phase.fail(
                "target_log_window_marker_error",
                "the target window marker pair is not unique and ordered",
            )
        self.window_start_line = starts[0]
        self.window_end_line = ends[0]
        window_slice = _window_slice(text, starts[0], ends[0])
        start_pattern = PROCESS_START_TEMPLATE.format(
            package=re.escape(self.package)
        )
        start_lines = [
            index
            for index, line in enumerate(
                window_slice.splitlines(), start=starts[0]
            )
            if re.search(start_pattern, line)
        ]
        if not start_lines:
            phase.fail(
                "target_log_window_capture_failed",
                "the window does not contain the target process start",
            )
        entry = self._write_artifact_bytes(
            phase,
            filename=TARGET_LOG_WINDOW_FILENAME,
            kind="target_log_window",
            payload=text.encode("utf-8"),
        )
        if "target_log_window" not in self.components:
            phase.fail(
                "target_log_window_unavailable", "the window component is missing"
            )
        self.components["target_log_window"].update(
            {
                "markers": dict(self.markers),
                "end_marker_command": list(written.command),
                "dump_command": list(dump.command),
                "start_line": starts[0],
                "end_line": ends[0],
                "line_count": len(text.splitlines()),
                "window_sha256": _sha256_bytes(window_slice.encode("utf-8")),
                "target_process_start_lines": start_lines,
                "capture_path": entry["path"],
                "capture_sha256": entry["sha256"],
                "capture_bytes": entry["bytes"],
                "closed": True,
                "closed_at": _now(),
            }
        )

    def _best_effort_close_window(self) -> None:
        """Close the log window on an aborted path without raising again."""
        if not self.window_opened or self.window_closed:
            return
        end_marker = self._marker(TARGET_WINDOW_END)
        self.markers[TARGET_WINDOW_END] = end_marker
        try:
            written = self.device.write_log_marker(end_marker)
            dump = self.device.dump_all_buffers_epoch()
        except Exception as error:  # noqa: BLE001 - best effort only
            # The abort reason already owns the receipt; a second failure
            # here must never mask it.
            self.components.setdefault("target_log_window", {}).update(
                {
                    "markers": dict(self.markers),
                    "capture": "unavailable_after_abort",
                    "capture_error": f"{type(error).__name__}: {error}",
                    "closed": False,
                }
            )
            return
        self.window_closed = True
        text = _terminated(dump.stdout)
        self.window_text = text
        starts = _marker_indexes(text, self.markers[TARGET_WINDOW_START])
        ends = _marker_indexes(text, end_marker)
        component = self.components.setdefault("target_log_window", {})
        component.update(
            {
                "markers": dict(self.markers),
                "end_marker_returncode": written.returncode,
                "dump_returncode": dump.returncode,
                "start_lines": starts,
                "end_lines": ends,
                "line_count": len(text.splitlines()),
                "closed": True,
                "partial": True,
            }
        )
        if len(starts) == 1 and len(ends) == 1 and starts[0] < ends[0]:
            self.window_start_line = starts[0]
            self.window_end_line = ends[0]
            window_slice = _window_slice(text, starts[0], ends[0])
            component["start_line"] = starts[0]
            component["end_line"] = ends[0]
            component["window_sha256"] = _sha256_bytes(
                window_slice.encode("utf-8")
            )
        try:
            path = self._artifact_path(TARGET_LOG_WINDOW_FILENAME)
            write_bytes_artifact(path, text.encode("utf-8"))
            entry = self._register_file(kind="target_log_window", path=path)
        except (RuntimeAttemptError, ArtifactStorageError, OSError) as error:
            component["capture"] = "unavailable_after_abort"
            component["capture_error"] = f"{type(error).__name__}: {error}"
            return
        component["capture"] = "partial"
        component["capture_path"] = entry["path"]
        component["capture_sha256"] = entry["sha256"]
        component["capture_bytes"] = entry["bytes"]

    # -- phase 13: prove the frozen lifecycle transition -------------------

    def _prove_lifecycle_transition(self, phase: _Phase) -> None:
        text = self.window_text
        if not text or self.window_start_line <= 0 or self.window_end_line <= 0:
            phase.fail(
                "lifecycle_transition_unproven",
                "the target log window was not captured",
            )
        start_marker = self.markers.get(LIFECYCLE_START, "")
        end_marker = self.markers.get(LIFECYCLE_END, "")
        if not start_marker or not end_marker:
            phase.fail(
                "lifecycle_transition_unproven", "a lifecycle marker is missing"
            )
        starts = _marker_indexes(text, start_marker)
        ends = _marker_indexes(text, end_marker)
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            phase.fail(
                "lifecycle_transition_unproven",
                "the lifecycle marker pair is not unique and ordered",
            )
        if starts[0] <= self.window_start_line or ends[0] >= self.window_end_line:
            phase.fail(
                "lifecycle_transition_unproven",
                "the lifecycle markers are outside the target log window",
            )
        slice_text = _window_slice(text, starts[0], ends[0])
        events: dict[str, list[dict[str, object]]] = {}
        for name, term in LIFECYCLE_EVENT_TERMS.items():
            found = [
                {
                    "line": _line_number(item) + starts[0] - 1,
                    "excerpt": item["excerpt"],
                }
                for item in _lines_matching(slice_text, term)
            ]
            if len(found) != 1:
                phase.fail(
                    "lifecycle_transition_unproven",
                    f"the {name} event is not unique",
                )
            events[name] = found
        ordered = [
            _line_number(events[name][0]) for name in LIFECYCLE_SIGNATURE_EVENTS
        ]
        if ordered != sorted(ordered):
            phase.fail(
                "lifecycle_transition_unproven",
                "the destroy/create/resume order is contradicted",
            )
        relaunch = _lines_matching(slice_text, LIFECYCLE_RELAUNCH_TAG)
        if len(relaunch) != 1:
            phase.fail(
                "lifecycle_transition_unproven", "the relaunch tag is not unique"
            )
        patterns = _target_process_patterns(self.package)
        restarts = [
            pattern
            for pattern in patterns
            if any(
                re.search(pattern, line) for line in slice_text.splitlines()
            )
        ]
        if restarts:
            phase.fail(
                "target_process_restarted",
                "the lifecycle slice reports a target process start or death",
            )
        before = dict(self.foreground_before)
        after = dict(self.foreground_after)
        if not before or not after:
            phase.fail(
                "lifecycle_transition_unproven", "the foreground reads are missing"
            )
        if before.get("task_id") != after.get("task_id"):
            phase.fail(
                "lifecycle_transition_unproven", "the task identity changed"
            )
        pid_before = before.get("pid")
        pid_after = after.get("pid")
        if type(pid_before) is not int or pid_before != pid_after:
            phase.fail("lifecycle_transition_unproven", "the PID identity changed")
        if not self._foreground_is_target(after, landscape=True):
            phase.fail(
                "lifecycle_transition_unproven",
                "the post-event foreground read is not the resumed landscape target",
            )
        entry = self._write_artifact_bytes(
            phase,
            filename=LIFECYCLE_WINDOW_FILENAME,
            kind="lifecycle_window",
            payload=slice_text.encode("utf-8"),
        )
        self.components["lifecycle_transition"].update(
            {
                "signature": {
                    "id": LIFECYCLE_SIGNATURE_ID,
                    "status": LIFECYCLE_SIGNATURE_STATUS,
                    "order": list(LIFECYCLE_SIGNATURE_EVENTS),
                    "events": events,
                    "relaunch": relaunch,
                },
                "process": {
                    "package": self.package,
                    "start_pattern": patterns[0],
                    "death_patterns": list(patterns[1:]),
                    "restart_evidence": [],
                },
                "task_id": after.get("task_id"),
                "pid": pid_after,
                "rotation": after.get("rotation"),
                "landscape": after.get("landscape"),
                "slice_lines": [starts[0], ends[0]],
                "slice_path": entry["path"],
                "slice_sha256": entry["sha256"],
            }
        )

    # -- phase 14: attributed L1 and post-event L2 -------------------------

    def _evaluate_oracles(self, phase: _Phase) -> None:
        window = _window_slice(
            self.window_text, self.window_start_line, self.window_end_line
        )
        if not window:
            phase.fail("log_attribution_ambiguous", "the target log window is empty")
        events = LogcatAnalyzer().analyze(window)
        attributed = [
            event for event in events if _event_is_target(event, self.package)
        ]
        foreign = [
            event for event in events if not _event_is_target(event, self.package)
        ]
        canonical = L1Oracle().judge(
            window, trigger_steps=list(FROZEN_TAP_TRAJECTORY)
        )
        if foreign:
            phase.fail(
                "log_attribution_ambiguous",
                f"{len(foreign)} log event(s) do not belong to the target package",
            )
        if not attributed and canonical.get("outcome") == L1_OUTCOME_FAIL:
            phase.fail(
                "log_attribution_ambiguous",
                "the canonical L1 signal has no target attribution",
            )
        l1_outcome = L1_OUTCOME_FAIL if attributed else L1_OUTCOME_INCONCLUSIVE
        observation = self.components.get("post_event_observation", {})
        l2_outcome = str(observation.get("l2_outcome", L2_OUTCOME_INCONCLUSIVE))
        l2_detail = str(
            observation.get("l2_detail", "post_event_observation_missing")
        )
        verdict = _reduce_verdict(l1_outcome=l1_outcome, l2_outcome=l2_outcome)
        self.verdict = verdict
        self.exit_code = 1 if verdict == L1_OUTCOME_FAIL else 0
        window_component = self.components.get("target_log_window", {})
        self.components["oracles"] = {
            "window_sha256": window_component.get("window_sha256"),
            "l1": {
                "outcome": l1_outcome,
                "attribution": "target_only",
                "attributed_event_count": len(attributed),
                "attributed_events": [
                    {
                        "type": event.type.value,
                        "process": _event_process(event),
                        "stacktrace_lines": len(event.stacktrace),
                    }
                    for event in attributed
                ],
                "canonical_verdict": canonical,
            },
            "l2": {
                "outcome": l2_outcome,
                "detail": l2_detail,
                "defect_class": (
                    "state_loss" if l2_outcome == L2_OUTCOME_FAIL else None
                ),
                "input_node_count": observation.get("input_node_count"),
                "input_text": observation.get("input_text"),
                "artifact_sha256": observation.get("artifact_sha256"),
            },
            "verdict": verdict,
        }

    # -- phase 15: exactly-once evidence and sealed receipt ----------------

    def _require_accountable_evidence(self, phase: _Phase) -> None:
        """Prove the exactly-once device budget and component completeness."""
        expected_mutations = expected_device_mutation_order(
            tap_count=self.tap_count
        )
        expected_reads = expected_device_read_counts(
            layout_reads=len(self.driver_plan.actions) + 2,
            foreground_reads=1 + self.poll_count,
        )
        mutation_table = {**EXPECTED_DEVICE_MUTATION_COUNTS, "tap": self.tap_count}
        counts = dict(self.device.operation_counts())
        observed_order = [
            operation for operation, _ in self.device.mutation_operations()
        ]
        if tuple(observed_order) != expected_mutations:
            phase.fail(
                "device_operation_budget_violated",
                "the ordered mutation sequence contradicts the frozen table",
            )
        for name, expected in {**mutation_table, **expected_reads}.items():
            observed = counts.get(name, 0)
            if observed != expected:
                phase.fail(
                    "device_operation_budget_violated",
                    f"operation {name} ran {observed} times, expected {expected}",
                )
        forbidden = sorted(set(counts) - set(mutation_table) - set(expected_reads))
        if forbidden:
            phase.fail(
                "device_operation_budget_violated",
                f"unadmitted device operations: {','.join(forbidden)}",
            )
        self.components["device_operations"] = {
            "counts": counts,
            "expected_mutation_counts": mutation_table,
            "expected_read_counts": dict(expected_reads),
            "observed_mutation_order": observed_order,
            "mutation_vectors": [
                list(vector) for vector in self.device.mutation_commands()
            ],
            "retries": 0,
            "tap_count": self.tap_count,
            "poll_count": self.poll_count,
        }
        missing = [
            name
            for name in REQUIRED_ACCOUNTABLE_COMPONENTS
            if name not in self.components
        ]
        if missing:
            phase.fail(
                "attempt_receipt_write_failed",
                f"missing accountable components: {','.join(missing)}",
            )

    # -- terminal conclusions ----------------------------------------------

    def conclude_accountable(self) -> RuntimeAttemptReceipt:
        """Seal one accountable_concluded attempt and finalize its record."""
        self.finished_at = _now()
        self.finished_clock = self.clock()
        if self.verdict is None or self.exit_code is None:
            raise RuntimeAttemptError("attempt_receipt_identity_invalid")
        receipt = self._write_receipt(
            terminal_state=ACCOUNTABLE_CONCLUDED, reason=None, failure=None
        )
        self._finalize_record(
            lifecycle_state="completed",
            execution={
                "status": "completed",
                "accounting_eligible": True,
                "reason": None,
                "message": None,
            },
            process_exit_code=self.exit_code,
            phase_errors=[],
            receipt_path=receipt.relative_path,
            provenance={
                "path": receipt.relative_path,
                "sha256": receipt.sha256,
                "kind": PROVENANCE_KIND,
                "attempt_id": self.attempt_id,
                "terminal_state": ACCOUNTABLE_CONCLUDED,
            },
        )
        return receipt

    def conclude_non_accountable(
        self, abort: _AttemptAbort
    ) -> RuntimeAttemptReceipt:
        """Seal one non_accountable attempt bound to its one canonical reason."""
        self.finished_at = _now()
        self.finished_clock = self.clock()
        self.verdict = L1_OUTCOME_INCONCLUSIVE
        self.exit_code = 2
        failure: dict[str, object] = {
            "phase": abort.phase,
            "kind": abort.kind,
            "reason": abort.reason,
            "message": abort.message,
            "scope": abort.scope,
        }
        self.failure = failure
        self._best_effort_close_window()
        try:
            receipt = self._write_receipt(
                terminal_state=NON_ACCOUNTABLE,
                reason=abort.reason,
                failure=failure,
            )
        except RuntimeAttemptError as error:
            terminal = error.code
            self._finalize_record(
                lifecycle_state="failed",
                execution={
                    "status": "non_accountable",
                    "accounting_eligible": False,
                    "reason": terminal,
                    "message": str(error),
                },
                process_exit_code=2,
                phase_errors=[
                    failure,
                    {
                        "phase": "finalize-receipt",
                        "kind": "evidence",
                        "reason": terminal,
                        "message": str(error),
                        "scope": "attempt",
                    },
                ],
                receipt_path=None,
                provenance=None,
            )
            raise
        self._finalize_record(
            lifecycle_state="failed",
            execution={
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": abort.reason,
                "message": abort.message,
            },
            process_exit_code=2,
            phase_errors=[failure],
            receipt_path=receipt.relative_path,
            provenance={
                "path": receipt.relative_path,
                "sha256": receipt.sha256,
                "kind": PROVENANCE_KIND,
                "attempt_id": self.attempt_id,
                "terminal_state": NON_ACCOUNTABLE,
            },
        )
        return receipt

    def _write_receipt(
        self,
        *,
        terminal_state: str,
        reason: str | None,
        failure: dict[str, object] | None,
    ) -> RuntimeAttemptReceipt:
        finished_at = self.finished_at or _now()
        total_seconds = 0.0
        if self.finished_clock is not None:
            total_seconds = max(0.0, self.finished_clock - self.started_clock)
        document: dict[str, object] = _stamp(
            {
                "schema_version": SCHEMA_VERSION,
                "seam": SEAM,
                "claim_boundary": CLAIM_BOUNDARY,
                "terminal_state": terminal_state,
                "reason": reason,
                "verdict": self.verdict,
                "attempt_id": self.attempt_id,
                "lane_id": self.lane_id,
                "scenario": self.scenario,
                "evidence_class": self.evidence_class,
                "retries": 0,
                "started_at": self.started_at,
                "finished_at": finished_at,
                "total_seconds": round(total_seconds, 6),
                "execution_record": {
                    "path": RECORD_FILENAME,
                    "attempt_id": self.attempt_id,
                },
                "phases": list(self.phases),
                "components": {
                    name: dict(value) for name, value in self.components.items()
                },
                "artifacts": list(self.artifacts),
                "failure": failure,
            }
        )
        path = self.output_dir / RECEIPT_FILENAME
        sha256, _identity = _write_json_exclusive(path, document)
        payload = canonical_bytes(document)
        return RuntimeAttemptReceipt(
            output_root=self.output_dir,
            path=path,
            payload=payload,
            sha256=sha256,
            attempt_id=self.attempt_id,
            scenario=self.scenario,
            terminal_state=terminal_state,
            reason=reason,
            execution_record_path=self.output_dir / RECORD_FILENAME,
        )

    def _finalize_record(
        self,
        *,
        lifecycle_state: str,
        execution: dict[str, object],
        process_exit_code: int,
        phase_errors: list[dict[str, object]],
        receipt_path: str | None,
        provenance: dict[str, object] | None,
    ) -> None:
        """Finalize the one ExecutionRecord with its exactly-once outcome."""
        finished_at = self.finished_at or _now()
        total_seconds = 0.0
        if self.finished_clock is not None:
            total_seconds = max(0.0, self.finished_clock - self.started_clock)
        evidence_refs: dict[str, object] = {
            "attempt_artifacts": [str(entry["path"]) for entry in self.artifacts]
        }
        if receipt_path is not None:
            evidence_refs["attempt_receipt_path"] = receipt_path
        if provenance is not None:
            evidence_refs["execution_provenance"] = provenance
        timing: dict[str, object] = {
            "started_at": self.started_at,
            "finished_at": finished_at,
            "total_seconds": round(total_seconds, 6),
            "phases": list(self.phases),
        }
        try:
            self.record_store.finalize(
                lifecycle_state=lifecycle_state,
                execution=execution,
                process_exit_code=process_exit_code,
                timing=timing,
                phase_errors=phase_errors,
                evidence_refs=evidence_refs,
            )
        except (
            ExecutionRecordStorageError,
            ExecutionRecordValidationError,
        ) as error:
            raise RuntimeAttemptError(
                "attempt_record_finalize_failed", str(error)
            ) from error


# ---------------------------------------------------------------------------
# Public seam
# ---------------------------------------------------------------------------


def execute_runtime_attempt(
    request: RuntimeAttemptRequest,
) -> RuntimeAttemptReceipt:
    """Execute exactly one accountable runtime attempt on the public seam.

    The pipeline establishes one ExecutionRecord before the first device side
    effect, drives the frozen phases in order, and concludes the attempt as
    ``accountable_concluded`` or ``non_accountable`` with one canonical reason.
    """
    if not isinstance(request, RuntimeAttemptRequest):
        raise RuntimeAttemptInputError("attempt_request_invalid")
    run = _AttemptRun(request)
    try:
        run.run_pipeline()
    except _AttemptAbort as abort:
        return run.conclude_non_accountable(abort)
    return run.conclude_accountable()


def _verification_violation(code: str, message: str) -> NoReturn:
    raise RuntimeAttemptVerificationError(code, message)


def _verify_receipt_identity(
    document: Mapping[str, object], *, expected_path: Path
) -> str:
    """Recompute the receipt identity and return its hex digest."""
    body = dict(document)
    identity = body.pop("identity_sha256", None)
    if not isinstance(identity, str) or _HEX_64.fullmatch(identity) is None:
        _verification_violation(
            "attempt_receipt_identity_invalid", "the receipt identity is invalid"
        )
    if canonical_sha256(body) != identity:
        _verification_violation(
            "attempt_receipt_identity_mismatch",
            "the receipt identity does not match its own bytes",
        )
    payload = canonical_bytes(dict(document))
    if expected_path.read_bytes() != payload:
        _verification_violation(
            "attempt_receipt_bytes_drifted",
            "the receipt bytes are not the canonical document",
        )
    return _sha256_bytes(payload)


def _verify_receipt_constants(document: Mapping[str, object]) -> str:
    if document.get("schema_version") != SCHEMA_VERSION:
        _verification_violation(
            "attempt_receipt_schema_invalid", "unsupported receipt schema version"
        )
    if document.get("seam") != SEAM:
        _verification_violation(
            "attempt_receipt_seam_invalid", "the receipt seam identity drifted"
        )
    if document.get("claim_boundary") != CLAIM_BOUNDARY:
        _verification_violation(
            "attempt_receipt_claim_boundary_invalid",
            "the receipt claim boundary drifted",
        )
    if document.get("retries") != 0:
        _verification_violation(
            "attempt_receipt_retry_invalid", "the receipt admits a retry"
        )
    terminal_state = document.get("terminal_state")
    if terminal_state not in {ACCOUNTABLE_CONCLUDED, NON_ACCOUNTABLE}:
        _verification_violation(
            "attempt_terminal_state_invalid", "unknown terminal state"
        )
    reason = document.get("reason")
    if terminal_state == NON_ACCOUNTABLE:
        if not isinstance(reason, str) or reason not in SHARED_FAILURE_REASONS:
            _verification_violation(
                "attempt_terminal_reason_invalid",
                "the non-accountable reason is not canonical",
            )
        if document.get("verdict") != L1_OUTCOME_INCONCLUSIVE:
            _verification_violation(
                "attempt_verdict_invalid",
                "a non-accountable attempt cannot own an authoritative verdict",
            )
    elif reason is not None:
        _verification_violation(
            "attempt_terminal_reason_invalid",
            "an accountable attempt cannot carry a terminal reason",
        )
    for key in ("attempt_id", "lane_id", "scenario", "evidence_class"):
        value = document.get(key)
        if not isinstance(value, str) or not value:
            _verification_violation(
                "attempt_receipt_identity_invalid",
                f"the receipt {key} is missing",
            )
    return str(terminal_state)


def _verify_evidence_class(document: Mapping[str, object]) -> None:
    """Recompute the evidence class from the bound device identity.

    Simulation honesty is bound by the runner (a recording device admits test
    substitutes, a real device must not); the verifier recomputes that same
    rule from the receipt's own identity component instead of trusting the
    recorded label.
    """
    components = document.get("components")
    components = components if isinstance(components, Mapping) else {}
    identity = components.get("identity")
    identity = identity if isinstance(identity, Mapping) else {}
    device = identity.get("device")
    device = device if isinstance(device, Mapping) else {}
    preparation = identity.get("preparation")
    preparation = preparation if isinstance(preparation, Mapping) else {}
    kind = device.get("kind")
    substitutes = preparation.get("test_substitutes")
    if kind == "recording" and substitutes is True:
        expected = "recorded_simulation"
    elif kind == "adb" and substitutes is False:
        expected = "device"
    else:
        expected = None
    if expected is None or document.get("evidence_class") != expected:
        _verification_violation(
            "attempt_evidence_class_mismatch",
            "the evidence class contradicts the device identity",
        )


def _verify_record_binding(
    document: Mapping[str, object], *, root: Path, receipt_sha256: str
) -> dict[str, object]:
    record_path = root / RECORD_FILENAME
    try:
        record = load_execution_record(record_path)
    except ExecutionRecordValidationError as error:
        _verification_violation(
            "attempt_record_invalid", f"the ExecutionRecord is invalid: {error}"
        )
    if record.get("attempt_id") != document.get("attempt_id"):
        _verification_violation(
            "attempt_record_binding_mismatch",
            "the record attempt identity contradicts the receipt",
        )
    if record.get("scenario") != document.get("scenario"):
        _verification_violation(
            "attempt_record_binding_mismatch",
            "the record scenario contradicts the receipt",
        )
    terminal_state = document.get("terminal_state")
    execution = record.get("execution")
    if not isinstance(execution, Mapping):
        _verification_violation(
            "attempt_record_binding_mismatch", "the record execution is missing"
        )
    if terminal_state == ACCOUNTABLE_CONCLUDED:
        if record.get("lifecycle_state") != "completed":
            _verification_violation(
                "attempt_record_binding_mismatch",
                "an accountable receipt requires a completed record",
            )
        provenance = record.get("evidence_refs", {})
        provenance = (
            provenance.get("execution_provenance")
            if isinstance(provenance, Mapping)
            else None
        )
        if not isinstance(provenance, Mapping):
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the record execution provenance is missing",
            )
        if provenance.get("sha256") != receipt_sha256:
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the record provenance contradicts the receipt bytes",
            )
        if provenance.get("path") != RECEIPT_FILENAME:
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the record provenance path contradicts the receipt",
            )
    else:
        if record.get("lifecycle_state") != "failed":
            _verification_violation(
                "attempt_record_binding_mismatch",
                "a non-accountable receipt requires a failed record",
            )
        if execution.get("reason") != document.get("reason"):
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the record reason contradicts the receipt reason",
            )
        phase_errors = record.get("phase_errors")
        if not isinstance(phase_errors, list) or not phase_errors:
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the failed record has no phase errors",
            )
        if phase_errors[-1].get("reason") != document.get("reason"):
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the terminal phase error does not match the receipt reason",
            )
    return record


def _verify_artifact_inventory(
    document: Mapping[str, object], *, root: Path, require_complete: bool = False
) -> tuple[dict[str, dict[str, object]], list[str]]:
    """Verify every artifact and refuse a shadowed or drifted inventory.

    A non-accountable attempt may keep a partial inventory of the artifacts it
    really produced, but no attempt may duplicate a kind or admit one outside
    the frozen set.  An accountable attempt must carry every frozen kind.
    """
    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list):
        _verification_violation(
            "attempt_artifact_inventory_invalid", "the artifact inventory is missing"
        )
    index: dict[str, dict[str, object]] = {}
    checks: list[str] = []
    for position, entry in enumerate(artifacts):
        if not isinstance(entry, Mapping):
            _verification_violation(
                "attempt_artifact_inventory_invalid",
                f"artifact {position} is not an object",
            )
        kind = entry.get("kind")
        relative = entry.get("path")
        digest = entry.get("sha256")
        size = entry.get("bytes")
        if not isinstance(kind, str) or not kind:
            _verification_violation(
                "attempt_artifact_inventory_invalid",
                f"artifact {position} has no kind",
            )
        if not isinstance(relative, str) or not relative:
            _verification_violation(
                "attempt_artifact_inventory_invalid",
                f"artifact {position} has no path",
            )
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            _verification_violation(
                "attempt_artifact_path_invalid",
                f"artifact {relative} is not a contained relative path",
            )
        target = root / path
        if target.is_symlink() or not target.is_file():
            _verification_violation(
                "attempt_artifact_missing", f"artifact {relative} is missing"
            )
        payload = target.read_bytes()
        if _sha256_bytes(payload) != digest:
            _verification_violation(
                "attempt_artifact_digest_mismatch",
                f"artifact {relative} does not match its recorded digest",
            )
        if len(payload) != size:
            _verification_violation(
                "attempt_artifact_size_mismatch",
                f"artifact {relative} does not match its recorded size",
            )
        if kind in index:
            _verification_violation(
                "attempt_artifact_inventory_invalid",
                f"artifact kind {kind} is duplicated",
            )
        index[str(kind)] = dict(entry)
        checks.append(f"artifact:{kind}")
    missing = sorted(set(_FROZEN_ARTIFACT_KINDS) - set(index))
    unexpected = sorted(set(index) - set(_FROZEN_ARTIFACT_KINDS))
    if unexpected or (require_complete and missing):
        _verification_violation(
            "attempt_artifact_inventory_invalid",
            "the artifact inventory does not match the frozen kinds: "
            f"missing {missing}, unexpected {unexpected}",
        )
    return index, checks


def _verify_device_budget(
    document: Mapping[str, object],
) -> tuple[list[str], dict[str, object]]:
    """Recompute the exactly-once device budget from the recorded shape."""
    components = document.get("components")
    if not isinstance(components, Mapping):
        _verification_violation(
            "attempt_component_invalid", "the receipt components are missing"
        )
    operations = components.get("device_operations")
    identity = components.get("identity")
    journey = components.get("journey")
    if not isinstance(operations, Mapping):
        _verification_violation(
            "attempt_component_invalid", "the device evidence components are missing"
        )
    if not isinstance(identity, Mapping) or not isinstance(journey, Mapping):
        _verification_violation(
            "attempt_component_invalid", "the device evidence components are missing"
        )
    tap_count = operations.get("tap_count")
    poll_count = operations.get("poll_count")
    action_count = journey.get("action_count")
    if type(tap_count) is not int or tap_count < MINIMUM_TAP_COUNT:
        _verification_violation(
            "attempt_device_budget_invalid", "the recorded tap count is invalid"
        )
    if type(poll_count) is not int or poll_count < 1:
        _verification_violation(
            "attempt_device_budget_invalid", "the recorded poll count is invalid"
        )
    if type(action_count) is not int or action_count < MINIMUM_TAP_COUNT:
        _verification_violation(
            "attempt_device_budget_invalid", "the recorded action count is invalid"
        )
    expected_mutations = expected_device_mutation_order(tap_count=tap_count)
    expected_reads = expected_device_read_counts(
        layout_reads=action_count + 2, foreground_reads=1 + poll_count
    )
    mutation_table = {**EXPECTED_DEVICE_MUTATION_COUNTS, "tap": tap_count}
    counts = operations.get("counts")
    if not isinstance(counts, Mapping):
        _verification_violation(
            "attempt_device_budget_invalid", "the recorded operation counts are missing"
        )
    for name, expected in {**mutation_table, **expected_reads}.items():
        observed = counts.get(name, 0)
        if type(observed) is not int or observed != expected:
            _verification_violation(
                "attempt_device_budget_violated",
                f"operation {name} ran {observed!r} times, expected {expected}",
            )
    forbidden = sorted(set(counts) - set(mutation_table) - set(expected_reads))
    if forbidden:
        _verification_violation(
            "attempt_device_budget_violated",
            f"unadmitted device operations: {','.join(forbidden)}",
        )
    observed_order = operations.get("observed_mutation_order")
    if not isinstance(observed_order, list) or observed_order != list(
        expected_mutations
    ):
        _verification_violation(
            "attempt_device_budget_violated",
            "the recorded mutation order contradicts the frozen table",
        )
    vectors = operations.get("mutation_vectors")
    if not isinstance(vectors, list) or len(vectors) != len(expected_mutations):
        _verification_violation(
            "attempt_device_budget_violated",
            "the recorded mutation vectors are incomplete",
        )
    device = identity.get("device")
    sealed_apk = identity.get("sealed_apk")
    if not isinstance(device, Mapping) or not isinstance(sealed_apk, Mapping):
        _verification_violation(
            "attempt_component_invalid", "the device identity binding is missing"
        )
    serial = device.get("serial")
    package = device.get("package")
    activity = device.get("activity")
    if not all(isinstance(value, str) and value for value in (serial, package, activity)):
        _verification_violation(
            "attempt_component_invalid", "the device identity binding is incomplete"
        )
    marker_expected = {
        TARGET_WINDOW_START: attempt_marker(
            lane_id=str(document.get("lane_id")),
            attempt_id=str(document.get("attempt_id")),
            kind=TARGET_WINDOW_START,
        ),
        LIFECYCLE_START: attempt_marker(
            lane_id=str(document.get("lane_id")),
            attempt_id=str(document.get("attempt_id")),
            kind=LIFECYCLE_START,
        ),
        LIFECYCLE_END: attempt_marker(
            lane_id=str(document.get("lane_id")),
            attempt_id=str(document.get("attempt_id")),
            kind=LIFECYCLE_END,
        ),
        TARGET_WINDOW_END: attempt_marker(
            lane_id=str(document.get("lane_id")),
            attempt_id=str(document.get("attempt_id")),
            kind=TARGET_WINDOW_END,
        ),
    }
    apk_path = sealed_apk.get("path")
    if not isinstance(apk_path, str) or not apk_path:
        _verification_violation(
            "attempt_component_invalid", "the sealed APK binding is incomplete"
        )
    tap_prefix = ("adb", "-s", str(serial), "shell", "input", "tap")
    expected_vectors: list[tuple[str, tuple[str, ...] | None]] = [
        (
            "deploy_apk",
            deployment_vector(
                str(serial),
                apk_path=Path(apk_path),
                package=str(package),
                activity=str(activity),
            ),
        ),
        ("clear_package_data", clear_package_data_vector(str(serial), str(package))),
        (
            "write_rotation_setting",
            rotation_setting_vector(
                str(serial), ALLOWED_ROTATION_SETTINGS[0], PORTRAIT_ROTATION
            ),
        ),
        (
            "write_rotation_setting",
            rotation_setting_vector(
                str(serial), ALLOWED_ROTATION_SETTINGS[1], PORTRAIT_ROTATION
            ),
        ),
        ("clear_log_buffers", clear_log_buffers_vector(str(serial))),
        (
            "write_log_marker",
            log_marker_vector(str(serial), marker_expected[TARGET_WINDOW_START]),
        ),
        (
            "canonical_launch",
            canonical_launch_vector(str(serial), str(package), str(activity)),
        ),
        *(("tap", None) for _ in range(tap_count)),
        (
            "write_log_marker",
            log_marker_vector(str(serial), marker_expected[LIFECYCLE_START]),
        ),
        (
            "dispatch_orientation",
            orientation_dispatch_vector(str(serial), LANDSCAPE_ROTATION),
        ),
        (
            "write_log_marker",
            log_marker_vector(str(serial), marker_expected[LIFECYCLE_END]),
        ),
        (
            "write_log_marker",
            log_marker_vector(str(serial), marker_expected[TARGET_WINDOW_END]),
        ),
    ]
    for position, (operation, expected_vector) in enumerate(expected_vectors):
        vector = vectors[position]
        if not isinstance(vector, list):
            _verification_violation(
                "attempt_device_budget_invalid", "a mutation vector is not a list"
            )
        if operation != expected_mutations[position]:
            _verification_violation(
                "attempt_device_budget_violated",
                "the expected mutation table contradicts its own order",
            )
        if expected_vector is not None and tuple(vector) != expected_vector:
            _verification_violation(
                "attempt_device_budget_violated",
                f"the {operation} vector contradicts the admitted command",
            )
        if operation == "tap":
            if tuple(vector[:6]) != tap_prefix or len(vector) != 8:
                _verification_violation(
                    "attempt_device_budget_violated",
                    "a tap vector is not the admitted input tap command",
                )
            if not all(str(item).isdigit() for item in vector[6:]):
                _verification_violation(
                    "attempt_device_budget_violated",
                    "a tap vector does not carry numeric coordinates",
                )
    checks = ["device-budget", "mutation-order", "mutation-vectors"]
    return checks, {
        "expected_mutations": list(expected_mutations),
        "expected_reads": dict(expected_reads),
    }


def _verify_log_and_oracles(
    document: Mapping[str, object],
    *,
    root: Path,
    index: Mapping[str, dict[str, object]],
) -> tuple[list[str], dict[str, object]]:
    """Recompute the window slice, lifecycle signature, and both oracles."""
    components = document.get("components")
    if not isinstance(components, Mapping):
        _verification_violation(
            "attempt_component_invalid", "the receipt components are missing"
        )
    window = components.get("target_log_window")
    lifecycle = components.get("lifecycle_transition")
    boundary = components.get("boundary_precondition")
    post_event = components.get("post_event_observation")
    oracles = components.get("oracles")
    if not isinstance(window, Mapping) or not isinstance(lifecycle, Mapping):
        _verification_violation(
            "attempt_component_invalid", "an accountable component is missing"
        )
    if not isinstance(boundary, Mapping) or not isinstance(post_event, Mapping):
        _verification_violation(
            "attempt_component_invalid", "an accountable component is missing"
        )
    if not isinstance(oracles, Mapping):
        _verification_violation(
            "attempt_component_invalid", "an accountable component is missing"
        )
    capture_entry = index.get("target_log_window")
    if capture_entry is None:
        _verification_violation(
            "attempt_artifact_missing", "the target log window capture is missing"
        )
    capture_path = root / str(capture_entry["path"])
    capture_bytes = capture_path.read_bytes()
    if _sha256_bytes(capture_bytes) != capture_entry.get("sha256"):
        _verification_violation(
            "attempt_artifact_digest_mismatch",
            "the log capture contradicts its recorded digest",
        )
    try:
        text = capture_bytes.decode("utf-8")
    except UnicodeDecodeError:
        _verification_violation(
            "attempt_log_window_unreadable", "the log capture is not UTF-8 text"
        )
    markers = window.get("markers")
    if not isinstance(markers, Mapping):
        _verification_violation(
            "attempt_log_window_unreadable", "the window markers are missing"
        )
    first = markers.get(TARGET_WINDOW_START)
    last = markers.get(TARGET_WINDOW_END)
    if not isinstance(first, str) or not isinstance(last, str):
        _verification_violation(
            "attempt_log_window_unreadable", "the window marker pair is missing"
        )
    starts = _marker_indexes(text, first)
    ends = _marker_indexes(text, last)
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        _verification_violation(
            "attempt_log_window_marker_error",
            "the window marker pair is not unique and ordered",
        )
    if starts[0] != window.get("start_line") or ends[0] != window.get("end_line"):
        _verification_violation(
            "attempt_log_window_marker_error",
            "the recorded window bounds contradict the capture",
        )
    window_slice = _window_slice(text, starts[0], ends[0])
    if _sha256_bytes(window_slice.encode("utf-8")) != window.get("window_sha256"):
        _verification_violation(
            "attempt_log_window_digest_mismatch",
            "the window slice contradicts its recorded digest",
        )
    start_pattern = PROCESS_START_TEMPLATE.format(
        package=re.escape(str(components["identity"]["device"]["package"]))
    )
    if not any(
        re.search(start_pattern, line) for line in window_slice.splitlines()
    ):
        _verification_violation(
            "attempt_log_window_capture_failed",
            "the window does not contain the target process start",
        )
    lifecycle_markers = lifecycle.get("markers")
    if not isinstance(lifecycle_markers, Mapping):
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle markers are missing"
        )
    lifecycle_first = lifecycle_markers.get(LIFECYCLE_START)
    lifecycle_last = lifecycle_markers.get(LIFECYCLE_END)
    if not isinstance(lifecycle_first, str) or not isinstance(lifecycle_last, str):
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle marker pair is missing"
        )
    lifecycle_starts = _marker_indexes(text, lifecycle_first)
    lifecycle_ends = _marker_indexes(text, lifecycle_last)
    if (
        len(lifecycle_starts) != 1
        or len(lifecycle_ends) != 1
        or lifecycle_starts[0] >= lifecycle_ends[0]
    ):
        _verification_violation(
            "attempt_lifecycle_unproven",
            "the lifecycle marker pair is not unique and ordered",
        )
    if (
        lifecycle_starts[0] <= starts[0]
        or lifecycle_ends[0] >= ends[0]
    ):
        _verification_violation(
            "attempt_lifecycle_unproven",
            "the lifecycle markers are outside the target log window",
        )
    slice_text = _window_slice(text, lifecycle_starts[0], lifecycle_ends[0])
    slice_entry = index.get("lifecycle_window")
    if slice_entry is None:
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle slice artifact is missing"
        )
    slice_path = root / str(slice_entry["path"])
    slice_bytes = slice_path.read_bytes()
    if slice_bytes != slice_text.encode("utf-8"):
        _verification_violation(
            "attempt_lifecycle_unproven",
            "the lifecycle slice artifact contradicts the recomputed slice",
        )
    signature = lifecycle.get("signature")
    if not isinstance(signature, Mapping):
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle signature is missing"
        )
    if signature.get("id") != LIFECYCLE_SIGNATURE_ID:
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle signature identity drifted"
        )
    if list(signature.get("order") or []) != list(LIFECYCLE_SIGNATURE_EVENTS):
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle signature order drifted"
        )
    recorded_events = signature.get("events")
    if not isinstance(recorded_events, Mapping):
        _verification_violation(
            "attempt_lifecycle_unproven", "the lifecycle events are missing"
        )
    recomputed: dict[str, list[int]] = {}
    for name, term in LIFECYCLE_EVENT_TERMS.items():
        found = [
            _line_number(item) + lifecycle_starts[0] - 1
            for item in _lines_matching(slice_text, term)
        ]
        if len(found) != 1:
            _verification_violation(
                "attempt_lifecycle_unproven", f"the {name} event is not unique"
            )
        recomputed[name] = found
    for name, lines in recomputed.items():
        recorded = recorded_events.get(name)
        if not isinstance(recorded, list) or len(recorded) != 1:
            _verification_violation(
                "attempt_lifecycle_unproven",
                f"the recorded {name} event is missing",
            )
        recorded_line = recorded[0].get("line")
        if type(recorded_line) is not int or recorded_line != lines[0]:
            _verification_violation(
                "attempt_lifecycle_unproven",
                f"the recorded {name} line contradicts the capture",
            )
    ordered = [recomputed[name][0] for name in LIFECYCLE_SIGNATURE_EVENTS]
    if ordered != sorted(ordered):
        _verification_violation(
            "attempt_lifecycle_unproven",
            "the destroy/create/resume order is contradicted",
        )
    if len(_lines_matching(slice_text, LIFECYCLE_RELAUNCH_TAG)) != 1:
        _verification_violation(
            "attempt_lifecycle_unproven", "the relaunch tag is not unique"
        )
    patterns = _target_process_patterns(
        str(components["identity"]["device"]["package"])
    )
    for pattern in patterns:
        if any(re.search(pattern, line) for line in slice_text.splitlines()):
            _verification_violation(
                "attempt_target_process_restarted",
                "the lifecycle slice reports a target process start or death",
            )
    boundary_entry = index.get("boundary_layout")
    if boundary_entry is None:
        _verification_violation(
            "attempt_boundary_unreadable", "the boundary layout artifact is missing"
        )
    boundary_document = _read_json_object(
        root / str(boundary_entry["path"]), "attempt_boundary_unreadable"
    )
    boundary_nodes = boundary_document.get("nodes")
    if not isinstance(boundary_nodes, list):
        _verification_violation(
            "attempt_boundary_unreadable", "the boundary layout nodes are missing"
        )
    boundary_matches = input_nodes(
        [node for node in boundary_nodes if isinstance(node, Mapping)]
    )
    if len(boundary_matches) != 1:
        _verification_violation(
            "attempt_boundary_unreadable", "the boundary input node is not unique"
        )
    if node_text(boundary_matches[0]) != str(boundary.get("input_text")):
        _verification_violation(
            "attempt_boundary_unreadable",
            "the boundary input text contradicts the layout artifact",
        )
    if str(boundary.get("input_text")) != BOUNDARY_PRECONDITION_TEXT:
        _verification_violation(
            "attempt_boundary_unreadable",
            "the boundary input text contradicts the frozen precondition",
        )
    post_entry = index.get("post_event_layout")
    if post_entry is None:
        _verification_violation(
            "attempt_post_event_unreadable",
            "the post-event layout artifact is missing",
        )
    post_document = _read_json_object(
        root / str(post_entry["path"]), "attempt_post_event_unreadable"
    )
    post_nodes = post_document.get("nodes")
    if not isinstance(post_nodes, list):
        _verification_violation(
            "attempt_post_event_unreadable",
            "the post-event layout nodes are missing",
        )
    post_matches = input_nodes(
        [node for node in post_nodes if isinstance(node, Mapping)]
    )
    post_valid = False
    post_text = ""
    if len(post_matches) == 1:
        center = node_center(post_matches[0])
        post_valid = (
            node_bounds(post_matches[0]) is not None
            and center is not None
            and node_contains(post_matches[0], *center)
        )
        post_text = node_text(post_matches[0])
    l2_outcome, l2_detail = _l2_evaluation(
        input_node_count=len(post_matches),
        input_valid=post_valid,
        input_text=post_text,
    )
    l2_recorded = oracles.get("l2")
    if not isinstance(l2_recorded, Mapping):
        _verification_violation(
            "attempt_oracle_invalid", "the recorded L2 evaluation is missing"
        )
    if (
        l2_recorded.get("outcome") != l2_outcome
        or l2_recorded.get("detail") != l2_detail
        or l2_recorded.get("input_node_count") != len(post_matches)
        or l2_recorded.get("input_text") != post_text
    ):
        _verification_violation(
            "attempt_oracle_invalid",
            "the recorded L2 evaluation contradicts the layout artifact",
        )
    events = LogcatAnalyzer().analyze(window_slice)
    package = str(components["identity"]["device"]["package"])
    attributed = [event for event in events if _event_is_target(event, package)]
    foreign = [event for event in events if not _event_is_target(event, package)]
    canonical = L1Oracle().judge(
        window_slice, trigger_steps=list(FROZEN_TAP_TRAJECTORY)
    )
    if foreign:
        _verification_violation(
            "attempt_log_attribution_ambiguous",
            "the window contains events outside the target package",
        )
    if not attributed and canonical.get("outcome") == L1_OUTCOME_FAIL:
        _verification_violation(
            "attempt_log_attribution_ambiguous",
            "the canonical L1 signal has no target attribution",
        )
    l1_outcome = L1_OUTCOME_FAIL if attributed else L1_OUTCOME_INCONCLUSIVE
    l1_recorded = oracles.get("l1")
    if not isinstance(l1_recorded, Mapping):
        _verification_violation(
            "attempt_oracle_invalid", "the recorded L1 evaluation is missing"
        )
    if l1_recorded.get("outcome") != l1_outcome:
        _verification_violation(
            "attempt_oracle_invalid",
            "the recorded L1 outcome contradicts the recomputed attribution",
        )
    recorded_count = l1_recorded.get("attributed_event_count")
    if type(recorded_count) is not int or recorded_count != len(attributed):
        _verification_violation(
            "attempt_oracle_invalid",
            "the recorded attributed event count contradicts the recomputation",
        )
    recorded_events = l1_recorded.get("attributed_events")
    if not isinstance(recorded_events, list) or len(recorded_events) != len(
        attributed
    ):
        _verification_violation(
            "attempt_oracle_invalid",
            "the recorded attributed events contradict the recomputation",
        )
    verdict = _reduce_verdict(l1_outcome=l1_outcome, l2_outcome=l2_outcome)
    if oracles.get("verdict") != verdict or document.get("verdict") != verdict:
        _verification_violation(
            "attempt_oracle_invalid",
            "the recorded verdict contradicts the recomputed oracles",
        )
    return ["log-window", "lifecycle-signature", "boundary", "l2", "l1", "verdict"], {
        "verdict": verdict,
        "l1_outcome": l1_outcome,
        "l2_outcome": l2_outcome,
        "window_sha256": window.get("window_sha256"),
    }


def verify_runtime_attempt(output_root: str | Path) -> dict[str, object]:
    """Independently recompute one committed attempt without a live device.

    The verifier re-reads the sealed receipt and its artifacts, recomputes the
    receipt identity, the record binding, every artifact digest, the marker
    bounded log window, the lifecycle signature, the boundary precondition, the
    L1 attribution and L2 evaluation, the reduced verdict, and the exactly-once
    device budget.  It never touches a device and never trusts a recorded
    verdict without recomputing it.
    """
    raw = Path(output_root).expanduser()
    if raw.is_symlink() or not raw.is_dir():
        _verification_violation(
            "attempt_output_root_unreadable", "the attempt root is not a directory"
        )
    root = raw.resolve()
    receipt_path = root / RECEIPT_FILENAME
    document = _read_json_object(receipt_path, "attempt_receipt_unreadable")
    receipt_sha256 = _verify_receipt_identity(document, expected_path=receipt_path)
    terminal_state = _verify_receipt_constants(document)
    _verify_evidence_class(document)
    record = _verify_record_binding(
        document, root=root, receipt_sha256=receipt_sha256
    )
    index, checks = _verify_artifact_inventory(
        document, root=root, require_complete=terminal_state == ACCOUNTABLE_CONCLUDED
    )
    recomputed: dict[str, object] | None = None
    if terminal_state == ACCOUNTABLE_CONCLUDED:
        budget_checks, _budget = _verify_device_budget(document)
        log_checks, recomputed = _verify_log_and_oracles(
            document, root=root, index=index
        )
        checks = [*checks, *budget_checks, *log_checks]
        execution = record.get("execution")
        if not isinstance(execution, Mapping) or execution.get("status") != "completed":
            _verification_violation(
                "attempt_record_binding_mismatch",
                "the completed record does not report an accountable execution",
            )
        exit_code = record.get("process_outcome", {})
        exit_code = (
            exit_code.get("exit_code") if isinstance(exit_code, Mapping) else None
        )
        if document.get("verdict") == L1_OUTCOME_FAIL:
            if exit_code != 1:
                _verification_violation(
                    "attempt_record_binding_mismatch",
                    "an unexpected verdict requires exit code 1",
                )
        elif exit_code != 0:
            _verification_violation(
                "attempt_record_binding_mismatch",
                "a preserved-state verdict requires exit code 0",
            )
    else:
        exit_code = record.get("process_outcome", {})
        exit_code = (
            exit_code.get("exit_code") if isinstance(exit_code, Mapping) else None
        )
        if exit_code != 2:
            _verification_violation(
                "attempt_record_binding_mismatch",
                "a non-accountable record requires exit code 2",
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "seam": SEAM,
        "claim_boundary": CLAIM_BOUNDARY,
        "attempt_id": document.get("attempt_id"),
        "lane_id": document.get("lane_id"),
        "scenario": document.get("scenario"),
        "evidence_class": document.get("evidence_class"),
        "terminal_state": terminal_state,
        "reason": document.get("reason"),
        "verdict": document.get("verdict"),
        "retries": 0,
        "receipt_sha256": receipt_sha256,
        "recomputed": recomputed,
        "verified": True,
        "checks": checks,
    }
