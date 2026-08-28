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


@pytest.mark.parametrize(
    "mutator, message",
    [
        (lambda p: p.update({"unexpected": True}), "unknown field"),
        (lambda p: p["actions"].append(dict(p["actions"][0])), "action count"),
        (lambda p: p["actions"][0].update({"timeout_ms": "5000"}), "timeout_ms"),
        (lambda p: p.update({"run_spec_sha256": "0" * 64}), "Run Spec digest"),
        (lambda p: p["actions"][0].update({"kind": "tap_resource_id"}), "only admits"),
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
