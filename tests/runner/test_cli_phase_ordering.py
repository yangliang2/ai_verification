"""Hermetic Runner CLI phase-ordering contracts for Issue #169."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import aiverify.runner.cli as cli
from aiverify.bench.live_validation_gate import GateResult
from aiverify.harness.device import AdbResult
from aiverify.runner.admission import (
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
)
from aiverify.runner.codex_backend import JourneyExecutionResult
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.execution_record import ExecutionRecordStore
from aiverify.runner.journey import JourneyExecutionInterrupted, JourneySegmentFlow
from aiverify.runner.run_spec import (
    MetricContextSpec,
    RunSpec,
    ScenarioSpec,
    SystemEventSpec,
)


_SIDE_EFFECT_ORDER = (
    "pre-run-setup",
    "static-identity-capture",
    "live-validation-preflight",
    "identity-deployment",
    "identity-readiness",
    "device-controller",
    "device-logcat-clear",
    "device-launch",
    "checkpoint-collector",
    "verification-agent-backend",
    "system-event-injector",
    "journey-runner",
    "runner-setup-output",
    "journey-execution",
    "oracle-l1",
    "oracle-l2",
    "oracle-l3-model",
    "identity-finalization",
    "verdict-output",
)


@dataclass
class PhaseTrace:
    """Record every hermetic replacement for a potentially external phase."""

    calls: list[str] = field(default_factory=list)

    def record(self, phase: str) -> None:
        self.calls.append(phase)


@dataclass(frozen=True)
class FailureCase:
    """One earliest injected failure and its expected terminal state."""

    id: str
    failure_action: str | None
    terminal_action: str
    reason: str
    preflight_rejected: bool = False
    launch: bool = True


_FAILURE_CASES = (
    FailureCase(
        id="pre-run-setup",
        failure_action="pre-run-setup",
        terminal_action="pre-run-setup",
        reason="pre_run_setup_error",
    ),
    FailureCase(
        id="static-identity",
        failure_action="static-identity-capture",
        terminal_action="static-identity-capture",
        reason="execution_identity_error",
    ),
    FailureCase(
        id="preflight-exception",
        failure_action="live-validation-preflight",
        terminal_action="live-validation-preflight",
        reason="live_validation_preflight_failed",
    ),
    FailureCase(
        id="preflight-rejection",
        failure_action=None,
        terminal_action="live-validation-preflight",
        reason="live_validation_preflight_failed",
        preflight_rejected=True,
    ),
    FailureCase(
        id="deployment",
        failure_action="identity-deployment",
        terminal_action="identity-deployment",
        reason="execution_identity_error",
    ),
    FailureCase(
        id="readiness",
        failure_action="identity-readiness",
        terminal_action="identity-readiness",
        reason="execution_identity_error",
    ),
    FailureCase(
        id="runner-setup",
        failure_action="device-logcat-clear",
        terminal_action="device-logcat-clear",
        reason="runner_setup_error",
    ),
    FailureCase(
        id="runner-setup-output",
        failure_action="runner-setup-output",
        terminal_action="runner-setup-output",
        reason="runner_setup_error",
    ),
    FailureCase(
        id="journey",
        failure_action="journey-execution",
        terminal_action="journey-execution",
        reason="journey_execution_error",
    ),
    FailureCase(
        id="journey-without-launch",
        failure_action="journey-execution",
        terminal_action="journey-execution",
        reason="journey_execution_error",
        launch=False,
    ),
    FailureCase(
        id="oracle",
        failure_action="oracle-l1",
        terminal_action="oracle-l1",
        reason="oracle_execution_error",
    ),
    FailureCase(
        id="identity-finalize",
        failure_action="identity-finalization",
        terminal_action="identity-finalization",
        reason="execution_identity_error",
    ),
    FailureCase(
        id="verdict-output",
        failure_action="verdict-output",
        terminal_action="verdict-output",
        reason="output_finalization_error",
    ),
)


def _expected_side_effect_prefix(case: FailureCase) -> tuple[str, ...]:
    """Return the exact side-effect prefix permitted before one failure."""
    terminal_index = _SIDE_EFFECT_ORDER.index(case.terminal_action)
    return tuple(
        action
        for action in _SIDE_EFFECT_ORDER[: terminal_index + 1]
        if case.launch or action != "device-launch"
    )


def _spec(
    tmp_path: Path,
    *,
    source_path: Path | None = None,
    metric_context: MetricContextSpec | None = None,
    l3_spec: str = "",
) -> RunSpec:
    return RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.example.phaseordering",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(
            id="runner-cli-phase-ordering",
            user_actions=["observe the initial screen"],
            metric_context=metric_context or MetricContextSpec(),
            l3_spec=l3_spec,
        ),
        source_path=source_path,
        source_sha256="0" * 64 if source_path is not None else None,
    )


def _flow(tmp_path: Path) -> JourneySegmentFlow:
    checkpoint_dir = tmp_path / "flow" / "after-segment-0"
    checkpoint_dir.mkdir(parents=True)
    layout = checkpoint_dir / "layout.json"
    layout.write_text("[]", encoding="utf-8")
    screenshot = checkpoint_dir / "screen.png"
    screenshot.write_bytes(b"png")
    logcat = checkpoint_dir / "logcat.txt"
    logcat.write_text("", encoding="utf-8")
    commands = checkpoint_dir / "commands.json"
    commands.write_text("[]", encoding="utf-8")
    result_path = checkpoint_dir / "journey-result.json"
    events_path = checkpoint_dir / "journey-events.jsonl"
    result_path.write_text('{"journey":"phase-ordering"}', encoding="utf-8")
    events_path.write_text("", encoding="utf-8")
    checkpoint = EvidenceCheckpoint(
        name="after-segment-0",
        directory=checkpoint_dir,
        layout_path=layout,
        screenshot_path=screenshot,
        annotated_screenshot_path=None,
        logcat_path=logcat,
        commands_path=commands,
    )
    result = JourneyExecutionResult(
        data={"journey": "phase-ordering", "results": []},
        result_path=result_path,
        events_path=events_path,
        command=["hermetic-fake-backend"],
    )
    return JourneySegmentFlow(journey_results=[result], checkpoints=[checkpoint])


def _oracle_verdict(level: str = "L1") -> dict[str, object]:
    return {
        "verdict_id": f"{level}-hermetic",
        "level": level,
        "outcome": "pass",
        "defect_class_hypothesis": None,
        "trigger_steps": [],
        "evidence": [],
        "confidence": 1.0,
    }


def _record_side_effect(
    trace: PhaseTrace, case: FailureCase, action: str
) -> None:
    """Record one sealed seam and raise only for this case's earliest failure."""
    trace.record(action)
    if case.failure_action == action:
        raise RuntimeError(f"controlled {action} failure")


def _install_phase_fences(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tmp_path: Path,
    trace: PhaseTrace,
    case: FailureCase,
) -> None:
    """Replace every external seam with traceable, local-only stand-ins."""

    def preflight(
        spec: RunSpec,
        *,
        device: str,
        artifact_dir: Path,
        runner: object,
    ) -> tuple[GateResult, Path, dict, dict]:
        del spec, runner
        _record_side_effect(trace, case, "live-validation-preflight")
        status = "failed" if case.preflight_rejected else "passed"
        result = GateResult(device=device, status=status, checks=())
        path = artifact_dir.parent / "live-validation-gate.json"
        cli.write_json_artifact(path, result.to_dict())
        return (
            result,
            path,
            cli._live_validation_gate_summary(result, path=path),
            {
                "phase": "live-validation-preflight",
                "kind": "preflight",
                "seconds": 0.0,
            },
        )

    class TraceController:
        def __init__(self, serial: str) -> None:
            self.serial = serial
            _record_side_effect(trace, case, "device-controller")

        def logcat_clear(self) -> AdbResult:
            _record_side_effect(trace, case, "device-logcat-clear")
            return AdbResult(stdout="", stderr="", returncode=0)

        def launch(self, package: str, activity: str | None) -> AdbResult:
            del package, activity
            _record_side_effect(trace, case, "device-launch")
            return AdbResult(stdout="", stderr="", returncode=0)

    class TraceCheckpointCollector:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            _record_side_effect(trace, case, "checkpoint-collector")

    class TraceBackend:
        def __init__(self) -> None:
            _record_side_effect(trace, case, "verification-agent-backend")

    class TraceSystemEventInjector:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            _record_side_effect(trace, case, "system-event-injector")

    class TraceJourneyRunner:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            _record_side_effect(trace, case, "journey-runner")

        def run(self, **kwargs: object) -> JourneySegmentFlow:
            del kwargs
            _record_side_effect(trace, case, "journey-execution")
            return _flow(tmp_path)

    class TraceL1Oracle:
        def judge(self, *args: object, **kwargs: object) -> dict[str, object]:
            del args, kwargs
            _record_side_effect(trace, case, "oracle-l1")
            return _oracle_verdict()

    def judge_l2(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        _record_side_effect(trace, case, "oracle-l2")
        return _oracle_verdict("L2")

    def judge_l3(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        _record_side_effect(trace, case, "oracle-l3-model")
        return _oracle_verdict("L3")

    original_write_json = cli.write_json_artifact

    def write_json(path: Path, payload: object) -> None:
        if (
            Path(path).name == "runner-setup.json"
            and isinstance(payload, dict)
            and payload.get("status") == "passed"
        ):
            trace.record("runner-setup-output")
            if case.failure_action == "runner-setup-output":
                original_write_json(path, payload)
                raise RuntimeError("controlled runner setup output failure")
        if (
            Path(path).name == "verdict.json"
            and case.failure_action == "verdict-output"
        ):
            _record_side_effect(trace, case, "verdict-output")
        original_write_json(path, payload)

    monkeypatch.setattr(cli, "_run_live_validation_preflight", preflight)
    monkeypatch.setattr(cli, "DeviceController", TraceController)
    monkeypatch.setattr(cli, "AndroidEvidenceCollector", TraceCheckpointCollector)
    monkeypatch.setattr(cli, "CodexCliBackend", TraceBackend)
    monkeypatch.setattr(cli, "DeviceSystemEventInjector", TraceSystemEventInjector)
    monkeypatch.setattr(cli, "JourneySegmentRunner", TraceJourneyRunner)
    monkeypatch.setattr(cli, "L1Oracle", TraceL1Oracle)
    monkeypatch.setattr(cli, "_judge_l2_from_checkpoints", judge_l2)
    monkeypatch.setattr(cli, "_judge_l3", judge_l3)
    monkeypatch.setattr(cli, "write_json_artifact", write_json)


def _record_terminalization(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], list[str]]:
    established: list[str] = []
    finalized: list[str] = []
    original_establish = cli.ExecutionRecordStore.establish
    original_finalize = cli.ExecutionRecordStore.finalize

    def establish(*args: object, **kwargs: object) -> ExecutionRecordStore:
        store = original_establish(*args, **kwargs)
        established.append(store.attempt_id)
        return store

    def finalize(
        store: ExecutionRecordStore, *args: object, **kwargs: object
    ) -> dict:
        finalized.append(store.attempt_id)
        return original_finalize(store, *args, **kwargs)

    monkeypatch.setattr(cli.ExecutionRecordStore, "establish", establish)
    monkeypatch.setattr(cli.ExecutionRecordStore, "finalize", finalize)
    return established, finalized


def _assert_terminal_non_accountable(
    *,
    artifact_dir: Path,
    verdict: dict,
    expected_reason: str,
    established: list[str],
    finalized: list[str],
) -> None:
    record_path = artifact_dir.parent / "execution-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))

    assert established == [record["attempt_id"]]
    assert finalized == [record["attempt_id"]]
    assert record["lifecycle_state"] != "in_progress"
    assert verdict["execution"]["status"] == "non_accountable"
    assert verdict["execution"]["accounting_eligible"] is False
    assert verdict["execution"]["reason"] == expected_reason
    assert record["execution"] == verdict["execution"]
    assert len(record["phase_errors"]) == 1
    assert record["phase_errors"][-1]["reason"] == expected_reason
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    assert "execution_provenance" not in record["evidence_refs"]


@pytest.mark.parametrize("case", _FAILURE_CASES, ids=lambda case: case.id)
def test_runner_failure_at_each_phase_blocks_later_external_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: FailureCase,
) -> None:
    """Each earliest failure terminalizes once before a later side effect."""
    trace = PhaseTrace()
    _install_phase_fences(
        monkeypatch,
        tmp_path=tmp_path,
        trace=trace,
        case=case,
    )
    established, finalized = _record_terminalization(monkeypatch)
    artifact_dir = tmp_path / "run" / "artifacts"

    def pre_run_setup() -> None:
        _record_side_effect(trace, case, "pre-run-setup")

    verdict = cli.run(
        _spec(tmp_path, l3_spec="the screen remains usable"),
        device="hermetic-device",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        launch=case.launch,
        pre_run_setup=pre_run_setup,
        identity_collector=_traced_identity_collector(trace, case, tmp_path),
    )

    _assert_terminal_non_accountable(
        artifact_dir=artifact_dir,
        verdict=verdict,
        expected_reason=case.reason,
        established=established,
        finalized=finalized,
    )
    assert tuple(trace.calls) == _expected_side_effect_prefix(case)
    if not case.launch:
        assert "device-launch" not in trace.calls


def _traced_identity_collector(
    trace: PhaseTrace,
    case: FailureCase,
    tmp_path: Path,
) -> object:
    """Return the identity seam for one strict side-effect trace."""

    class Identity:
        def capture_static(self) -> None:
            _record_side_effect(trace, case, "static-identity-capture")

        def deploy(self) -> None:
            _record_side_effect(trace, case, "identity-deployment")

        def verify_ready_for_agent(self) -> None:
            _record_side_effect(trace, case, "identity-readiness")

        def finalize(self, **kwargs: object) -> dict[str, str]:
            del kwargs
            _record_side_effect(trace, case, "identity-finalization")
            provenance = tmp_path / "run" / "execution-provenance.json"
            provenance.write_bytes(b'{"schema_version":1,"hermetic":true}\n')
            return {
                "path": str(provenance),
                "sha256": hashlib.sha256(provenance.read_bytes()).hexdigest(),
            }

    return Identity()


@pytest.mark.parametrize(
    ("case", "expected"),
    (
        (
            "collector-and-factory",
            "provide either identity_collector or identity_collector_factory",
        ),
        (
            "missing-receipt-and-policy",
            "formal runner requires a production-seam admission receipt and policy",
        ),
        ("policy-drift", "formal runner options differ from admitted policy"),
    ),
    ids=(
        "collector-and-factory",
        "missing-receipt-and-policy",
        "policy-drift",
    ),
)
def test_admission_contract_rejections_precede_execution_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected: str,
) -> None:
    """Admission/policy failures are side-effect-free before attempt creation."""
    artifact_dir = tmp_path / "run" / "artifacts"
    established, finalized = _record_terminalization(monkeypatch)
    kwargs: dict[str, object] = {}
    if case == "collector-and-factory":
        kwargs.update(
            identity_collector=object(),
            identity_collector_factory=lambda attempt_id: object(),
        )
    elif case == "missing-receipt-and-policy":
        kwargs["admission_required"] = True
    else:
        kwargs.update(
            admission_required=True,
            admission_receipt=object(),
            admission_options=PlannedRunnerOptions(
                device="hermetic-device",
                workdir=tmp_path,
                artifact_dir=artifact_dir,
                launch=False,
            ),
        )

    with pytest.raises(ProductionSeamAdmissionError, match=expected):
        cli.run(
            _spec(tmp_path),
            device="hermetic-device",
            artifact_dir=artifact_dir,
            workdir=tmp_path,
            **kwargs,
        )

    assert established == []
    assert finalized == []
    assert not (artifact_dir.parent / "execution-record.json").exists()


def test_admitted_policy_is_revalidated_before_execution_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The equal-policy path revalidates the receipt before identity capture."""
    artifact_dir = tmp_path / "run" / "artifacts"
    options = PlannedRunnerOptions(
        device="hermetic-device",
        workdir=tmp_path,
        artifact_dir=artifact_dir,
    )
    revalidations: list[tuple[object, object, object]] = []
    established, finalized = _record_terminalization(monkeypatch)

    def verify(receipt: object, spec: object, received_options: object, **kwargs: object) -> None:
        del kwargs
        revalidations.append((receipt, spec, received_options))

    class FailingIdentity:
        def capture_static(self) -> None:
            raise RuntimeError("controlled static identity failure")

    monkeypatch.setattr(cli, "verify_admitted_receipt", verify)
    verdict = cli.run(
        _spec(tmp_path),
        device="hermetic-device",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        admission_required=True,
        admission_receipt={"admitted": True},
        admission_options=options,
        identity_collector=FailingIdentity(),
    )

    _assert_terminal_non_accountable(
        artifact_dir=artifact_dir,
        verdict=verdict,
        expected_reason="execution_identity_error",
        established=established,
        finalized=finalized,
    )
    assert revalidations == [({"admitted": True}, _spec(tmp_path), options)]


def test_identity_factory_receives_the_established_attempt_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory branch cannot run before an ExecutionRecord exists."""
    artifact_dir = tmp_path / "run" / "artifacts"
    established, finalized = _record_terminalization(monkeypatch)
    received_attempt_ids: list[str] = []

    class FailingIdentity:
        def capture_static(self) -> None:
            raise RuntimeError("controlled static identity failure")

    def factory(attempt_id: str) -> FailingIdentity:
        received_attempt_ids.append(attempt_id)
        return FailingIdentity()

    verdict = cli.run(
        _spec(tmp_path),
        device="hermetic-device",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        identity_collector_factory=factory,
    )

    _assert_terminal_non_accountable(
        artifact_dir=artifact_dir,
        verdict=verdict,
        expected_reason="execution_identity_error",
        established=established,
        finalized=finalized,
    )
    assert received_attempt_ids == established


def test_non_accountable_journey_without_runner_setup_omits_that_reference(
    tmp_path: Path,
) -> None:
    """The diagnostic writer does not claim absent runner setup evidence."""
    artifact_dir = tmp_path / "run" / "artifacts"
    flow = _flow(tmp_path)
    started_at = "2026-08-15T00:00:00+00:00"
    record = ExecutionRecordStore.establish(
        artifact_dir.parent,
        artifact_dir=artifact_dir,
        scenario="runner-cli-phase-ordering",
        started_at=started_at,
    )
    gate_path = artifact_dir.parent / "live-validation-gate.json"
    gate_path.write_text('{"status":"passed"}\n', encoding="utf-8")
    error = JourneyExecutionInterrupted(
        reason="journey_action_failed",
        message="controlled journey interruption",
        journey_results=flow.journey_results,
        checkpoints=flow.checkpoints,
        injected_events=[],
        timings=[],
    )

    verdict = cli._write_non_accountable_verdict(
        spec=_spec(tmp_path),
        error=error,
        artifact_dir=artifact_dir,
        started_at=started_at,
        run_start=0.0,
        preflight_summary={
            "status": "passed",
            "artifact": str(gate_path),
            "failed_checks": [],
        },
        preflight_timing={
            "phase": "live-validation-preflight",
            "kind": "preflight",
            "seconds": 0.0,
        },
        execution_record=record,
    )

    persisted = json.loads(record.path.read_text(encoding="utf-8"))
    assert "runner_setup" not in verdict
    assert "runner_setup" not in verdict["diagnostic_artifacts"]
    assert "runner_setup" not in persisted["evidence_refs"]


def test_trigger_steps_records_the_system_event_boundary(tmp_path: Path) -> None:
    """A system event remains visible in the L1/L2 trigger sequence."""
    event_spec = replace(
        _spec(tmp_path),
        scenario=ScenarioSpec(
            id="helpers",
            user_actions=["observe"],
            system_events=[SystemEventSpec(step_index=0, event="rotate")],
        ),
    )
    assert cli._trigger_steps(event_spec) == [
        "observe",
        "[boundary] inject rotate {}",
    ]


def test_l2_helper_rejects_invalid_or_incomplete_boundary_evidence() -> None:
    """L2 stays inconclusive when a selected Journey Segment Boundary is unusable."""
    invalid_boundary = ScenarioSpec(
        id="invalid-boundary",
        system_events=[
            SystemEventSpec(step_index=0, event="rotate"),
            SystemEventSpec(step_index=1, event="dark_mode"),
        ],
        l2_boundary_index=2,
    )
    missing_checkpoints = ScenarioSpec(
        id="missing-checkpoints",
        system_events=[SystemEventSpec(step_index=0, event="rotate")],
    )
    assert cli._judge_l2_from_checkpoints(
        invalid_boundary, {}, steps=[]
    )["evidence"][0]["ref"] == "invalid L2 boundary selection"
    assert cli._judge_l2_from_checkpoints(
        missing_checkpoints, {}, steps=[]
    )["evidence"][0]["ref"] == "missing selected L2 checkpoints"


def test_metric_context_marks_a_failed_baseline_control_as_false_positive(
    tmp_path: Path,
) -> None:
    """Metric classification keeps a baseline-control oracle failure explicit."""
    baseline_control = _spec(
        tmp_path,
        metric_context=MetricContextSpec(seed_kind="baseline_control"),
    )
    metric = cli._build_metric_context(
        baseline_control,
        l1={**_oracle_verdict(), "outcome": "fail"},
        l2={**_oracle_verdict(), "level": "L2"},
        l3=None,
    )
    assert metric["seed_outcome"] == "false_positive"


def test_live_validation_gate_summary_preserves_the_app_surface(tmp_path: Path) -> None:
    """An app-specific preflight receipt remains available to terminal evidence."""
    result = GateResult(
        device="hermetic-device",
        status="passed",
        checks=(),
        app_package="org.example.phaseordering",
        app_activity="MainActivity",
        target_surface={"text": "Home"},
    )
    summary = cli._live_validation_gate_summary(
        result, path=tmp_path / "live-validation-gate.json"
    )
    assert summary["app"] == result.to_dict()["app"]


def test_runner_setup_requires_an_adb_result() -> None:
    """A malformed runner-setup result fails closed before a Journey can start."""
    with pytest.raises(RuntimeError, match="did not return an AdbResult"):
        cli._require_runner_setup_success("logcat_clear", object())  # type: ignore[arg-type]


def _source_backed_spec(tmp_path: Path) -> RunSpec:
    source_path = tmp_path / "run-spec.yaml"
    source_path.write_text("scenario: phase-ordering\n", encoding="utf-8")
    return _spec(tmp_path, source_path=source_path)


def _completed_verdict() -> dict[str, object]:
    return {
        "scenario": "runner-cli-phase-ordering",
        "execution": {"status": "completed"},
        "l1": {"outcome": "pass", "defect_class_hypothesis": None},
        "l2": {"outcome": "pass", "defect_class_hypothesis": None},
        "l3": None,
    }


def test_main_rejected_admission_stops_before_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI admission rejection writes its receipt and never invokes Runner."""
    spec = _source_backed_spec(tmp_path)
    runner_calls: list[object] = []
    receipts: list[Path] = []
    admission = SimpleNamespace(admitted=False, reasons=("controlled rejection",))

    monkeypatch.setattr(cli, "load_run_spec", lambda *args, **kwargs: spec)
    monkeypatch.setattr(cli, "admit_production_seam", lambda *args, **kwargs: admission)
    monkeypatch.setattr(
        cli,
        "write_admission_receipt",
        lambda result, path: (receipts.append(path), path.write_text("receipt\n")),
    )
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: runner_calls.append((args, kwargs)),
    )

    status = cli.main(
        [
            "run-spec.yaml",
            "--device",
            "hermetic-device",
            "--artifact-dir",
            str(tmp_path / "run" / "artifacts"),
        ]
    )

    assert status == 2
    assert len(receipts) == 1 and receipts[0].is_file()
    assert runner_calls == []


def test_main_admitted_receipt_reaches_runner_with_the_exact_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI passes the admitted policy unchanged into the public Runner."""
    spec = _source_backed_spec(tmp_path)
    captured: dict[str, object] = {}
    admission = SimpleNamespace(admitted=True, reasons=())

    monkeypatch.setattr(cli, "load_run_spec", lambda *args, **kwargs: spec)
    monkeypatch.setattr(cli, "admit_production_seam", lambda *args, **kwargs: admission)
    monkeypatch.setattr(
        cli, "write_admission_receipt", lambda result, path: path.write_text("receipt\n")
    )

    def fake_run(loaded_spec: RunSpec, **kwargs: object) -> dict[str, object]:
        captured["spec"] = loaded_spec
        captured.update(kwargs)
        return _completed_verdict()

    monkeypatch.setattr(cli, "run", fake_run)
    status = cli.main(
        [
            "run-spec.yaml",
            "--device",
            "hermetic-device",
            "--artifact-dir",
            str(tmp_path / "run" / "artifacts"),
        ]
    )

    assert status == 0
    assert captured["spec"] is spec
    assert captured["admission_required"] is True
    assert captured["admission_receipt"] is admission
    assert isinstance(captured["admission_options"], PlannedRunnerOptions)


def test_module_entrypoint_routes_help_without_runner_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The module guard executes only argparse help for the public CLI surface."""
    monkeypatch.setattr(sys, "argv", ["aiverify.runner.cli", "--help"])
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r".*found in sys.modules after import.*",
            category=RuntimeWarning,
        )
        with pytest.raises(SystemExit) as exit_status:
            runpy.run_module("aiverify.runner.cli", run_name="__main__")

    assert exit_status.value.code == 0
