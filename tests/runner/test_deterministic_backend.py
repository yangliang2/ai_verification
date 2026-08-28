from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aiverify.harness.device import AdbResult
from aiverify.runner import cli
from aiverify.runner.admission import ProductionSeamAdmissionError
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.deterministic_backend import (
    AndroidLayoutDeviceAdapter,
    DeterministicAndroidBackend,
    DeterministicDriverError,
    DeterministicDriverPlanError,
    LayoutObservation,
    load_deterministic_driver_plan,
)
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.execution_identity import (
    ExecutionIdentityCollector,
    ExecutionIdentityError,
    verify_execution_provenance,
)
from aiverify.runner.journey import JourneySegmentRunner
from aiverify.runner.journey_backend import DETERMINISTIC_ANDROID_V1
from aiverify.runner.run_spec import RunSpec, ScenarioSpec, load_run_spec


def _run_spec_bytes() -> bytes:
    return b"host_project: .\nscenario:\n  id: wait-smoke\n  user_actions:\n    - wait for resource id oneButton\n"


KEYPAD_ACTIONS = (
    "wait for resource id oneButton",
    "tap resource id oneButton",
    "tap resource id twoButton",
    "tap resource id addButton",
    "tap resource id threeButton",
    "tap resource id fourButton",
)


def _keypad_run_spec_bytes() -> bytes:
    return (
        b"host_project: .\n"
        b"scenario:\n"
        b"  id: opencalc-preserve-expression\n"
        b"  user_actions:\n"
        b"    - wait for resource id oneButton\n"
        b"    - tap resource id oneButton\n"
        b"    - tap resource id twoButton\n"
        b"    - tap resource id addButton\n"
        b"    - tap resource id threeButton\n"
        b"    - tap resource id fourButton\n"
    )


def _keypad_plan_payload(run_spec_path: str, run_spec_bytes: bytes) -> dict:
    resources = (
        "oneButton",
        "oneButton",
        "twoButton",
        "addButton",
        "threeButton",
        "fourButton",
    )
    kinds = (
        "wait_for_resource_id",
        "tap_resource_id",
        "tap_resource_id",
        "tap_resource_id",
        "tap_resource_id",
        "tap_resource_id",
    )
    return {
        "schema_version": 1,
        "document_kind": "deterministic_driver_plan",
        "family_id": "test-family",
        "family_version": "v1",
        "lane_id": "lane-01",
        "plan_id": "lane-01-driver-plan",
        "run_spec_path": run_spec_path,
        "run_spec_sha256": hashlib.sha256(run_spec_bytes).hexdigest(),
        "actions": [
            {
                "action_id": f"action-{index:02d}",
                "kind": kind,
                "resource_id": resource,
                "timeout_ms": 5000 if kind == "wait_for_resource_id" else 0,
                "observation_interval_ms": 350 if kind == "wait_for_resource_id" else 0,
                "settle_ms": 0 if kind == "wait_for_resource_id" else 350,
            }
            for index, (kind, resource) in enumerate(zip(kinds, resources), start=1)
        ],
    }


def _plan_payload(run_spec_path: str, run_spec_bytes: bytes) -> dict:
    return {
        "schema_version": 1,
        "document_kind": "deterministic_driver_plan",
        "family_id": "test-family",
        "family_version": "v1",
        "lane_id": "lane-01",
        "plan_id": "lane-01-driver-plan",
        "run_spec_path": run_spec_path,
        "run_spec_sha256": hashlib.sha256(run_spec_bytes).hexdigest(),
        "actions": [
            {
                "action_id": "action-01",
                "kind": "wait_for_resource_id",
                "resource_id": "oneButton",
                "timeout_ms": 5000,
                "observation_interval_ms": 350,
                "settle_ms": 0,
            }
        ],
    }


def _write_plan(tmp_path: Path, payload: dict, *, name: str = "driver-plan.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    return path


def test_plan_is_bound_to_exact_run_spec_bytes_and_action() -> None:
    raw = _run_spec_bytes()
    plan = load_deterministic_driver_plan(
        Path("/tmp/driver-plan.json"),
        serialized_run_spec=raw,
        run_spec_path=Path("/tmp/run-spec.yaml"),
        plan_bytes=json.dumps(_plan_payload("run-spec.yaml", raw)).encode(),
        expected_actions=("wait for resource id oneButton",),
    )

    assert plan.actions[0].kind == "wait_for_resource_id"
    assert plan.actions[0].resource_id == "oneButton"
    assert plan.run_spec_sha256 == hashlib.sha256(raw).hexdigest()


def test_keypad_plan_is_bound_to_the_complete_frozen_action_sequence(
    tmp_path: Path,
) -> None:
    raw = _keypad_run_spec_bytes()
    spec_path = tmp_path / "run-spec.yaml"
    spec_path.write_bytes(raw)
    plan_path = _write_plan(tmp_path, _keypad_plan_payload(spec_path.name, raw))

    plan = load_deterministic_driver_plan(
        plan_path,
        serialized_run_spec=raw,
        run_spec_path=spec_path,
        expected_actions=KEYPAD_ACTIONS,
    )

    assert [(action.kind, action.resource_id) for action in plan.actions] == [
        ("wait_for_resource_id", "oneButton"),
        ("tap_resource_id", "oneButton"),
        ("tap_resource_id", "twoButton"),
        ("tap_resource_id", "addButton"),
        ("tap_resource_id", "threeButton"),
        ("tap_resource_id", "fourButton"),
    ]
    assert [action.settle_ms for action in plan.actions] == [0, 350, 350, 350, 350, 350]


def test_public_opencalc_plan_accepts_its_canonical_run_spec_binding() -> None:
    lane = Path(
        "bench/runtime-calibration/opencalc-input-save-enabled-v1/runtime/lanes/lane-01"
    ).resolve()
    run_spec_path = lane / "run-spec.yaml"

    plan = load_deterministic_driver_plan(
        lane / "driver-plan.json",
        serialized_run_spec=run_spec_path.read_bytes(),
        run_spec_path=run_spec_path,
        expected_actions=KEYPAD_ACTIONS,
    )

    assert [action.action_id for action in plan.actions] == [
        f"action-{index:02d}" for index in range(1, 7)
    ]


@pytest.mark.parametrize(
    "mutator, message",
    [
        (
            lambda p: p["actions"][2].update({"resource_id": "equalsButton"}),
            "does not match",
        ),
        (
            lambda p: p["actions"][1].update({"center": "[150,1888]"}),
            "unknown field",
        ),
        (
            lambda p: p["actions"][1].update({"observation_interval_ms": 1}),
            "fixed",
        ),
    ],
)
def test_keypad_plan_rejects_order_coordinates_and_unbounded_timing(
    tmp_path: Path,
    mutator,
    message: str,
) -> None:
    raw = _keypad_run_spec_bytes()
    spec_path = tmp_path / "run-spec.yaml"
    spec_path.write_bytes(raw)
    payload = _keypad_plan_payload(spec_path.name, raw)
    mutator(payload)
    plan_path = _write_plan(tmp_path, payload)

    with pytest.raises(DeterministicDriverPlanError, match=message):
        load_deterministic_driver_plan(
            plan_path,
            serialized_run_spec=raw,
            run_spec_path=spec_path,
            expected_actions=KEYPAD_ACTIONS,
        )


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda p: p.update({"unexpected": True}), "unknown field"),
        (lambda p: p["actions"].append(dict(p["actions"][0])), "action count"),
        (lambda p: p["actions"][0].update({"timeout_ms": "5000"}), "timeout_ms"),
        (lambda p: p.update({"run_spec_sha256": "0" * 64}), "Run Spec digest"),
        (
            lambda p: p["actions"][0].update(
                {
                    "kind": "tap_resource_id",
                    "timeout_ms": 0,
                    "observation_interval_ms": 0,
                    "settle_ms": 350,
                }
            ),
            "does not match",
        ),
    ],
)
def test_invalid_plan_is_rejected_before_it_can_be_used(
    tmp_path: Path, mutator, message: str
) -> None:
    raw = _run_spec_bytes()
    payload = _plan_payload("run-spec.yaml", raw)
    mutator(payload)
    plan_path = _write_plan(tmp_path, payload)

    with pytest.raises(DeterministicDriverPlanError, match=message):
        load_deterministic_driver_plan(
            plan_path,
            serialized_run_spec=raw,
            run_spec_path=tmp_path / "run-spec.yaml",
            expected_actions=("wait for resource id oneButton",),
        )


def test_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    raw = _run_spec_bytes()
    payload = _plan_payload("run-spec.yaml", raw)
    duplicate = json.dumps(payload)[:-1] + ',"schema_version":1}\n'
    plan_path = tmp_path / "driver-plan.json"
    plan_path.write_text(duplicate, encoding="utf-8")

    with pytest.raises(DeterministicDriverPlanError, match="duplicate JSON key"):
        load_deterministic_driver_plan(
            plan_path,
            serialized_run_spec=raw,
            run_spec_path=tmp_path / "run-spec.yaml",
            expected_actions=("wait for resource id oneButton",),
        )


class RecordingLayoutAdapter:
    def __init__(self, observations: list[object]) -> None:
        self.observations = list(observations)
        self.calls = 0

    def read_layout(self) -> object:
        self.calls += 1
        if not self.observations:
            return [{"resource-id": "other"}]
        value = self.observations.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


class RecordingDeviceAdapter(RecordingLayoutAdapter):
    def __init__(
        self,
        observations: list[object],
        tap_results: list[object] | None = None,
    ) -> None:
        super().__init__(observations)
        self.tap_results = list(tap_results or [])
        self.taps: list[tuple[int, int]] = []

    def tap(self, x: int, y: int) -> CommandResult | None:
        self.taps.append((x, y))
        if not self.tap_results:
            return CommandResult(
                args=[
                    "adb",
                    "-s",
                    "emulator-5554",
                    "shell",
                    "input",
                    "tap",
                    str(x),
                    str(y),
                ],
                stdout="",
                stderr="",
                returncode=0,
            )
        value = self.tap_results.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def _loaded_keypad_plan(tmp_path: Path):
    raw = _keypad_run_spec_bytes()
    spec_path = tmp_path / "run-spec.yaml"
    spec_path.write_bytes(raw)
    plan_path = _write_plan(tmp_path, _keypad_plan_payload(spec_path.name, raw))
    return load_deterministic_driver_plan(
        plan_path,
        serialized_run_spec=raw,
        run_spec_path=spec_path,
        expected_actions=KEYPAD_ACTIONS,
    )


def _layout_response(
    resource_id: str,
    *,
    center: str | None = None,
    clickable: bool = True,
) -> LayoutObservation:
    node: dict[str, object] = {"resource-id": resource_id}
    if clickable:
        node["interactions"] = ["clickable", "focusable"]
    if center is not None:
        node["center"] = center
    return LayoutObservation(
        command=("android", "layout", "--device=emulator-5554", "--pretty"),
        stdout=json.dumps([node]),
    )


def _keypad_layouts() -> list[object]:
    centers = {
        "oneButton": "[150,1888]",
        "twoButton": "[409,1888]",
        "addButton": "[929,1888]",
        "threeButton": "[669,1888]",
        "fourButton": "[150,1590]",
    }
    return [
        _layout_response("oneButton"),
        *[
            _layout_response(
                action.removeprefix("tap resource id "),
                center=centers[action.removeprefix("tap resource id ")],
            )
            for action in KEYPAD_ACTIONS[1:]
        ],
    ]


class RecordingCommandRunner(CommandRunner):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.timeouts: list[int | None] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
        self.timeouts.append(timeout_seconds)
        return CommandResult(args=args, stdout="[]", stderr="", returncode=0)


def test_android_layout_adapter_uses_the_fixed_wait_read_timeout() -> None:
    runner = RecordingCommandRunner()
    adapter = AndroidLayoutDeviceAdapter(
        device="emulator-5554",
        android_bin="android",
        runner=runner,
    )

    observation = adapter.read_layout()

    assert observation.returncode == 0
    assert runner.calls == [[
        "android",
        "layout",
        "--device=emulator-5554",
        "--pretty",
    ]]
    assert runner.timeouts == [5]


def test_android_layout_adapter_taps_with_the_selected_device_and_fixed_timeout() -> None:
    runner = RecordingCommandRunner()
    adapter = AndroidLayoutDeviceAdapter(
        device="emulator-5554",
        android_bin="android",
        adb_bin="adb-custom",
        runner=runner,
    )

    result = adapter.tap(150, 1888)

    assert result.returncode == 0
    assert runner.calls == [[
        "adb-custom",
        "-s",
        "emulator-5554",
        "shell",
        "input",
        "tap",
        "150",
        "1888",
    ]]
    assert runner.timeouts == [5]


def _loaded_plan(tmp_path: Path):
    raw = _run_spec_bytes()
    spec_path = tmp_path / "run-spec.yaml"
    spec_path.write_bytes(raw)
    plan_path = _write_plan(tmp_path, _plan_payload(spec_path.name, raw))
    return load_deterministic_driver_plan(
        plan_path,
        serialized_run_spec=raw,
        run_spec_path=spec_path,
        expected_actions=("wait for resource id oneButton",),
    )


def test_keypad_executes_the_frozen_sequence_with_fresh_center_dispatches(
    tmp_path: Path,
) -> None:
    plan = _loaded_keypad_plan(tmp_path)
    adapter = RecordingDeviceAdapter(_keypad_layouts())
    sleeps: list[float] = []
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=adapter,
        sleeper=sleeps.append,
    )
    request = backend.build_request(
        segment_id="opencalc-preserve-expression-segment-0",
        action_offset=0,
        action_count=6,
        artifact_dir=tmp_path / "artifacts",
    )

    assert request.action_ids == tuple(f"action-{index}" for index in range(1, 7))
    assert [action.action_id for action in request.plan_actions] == [
        f"action-{index:02d}" for index in range(1, 7)
    ]
    result = backend.execute(request)

    assert adapter.calls == 6
    assert adapter.taps == [
        (150, 1888),
        (409, 1888),
        (929, 1888),
        (669, 1888),
        (150, 1590),
    ]
    assert sleeps == [0.35] * 5
    assert [item["status"] for item in result.data["results"]] == [
        "PASSED"
    ] * 6
    assert not any(
        "equals" in str(item).lower() for item in result.data["results"]
    )

    events = json.loads(result.events_path.read_text(encoding="utf-8"))
    assert len(events["observations"]) == 6
    assert [item["status"] for item in events["observations"]] == [
        "resource_found",
        "tap_target_validated",
        "tap_target_validated",
        "tap_target_validated",
        "tap_target_validated",
        "tap_target_validated",
    ]
    assert [item["resource_id"] for item in events["dispatches"]] == [
        "oneButton",
        "twoButton",
        "addButton",
        "threeButton",
        "fourButton",
    ]
    assert [item["center"] for item in events["dispatches"]] == [
        [150, 1888],
        [409, 1888],
        [929, 1888],
        [669, 1888],
        [150, 1590],
    ]
    assert all(item["status"] == "dispatched" for item in events["dispatches"])

    invocation = json.loads(
        (tmp_path / "artifacts" / "deterministic-driver-invocation.json").read_text(
            encoding="utf-8"
        )
    )
    assert invocation["action_ids"] == [f"action-{index}" for index in range(1, 7)]
    assert invocation["plan_action_ids"] == [
        f"action-{index:02d}" for index in range(1, 7)
    ]
    assert invocation["dispatch_count"] == 5
    assert invocation["command"][:2] == ["android", "layout"]
    assert all("equals" not in command for command in invocation["commands"])
    assert set(result.data) == {"schema_version", "journey", "results"}


@pytest.mark.parametrize(
    "layout, message, expected_status",
    [
        ([], "missing", "resource_missing"),
        (
            [
                {"resource-id": "oneButton"},
                {"resource-id": "oneButton"},
            ],
            "duplicated",
            "resource_duplicate",
        ),
        (
            [{"resource-id": "oneButton", "center": "[150,1888]"}],
            "not clickable",
            "resource_not_clickable",
        ),
        (
            [{"resource-id": "oneButton", "interactions": ["clickable"]}],
            "on-screen coordinate",
            "center_invalid",
        ),
        (
            [
                {
                    "resource-id": "oneButton",
                    "interactions": ["clickable"],
                    "center": "[150,1888]",
                    "bounds": "[0,0][100,100]",
                }
            ],
            "outside node bounds",
            "center_invalid",
        ),
        ("not-json-layout", "malformed", "malformed_layout"),
    ],
)
def test_tap_requires_one_clickable_target_with_a_valid_center(
    tmp_path: Path,
    layout: object,
    message: str,
    expected_status: str,
) -> None:
    plan = _loaded_keypad_plan(tmp_path)
    adapter = RecordingDeviceAdapter([layout])
    sleeps: list[float] = []
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=adapter,
        sleeper=sleeps.append,
    )
    request = backend.build_request(
        segment_id="opencalc-preserve-expression-segment-0",
        action_offset=1,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(DeterministicDriverError, match=message) as raised:
        backend.execute(request)

    assert adapter.calls == 1
    assert adapter.taps == []
    assert sleeps == []
    events = json.loads(raised.value.events_path.read_text(encoding="utf-8"))
    assert events["observations"][0]["status"] == expected_status
    assert events["dispatches"] == []


def test_tap_dispatch_failure_is_terminal_and_is_not_retried(tmp_path: Path) -> None:
    plan = _loaded_keypad_plan(tmp_path)
    adapter = RecordingDeviceAdapter(
        [_layout_response("oneButton", center="[150,1888]")],
        tap_results=[
            CommandResult(
                args=["adb", "tap", "150", "1888"],
                stdout="",
                stderr="transport failed",
                returncode=7,
            )
        ],
    )
    sleeps: list[float] = []
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=adapter,
        sleeper=sleeps.append,
    )
    request = backend.build_request(
        segment_id="opencalc-preserve-expression-segment-0",
        action_offset=1,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(DeterministicDriverError, match="tap command failed") as raised:
        backend.execute(request)

    assert adapter.taps == [(150, 1888)]
    assert sleeps == []
    events = json.loads(raised.value.events_path.read_text(encoding="utf-8"))
    assert len(events["dispatches"]) == 1
    assert events["dispatches"][0]["status"] == "failed"


@pytest.mark.parametrize("failure", [RuntimeError("tap transport closed"), None])
def test_tap_has_one_dispatch_even_when_dispatch_or_settle_is_interrupted(
    tmp_path: Path,
    failure: BaseException | None,
) -> None:
    plan = _loaded_keypad_plan(tmp_path)
    tap_results = [failure] if failure is not None else None
    adapter = RecordingDeviceAdapter(
        [_layout_response("oneButton", center="[150,1888]")],
        tap_results=tap_results,
    )
    sleeps: list[float] = []

    def interrupted_settle(seconds: float) -> None:
        sleeps.append(seconds)
        raise InterruptedError("settle cancelled")

    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=adapter,
        sleeper=interrupted_settle if failure is None else sleeps.append,
    )
    request = backend.build_request(
        segment_id="opencalc-preserve-expression-segment-0",
        action_offset=1,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    expected = "tap dispatch interrupted" if failure is not None else "settle interrupted"
    with pytest.raises(DeterministicDriverError, match=expected) as raised:
        backend.execute(request)

    assert adapter.taps == [(150, 1888)]
    assert len(sleeps) == (0 if failure is not None else 1)
    events = json.loads(raised.value.events_path.read_text(encoding="utf-8"))
    assert len(events["dispatches"]) == 1
    assert events["dispatches"][0]["status"] == (
        "interrupted" if failure is not None else "dispatched"
    )


def test_driver_plan_bytes_cannot_drift_between_admission_and_dispatch(
    tmp_path: Path,
) -> None:
    plan = _loaded_keypad_plan(tmp_path)
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=RecordingDeviceAdapter([]),
    )
    plan.path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(DeterministicDriverPlanError, match="drifted"):
        backend.build_request(
            segment_id="opencalc-preserve-expression-segment-0",
            action_offset=0,
            action_count=6,
            artifact_dir=tmp_path / "artifacts",
        )


def test_invalid_source_backed_plan_is_rejected_before_execution_record(
    tmp_path: Path,
) -> None:
    raw = (
        b"host_project: .\n"
        b"apk_glob: '*.apk'\n"
        b"package: org.example.app\n"
        b"activity: org.example.MainActivity\n"
        b"scenario:\n"
        b"  id: wait-smoke\n"
        b"  user_actions:\n"
        b"    - wait for resource id oneButton\n"
    )
    spec_path = tmp_path / "run-spec.yaml"
    spec_path.write_bytes(raw)
    spec = load_run_spec(spec_path)
    payload = _plan_payload(spec_path.name, raw)
    payload["unexpected"] = True
    plan_path = _write_plan(tmp_path, payload)
    artifact_dir = tmp_path / "run" / "artifacts"

    with pytest.raises(ProductionSeamAdmissionError, match="unknown field"):
        cli.run(
            spec,
            device="emulator-5554",
            artifact_dir=artifact_dir,
            workdir=tmp_path,
            backend=DETERMINISTIC_ANDROID_V1,
            driver_plan_path=plan_path,
        )

    assert not (artifact_dir.parent / "execution-record.json").exists()


def test_wait_uses_one_read_only_observation_and_writes_normalized_raw_evidence(
    tmp_path: Path,
) -> None:
    plan = _loaded_plan(tmp_path)
    adapter = RecordingLayoutAdapter([[{"resource-id": "org.example:id/oneButton"}]])
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=adapter,
    )
    request = backend.build_request(
        segment_id="wait-smoke-segment-0",
        action_offset=0,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    assert set(request.__dict__) == {
        "segment_id",
        "action_id",
        "plan_action",
        "device",
        "evidence_sink",
    }
    result = backend.execute(request)

    assert adapter.calls == 1
    assert result.backend == "deterministic_android_v1"
    assert result.data["results"] == [
        {
            "action_id": "action-1",
            "plan_action_id": "action-01",
            "status": "PASSED",
            "commands": [],
            "comment": "oneButton was observed exactly once; dispatch only.",
        }
    ]
    assert json.loads(result.result_path.read_text(encoding="utf-8"))["results"]
    observations = json.loads(result.events_path.read_text(encoding="utf-8"))
    assert observations["observations"][0]["status"] == "resource_found"
    assert observations["observations"][0]["layout"] == [
        {"resource-id": "org.example:id/oneButton"}
    ]


def test_wait_is_bounded_and_retains_every_missing_observation(tmp_path: Path) -> None:
    plan = _loaded_plan(tmp_path)
    adapter = RecordingLayoutAdapter([[{"resource-id": "other"}]] * 20)
    now = [0.0]
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=adapter,
        clock=lambda: now[0],
        sleeper=lambda seconds: now.__setitem__(0, now[0] + seconds),
    )
    request = backend.build_request(
        segment_id="wait-smoke-segment-0",
        action_offset=0,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(DeterministicDriverError, match="timed out") as raised:
        backend.execute(request)

    assert adapter.calls == 15
    assert raised.value.events_path is not None
    observations = json.loads(raised.value.events_path.read_text(encoding="utf-8"))
    assert len(observations["observations"]) == adapter.calls
    assert all(item["status"] == "resource_missing" for item in observations["observations"])


@pytest.mark.parametrize(
    "layout, message",
    [
        ([{"resource-id": "oneButton"}, {"resource-id": "oneButton"}], "duplicate"),
        ("not-json-layout", "malformed"),
    ],
)
def test_wait_rejects_ambiguous_or_malformed_layouts(
    tmp_path: Path, layout: object, message: str
) -> None:
    plan = _loaded_plan(tmp_path)
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=RecordingLayoutAdapter([layout]),
    )
    request = backend.build_request(
        segment_id="wait-smoke-segment-0",
        action_offset=0,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(DeterministicDriverError, match=message):
        backend.execute(request)


def test_interrupted_layout_read_keeps_raw_attempt_artifacts(tmp_path: Path) -> None:
    plan = _loaded_plan(tmp_path)
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=RecordingLayoutAdapter([RuntimeError("layout transport closed")]),
    )
    request = backend.build_request(
        segment_id="wait-smoke-segment-0",
        action_offset=0,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(DeterministicDriverError, match="layout transport closed") as raised:
        backend.execute(request)

    assert raised.value.result_path is not None and raised.value.result_path.is_file()
    assert raised.value.events_path is not None and raised.value.events_path.is_file()


def test_interrupted_wait_keeps_the_observation_before_sleep(tmp_path: Path) -> None:
    plan = _loaded_plan(tmp_path)

    def interrupted_sleep(seconds: float) -> None:
        raise InterruptedError("cancelled")

    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=RecordingLayoutAdapter([[{"resource-id": "other"}]]),
        sleeper=interrupted_sleep,
    )
    request = backend.build_request(
        segment_id="wait-smoke-segment-0",
        action_offset=0,
        action_count=1,
        artifact_dir=tmp_path / "artifacts",
    )

    with pytest.raises(DeterministicDriverError, match="wait interrupted") as raised:
        backend.execute(request)

    observations = json.loads(raised.value.events_path.read_text(encoding="utf-8"))
    assert [item["status"] for item in observations["observations"]] == [
        "resource_missing",
        "interrupted",
    ]


class RecordingCheckpointCollector:
    def capture_checkpoint(
        self,
        *,
        name: str,
        output_dir: Path,
        device: str | None = None,
        annotated: bool = True,
    ) -> EvidenceCheckpoint:
        directory = output_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        layout = directory / "layout.json"
        layout.write_text("[]", encoding="utf-8")
        screen = directory / "screen.png"
        screen.write_bytes(b"png")
        logcat = directory / "logcat.txt"
        logcat.write_text("", encoding="utf-8")
        commands = directory / "commands.json"
        commands.write_text("[]", encoding="utf-8")
        return EvidenceCheckpoint(
            name=name,
            directory=directory,
            layout_path=layout,
            screenshot_path=screen,
            annotated_screenshot_path=None,
            logcat_path=logcat,
            commands_path=commands,
        )


def test_runner_emits_backend_neutral_normalized_result_and_lineage(
    tmp_path: Path,
) -> None:
    plan = _loaded_plan(tmp_path)
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=RecordingLayoutAdapter([[{"resource-id": "oneButton"}]]),
    )
    flow = JourneySegmentRunner(
        backend=backend,
        checkpoint_collector=RecordingCheckpointCollector(),
        system_event_injector=lambda event: None,
    ).run(
        scenario=ScenarioSpec(
            id="wait-smoke",
            user_actions=["wait for resource id oneButton"],
        ),
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=tmp_path / "unused-schema.json",
        device="emulator-5554",
    )

    result = flow.journey_results[0]
    assert result.result_path.name == "journey-result.normalized.json"
    assert result.action_lineage_path is not None
    lineage = json.loads(result.action_lineage_path.read_text(encoding="utf-8"))
    assert lineage["backend"] == "deterministic_android_v1"
    assert lineage["results"] == [
        {
            "action_id": "action-1",
            "plan_action_id": "action-01",
            "requested_action": "wait for resource id oneButton",
            "status": "PASSED",
        }
    ]
    assert not (result.result_path.parent / "codex-journey-result.normalized.json").exists()


def test_runner_preserves_all_keypad_action_lineage_without_oracle_fields(
    tmp_path: Path,
) -> None:
    plan = _loaded_keypad_plan(tmp_path)
    backend = DeterministicAndroidBackend(
        plan=plan,
        device="emulator-5554",
        device_adapter=RecordingDeviceAdapter(_keypad_layouts()),
        sleeper=lambda seconds: None,
    )
    flow = JourneySegmentRunner(
        backend=backend,
        checkpoint_collector=RecordingCheckpointCollector(),
        system_event_injector=lambda event: None,
    ).run(
        scenario=ScenarioSpec(id="opencalc-preserve-expression", user_actions=list(KEYPAD_ACTIONS)),
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=tmp_path / "unused-schema.json",
        device="emulator-5554",
    )

    result = flow.journey_results[0]
    lineage = json.loads(result.action_lineage_path.read_text(encoding="utf-8"))
    assert [item["requested_action"] for item in lineage["results"]] == list(
        KEYPAD_ACTIONS
    )
    assert [item["action_id"] for item in lineage["results"]] == [
        f"action-{index}" for index in range(1, 7)
    ]
    assert [item["plan_action_id"] for item in lineage["results"]] == [
        f"action-{index:02d}" for index in range(1, 7)
    ]
    assert lineage["results"][0] == {
        "action_id": "action-1",
        "plan_action_id": "action-01",
        "requested_action": KEYPAD_ACTIONS[0],
        "status": "PASSED",
        "operation": "observation_probe",
    }
    for item in lineage["results"][1:]:
        assert item["operation"] == "side_effect_dispatch"
    assert not any(
        key in result.data for key in ("L1", "L2", "L3", "finding", "oracle")
    )


def test_deterministic_identity_records_real_tool_and_zero_model_calls(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts"
    binary_path = tmp_path / "bin" / "android"
    binary_path.parent.mkdir()
    binary_path.write_text("android test binary\n", encoding="utf-8")
    binary = {
        "requested": str(binary_path),
        "resolved_path": str(binary_path.resolve()),
        "sha256": hashlib.sha256(binary_path.read_bytes()).hexdigest(),
        "version": "android-cli test-v1",
    }
    binary["identity_sha256"] = hashlib.sha256(
        json.dumps(
            binary,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    raw_dir = artifact_dir / "wait-smoke-segment-0"
    raw_dir.mkdir(parents=True)
    raw_path = raw_dir / "deterministic-driver-invocation.json"
    result_path = raw_dir / "deterministic-journey-result.json"
    events_path = raw_dir / "deterministic-observations.json"
    result_path.write_text("{}\n", encoding="utf-8")
    events_path.write_text("{}\n", encoding="utf-8")
    raw_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": DETERMINISTIC_ANDROID_V1,
                "role": "journey_driver",
                "journey": "wait-smoke-segment-0",
                "action_id": "action-1",
                "plan_action_id": "action-01",
                "requested_model": None,
                "effective_model": None,
                "model_calls": 0,
                "command": [str(binary_path), "layout", "--device=emulator-5554", "--pretty"],
                "result_path": str(result_path),
                "events_path": str(events_path),
                "raw_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                "raw_events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
                "observation_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    collector = ExecutionIdentityCollector(
        run_dir=run_dir,
        artifact_dir=artifact_dir,
        attempt_id="attempt-deterministic",
        spec=RunSpec(
            host_project=tmp_path,
            apk_glob="*.apk",
            package="org.example.app",
            activity="org.example.MainActivity",
            diff=None,
            spec=None,
            scenario=ScenarioSpec(id="wait-smoke", user_actions=["wait for resource id oneButton"]),
        ),
        run_spec_path=tmp_path / "run-spec.yaml",
        workdir=tmp_path,
        device="emulator-5554",
        requested_driver_model=None,
        requested_l3_model=None,
        journey_driver_backend=DETERMINISTIC_ANDROID_V1,
        android_bin=str(binary_path),
    )
    collector._static = {"tools": {"android_cli": binary}}

    collector._materialize_deterministic_identity_receipts()
    role = collector._role_identity(
        "journey_driver",
        [raw_dir / "deterministic-invocation-identity.json"],
        None,
        [raw_dir / "deterministic-invocation-ledger.json"],
        binary,
        backend=DETERMINISTIC_ANDROID_V1,
    )

    assert role["effective_model"] is None
    assert role["model_calls"] == 0
    identity = json.loads(
        (raw_dir / "deterministic-invocation-identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert identity["binary"]["resolved_path"] == str(binary_path.resolve())
    assert identity["model_identity"] == {
        "status": "not_applicable",
        "reason": "deterministic_backend_has_no_model_role",
    }
    assert identity["raw_result_sha256"] == hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
    assert identity["raw_events_sha256"] == hashlib.sha256(
        events_path.read_bytes()
    ).hexdigest()

    result_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ExecutionIdentityError, match="raw artifact checksum"):
        collector._materialize_deterministic_identity_receipts()


def test_deterministic_attempt_identity_materializes_role_artifacts(tmp_path: Path) -> None:
    """Non-accountable deterministic attempts still retain a zero-call ledger."""
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts"
    binary_path = tmp_path / "bin" / "android"
    binary_path.parent.mkdir()
    binary_path.write_text("android test binary\n", encoding="utf-8")
    result_path = artifact_dir / "wait-smoke-segment-0" / "deterministic-journey-result.json"
    events_path = artifact_dir / "wait-smoke-segment-0" / "deterministic-observations.json"
    raw_path = artifact_dir / "wait-smoke-segment-0" / "deterministic-driver-invocation.json"
    result_path.parent.mkdir(parents=True)
    result_path.write_text("{}\n", encoding="utf-8")
    events_path.write_text("{}\n", encoding="utf-8")
    raw_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "backend": DETERMINISTIC_ANDROID_V1,
                "role": "journey_driver",
                "journey": "wait-smoke-segment-0",
                "action_id": "action-1",
                "plan_action_id": "action-01",
                "requested_model": None,
                "effective_model": None,
                "model_calls": 0,
                "command": [str(binary_path), "layout"],
                "result_path": str(result_path),
                "events_path": str(events_path),
                "raw_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                "raw_events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
                "observation_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    binary = {
        "requested": str(binary_path),
        "resolved_path": str(binary_path.resolve()),
        "sha256": hashlib.sha256(binary_path.read_bytes()).hexdigest(),
        "version": "android-cli test-v1",
    }
    binary["identity_sha256"] = hashlib.sha256(
        json.dumps(binary, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    collector = object.__new__(ExecutionIdentityCollector)
    collector.artifact_dir = artifact_dir.resolve()
    collector.journey_driver_backend = DETERMINISTIC_ANDROID_V1
    collector.attempt_id = "attempt-deterministic"
    collector._static = {"tools": {"android_cli": binary}}

    paths = collector.materialize_deterministic_attempt_identity()

    assert [path.name for path in paths] == [
        "deterministic-invocation-identity.json",
        "deterministic-invocation-ledger.json",
    ]
    ledger = json.loads(paths[1].read_text(encoding="utf-8"))
    assert ledger["model_calls"] == 0
    assert ledger["requested_model"] is None
    assert ledger["effective_model"] is None


def test_multi_action_identity_retains_exact_sequence_and_zero_model_calls(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts"
    binary_path = tmp_path / "bin" / "android"
    binary_path.parent.mkdir()
    binary_path.write_text("android test binary\n", encoding="utf-8")
    binary = {
        "requested": str(binary_path),
        "resolved_path": str(binary_path.resolve()),
        "sha256": hashlib.sha256(binary_path.read_bytes()).hexdigest(),
        "version": "android-cli test-v1",
    }
    binary["identity_sha256"] = hashlib.sha256(
        json.dumps(binary, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    layout_command = (
        str(binary_path),
        "layout",
        "--device=emulator-5554",
        "--pretty",
    )
    observations = [
        LayoutObservation(command=layout_command, stdout=value.stdout)
        for value in _keypad_layouts()
    ]
    backend = DeterministicAndroidBackend(
        plan=_loaded_keypad_plan(tmp_path),
        device="emulator-5554",
        device_adapter=RecordingDeviceAdapter(observations),
        sleeper=lambda seconds: None,
    )
    request = backend.build_request(
        segment_id="opencalc-preserve-expression-segment-0",
        action_offset=0,
        action_count=6,
        artifact_dir=artifact_dir / "opencalc-preserve-expression-segment-0",
    )
    backend.execute(request)

    collector = object.__new__(ExecutionIdentityCollector)
    collector.run_dir = run_dir.resolve()
    collector.artifact_dir = artifact_dir.resolve()
    collector.attempt_id = "attempt-deterministic"
    collector.workdir = tmp_path.resolve()
    collector.journey_driver_backend = DETERMINISTIC_ANDROID_V1
    collector._static = {"tools": {"android_cli": binary}}
    collector._materialize_deterministic_identity_receipts()

    identity_path = (
        artifact_dir
        / "opencalc-preserve-expression-segment-0"
        / "deterministic-invocation-identity.json"
    )
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    assert identity["action_ids"] == [f"action-{index}" for index in range(1, 7)]
    assert identity["plan_action_ids"] == [
        f"action-{index:02d}" for index in range(1, 7)
    ]
    assert identity["dispatch_count"] == 5
    assert identity["model_calls"] == 0
    collector._role_identity(
        "journey_driver",
        [identity_path],
        None,
        [identity_path.with_name("deterministic-invocation-ledger.json")],
        binary,
        backend=DETERMINISTIC_ANDROID_V1,
    )


def test_cli_public_deterministic_run_records_verified_real_tool_identity(
    tmp_path: Path, monkeypatch
) -> None:
    """The public runner path emits verifiable deterministic identity evidence."""
    source_path = tmp_path / "run-spec.yaml"
    source_path.write_text(
        "host_project: .\n"
        "apk_glob: '*.apk'\n"
        "package: org.example.app\n"
        "activity: org.example.MainActivity\n"
        "scenario:\n"
        "  id: deterministic-public-smoke\n"
        "  user_actions:\n"
        "    - wait for resource id oneButton\n",
        encoding="utf-8",
    )
    (tmp_path / "base.apk").write_bytes(b"test apk")
    spec = load_run_spec(source_path)
    plan_path = _write_plan(tmp_path, _plan_payload(source_path.name, source_path.read_bytes()))
    binary_path = tmp_path / "bin" / "android"
    binary_path.parent.mkdir()
    binary_path.write_text("android test binary\n", encoding="utf-8")
    binary_sha256 = hashlib.sha256(binary_path.read_bytes()).hexdigest()

    def identity_checksum(value: dict) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def tool(requested: str, version: str) -> dict[str, str]:
        value = {
            "requested": requested,
            "resolved_path": str(binary_path.resolve()),
            "sha256": binary_sha256,
            "version": version,
        }
        value["identity_sha256"] = identity_checksum(value)
        return value

    tools = {
        "android_cli": tool(str(binary_path), "android-cli test-v1"),
        "adb": tool("adb", "adb test-v1"),
        "git": tool("git", "git test-v1"),
        "python": tool("python", "python test-v1"),
    }
    apk_path = tmp_path / "base.apk"
    apk = {
        "path": str(apk_path.resolve()),
        "bytes": apk_path.stat().st_size,
        "sha256": hashlib.sha256(apk_path.read_bytes()).hexdigest(),
    }
    device = {
        "serial": "emulator-5554",
        "api_level": "35",
        "build_fingerprint": "test/fingerprint",
        "profile": {
            "kind": "emulator",
            "name": "test-avd",
            "model": "test-model",
            "device": "test-device",
        },
    }

    def host() -> dict[str, object]:
        status = ""
        return {
            "repository_root": str(tmp_path.resolve()),
            "origin": "https://example.invalid/repository.git",
            "commit": "a" * 40,
            "worktree": {
                "clean": True,
                "status": status,
                "status_sha256": hashlib.sha256(status.encode()).hexdigest(),
                "untracked_files": [],
            },
            "patch_bytes": b"",
        }

    class StubbedIdentityCollector(ExecutionIdentityCollector):
        def _host_identity(self):
            return host()

        def _apk_artifacts(self):
            return [dict(apk)]

        def _device_identity(self):
            return {
                **device,
                "profile": dict(device["profile"]),
            }

        def _tools_identity(self):
            return {key: dict(value) for key, value in tools.items()}

        def _installed_artifacts(self):
            return [{"path": "/data/app/org.example.app/base.apk", "sha256": apk["sha256"]}]

        def _adb(self, *args: str):
            return CommandResult(
                args=["adb", "-s", self.device_serial, *args],
                stdout="org.example.app/org.example.MainActivity\n",
                stderr="",
                returncode=0,
            )

        def deploy(self):
            command = [
                self.android_bin,
                "run",
                f"--device={self.device_serial}",
                f"--apks={apk['path']}",
                "--activity=org.example.MainActivity",
                "--type=ACTIVITY",
            ]
            process = {
                "args": command,
                "returncode": 0,
                "stdout": "deployed\n",
                "stderr": "",
            }
            process["identity_sha256"] = identity_checksum(process)
            deployed_device = self._device_identity()
            deployed_device["identity_sha256"] = identity_checksum(deployed_device)
            self._deployment = {
                "target": self._target_identity(),
                "process": process,
                "installed_artifacts": self._installed_artifacts(),
                "resolved_component": "org.example.app/org.example.MainActivity",
                "device": deployed_device,
                "tools": {
                    "android_cli_sha256": tools["android_cli"]["sha256"],
                    "adb_sha256": tools["adb"]["sha256"],
                },
            }
            self._deployment["identity_sha256"] = identity_checksum(self._deployment)
            return self._deployment

    class PassingPreflightRunner(CommandRunner):
        def __init__(self) -> None:
            self.responses = [
                "List of devices attached\nemulator-5554 device\n",
                "1\n",
                "stopped\n",
                "[]",
                "UI hierarchy dumped\n",
            ]

        def run(
            self,
            args: list[str],
            *,
            cwd: Path | None = None,
            timeout_seconds: int | None = None,
            input_text: str | None = None,
        ) -> CommandResult:
            return CommandResult(
                args=args,
                stdout=self.responses.pop(0),
                stderr="",
                returncode=0,
            )

    class FakeDeviceController:
        def __init__(self, serial: str) -> None:
            self.serial = serial

        def logcat_clear(self) -> AdbResult:
            return AdbResult(stdout="", stderr="", returncode=0)

        def launch(self, package: str, activity: str | None) -> AdbResult:
            return AdbResult(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(cli, "AndroidEvidenceCollector", RecordingCheckpointCollector)
    def identity_factory(attempt_id: str) -> StubbedIdentityCollector:
        collector = StubbedIdentityCollector(
            run_dir=tmp_path / "run",
            artifact_dir=tmp_path / "run" / "artifacts",
            attempt_id=attempt_id,
            spec=spec,
            run_spec_path=source_path,
            workdir=tmp_path,
            device="emulator-5554",
            requested_driver_model=None,
            requested_l3_model=None,
            android_bin=str(binary_path),
            adb_bin="adb",
            codex_bin="codex",
            journey_driver_backend=DETERMINISTIC_ANDROID_V1,
        )
        return collector

    backend = DeterministicAndroidBackend(
        plan=load_deterministic_driver_plan(
            plan_path,
            serialized_run_spec=source_path.read_bytes(),
            run_spec_path=source_path,
            expected_actions=spec.scenario.user_actions,
        ),
        device="emulator-5554",
        android_bin=str(binary_path),
        device_adapter=RecordingLayoutAdapter(
            [
                LayoutObservation(
                    command=(str(binary_path), "layout", "--device=emulator-5554", "--pretty"),
                    stdout='[{"resource-id":"oneButton"}]',
                )
            ]
        ),
    )
    run_dir = tmp_path / "run"
    verdict = cli.run(
        spec,
        device="emulator-5554",
        artifact_dir=run_dir / "artifacts",
        workdir=tmp_path,
        launch=False,
        backend=DETERMINISTIC_ANDROID_V1,
        driver_plan_path=plan_path,
        journey_backend=backend,
        preflight_command_runner=PassingPreflightRunner(),
        identity_collector_factory=identity_factory,
    )

    assert verdict["execution"]["status"] == "completed"
    record = json.loads((run_dir / "execution-record.json").read_text(encoding="utf-8"))
    assert record["evidence_refs"]["execution_provenance"]["path"] == "execution-provenance.json"
    provenance = verify_execution_provenance(
        verdict["execution_provenance"],
        attempt_id=record["attempt_id"],
        scenario=spec.scenario.id,
        base_dir=run_dir,
    )
    assert "codex_cli" not in provenance["tools"]
    driver = provenance["roles"]["journey_driver"]
    assert driver["effective_model"] is None
    assert driver["model_calls"] == 0
    ledger_path = run_dir / driver["invocation_ledger"][0]["path"]
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert ledger["model_calls"] == 0
    assert ledger["requested_model"] is None
    assert ledger["effective_model"] is None
