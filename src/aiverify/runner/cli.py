"""End-to-end verification runner.

Wires a Run Spec through the full chain with no manual driving:

    run-spec.yaml
      -> JourneySegmentRunner
           -> CodexCliBackend            (Codex CLI drives the app per segment)
           -> AndroidEvidenceCollector   (layout/screenshot/logcat checkpoints)
           -> DeviceSystemEventInjector  (system event at the Journey Segment Boundary)
      -> L1/L2 oracle
      -> verdict.json

Usage:
    python -m aiverify.runner RUN_SPEC.yaml --device emulator-5554 \
        --artifact-dir docs/runs/<slug>/artifacts [--no-launch] [--model MODEL]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aiverify.agent.oracle import L1Oracle
from aiverify.agent.oracle.l3 import L3Oracle
from aiverify.agent.oracle.schema import VerdictValidationError, validate_verdict
from aiverify.bench.live_validation_gate import GateResult, run_live_validation_gate
from aiverify.harness.device import AdbResult
from aiverify.harness.device.controller import DeviceController
from aiverify.providers.codex_cli import CodexCliProvider, CodexCliProviderError
from aiverify.runner.codex_backend import CodexCliBackend, _DEFAULT_SCHEMA_PATH
from aiverify.runner.command import CommandRunner
from aiverify.runner.evidence import AndroidEvidenceCollector
from aiverify.runner.execution_identity import (
    ExecutionIdentityCollector,
)
from aiverify.runner.execution_record import (
    ArtifactStorageError,
    ExecutionRecordStorageError,
    ExecutionRecordStore,
    write_json_artifact,
)
from aiverify.runner.journey import (
    JourneyExecutionInterrupted,
    JourneySegmentFlow,
    JourneySegmentRunner,
)
from aiverify.runner.run_spec import RunSpec, ScenarioSpec, load_run_spec
from aiverify.runner.system_events import DeviceSystemEventInjector
from aiverify.runner.verdict import judge_l2_from_android_layout

_DRIVER_PREAMBLE = """\
You are a Verification Agent Backend driving a real Android emulator (serial: {device}).

TOOLS (run as shell commands):
- `android layout --device={device} --pretty` prints the current UI as a JSON list.
  Each element may have "resource-id", "text", "content-desc", and "center"
  (a string like "[540,2232]" giving the tap x,y).
- `adb -s {device} shell input tap X Y` taps a coordinate.
- `adb -s {device} shell input text "STR"` types into the focused field.

HOW TO ACT: For each <action> in the journey below, run `android layout` to get a
fresh tree, find the named element (usually by its resource-id) to read its "center",
then tap/type as the action says. Re-read the layout between actions. If the app is on
an onboarding screen (no bottom nav yet), advance it by tapping the element with
content-desc "Forward" or text "Skip" until the main feed appears.

CONSTRAINTS: Only use android/adb shell commands against {device}. Do NOT edit files,
install anything, or rotate/toggle the device — the harness injects system events itself.
Navigate ONLY by tapping/typing on visible UI elements (`input tap` / `input text`).
Do NOT use `am start`, `am broadcast`, `monkey`, or any intent-based shortcut to reach
a screen — the app under test may not support that intent and could crash, which would
contaminate the crash oracle. If a screen seems unreachable, keep tapping through the
UI; report FAILED for the action rather than falling back to intents.

ACTION RESULT CONTRACT: Each <action> has a stable id; copy its stable id into action_id
and keep one result per requested action in the same order. PASSED means the requested
UI interaction was dispatched and any required precondition was observed. A crash, ANR,
or incorrect UI after that dispatch is product evidence for the harness oracles, not a
reason to mark the driver action FAILED. Use FAILED only when the requested interaction
could not be dispatched; use SKIPPED only when a prior failure prevented the attempt.
Record the exact commands and observed product behavior in the comment.
Do not infer dispatch from apparent UI side effects and do not claim a command that was
not run.

FINAL OUTPUT: a JSON object matching the provided schema — a "journey" name and a
"results" array with one entry per <action> ("action_id", "status"
PASSED/FAILED/SKIPPED, the "commands" you ran, and a short "comment").

--- JOURNEY SEGMENT TO EXECUTE ---
"""


def build_instruction_prefix(device: str) -> str:
    return _DRIVER_PREAMBLE.format(device=device)


def _build_l3_trace_summary(spec: RunSpec, flow) -> str:
    """L3 judge 的执行轨迹摘要：动作、驱动结果、最终 checkpoint 的 layout 全文。

    只给观测事实，不给 expected_behavior（那会泄露注入缺陷的位置）。
    layout JSON 实测在 10KB 量级，整体嵌入 prompt 在成本边界内。
    """
    final_cp = flow.checkpoints[-1]
    journey_data = json.dumps(
        [r.data for r in flow.journey_results], ensure_ascii=False, indent=2
    )
    layout_text = final_cp.layout_path.read_text(encoding="utf-8")
    return (
        "### 脚本化用户动作（scenario.user_actions）\n"
        + "\n".join(f"{i + 1}. {a}" for i, a in enumerate(spec.scenario.user_actions))
        + "\n\n### 驱动 agent 的分段执行结果（journey results JSON）\n"
        + journey_data
        + f"\n\n### 最终 checkpoint（{final_cp.name}）的 UI layout JSON 全文\n"
        + layout_text
    )


def _judge_l3(spec: RunSpec, flow, *, l1: dict, l2: dict, steps: list[str],
              workdir: Path, artifact_dir: Path, model: str | None) -> dict | None:
    """按分层 oracle 设计门控并执行 L3：仅当 l3_spec 非空且 L1/L2 均未 fail。

    judge 调用失败（格式两次不合规 / codex 出错）降级为 inconclusive 而不是
    让整个 run 丢失 verdict——L3 无法判定本身就是一种合法结果。
    """
    if not spec.scenario.l3_spec:
        return None
    if l1["outcome"] == "fail" or l2["outcome"] == "fail":
        return None

    provider = CodexCliProvider(
        workdir=workdir, artifact_dir=artifact_dir / "l3-judge", model=model
    )
    trace_summary = _build_l3_trace_summary(spec, flow)
    screenshot_refs = [str(cp.screenshot_path) for cp in flow.checkpoints]
    start = time.monotonic()
    try:
        verdict = L3Oracle(provider).judge(
            trace_summary,
            spec.scenario.l3_spec,
            screenshot_refs=screenshot_refs,
            trigger_steps=steps,
        )
    except (VerdictValidationError, CodexCliProviderError, json.JSONDecodeError) as exc:
        verdict = {
            "verdict_id": "L3-error", "level": "L3", "outcome": "inconclusive",
            "defect_class_hypothesis": None, "trigger_steps": steps,
            "evidence": [{"type": "llm_reasoning", "ref": "l3 judge error",
                          "note": f"{type(exc).__name__}: {exc}"[:500]}],
            "confidence": 0.0,
        }
        validate_verdict(verdict)
    finally:
        flow.timings.append({
            "phase": "l3-judge", "kind": "oracle",
            "seconds": round(time.monotonic() - start, 3),
        })
    return verdict


def _trigger_steps(spec: RunSpec) -> list[str]:
    steps = list(spec.scenario.user_actions)
    for ev in spec.scenario.system_events:
        steps.append(f"[boundary] inject {ev.event} {ev.args}")
    return steps


def _l2_inconclusive(*, steps: list[str], ref: str, note: str) -> dict:
    verdict = {
        "verdict_id": "L2-na",
        "level": "L2",
        "outcome": "inconclusive",
        "defect_class_hypothesis": None,
        "trigger_steps": steps,
        "evidence": [{"type": "state_diff", "ref": ref, "note": note}],
        "confidence": 0.0,
    }
    validate_verdict(verdict)
    return verdict


def _judge_l2_from_checkpoints(
    scenario: ScenarioSpec,
    checkpoints: dict,
    *,
    steps: list[str],
) -> dict:
    """Evaluate L2 at the selected Journey Segment Boundary, if unambiguous."""
    event_count = len(scenario.system_events)
    if event_count == 0:
        return _l2_inconclusive(
            steps=steps,
            ref="no boundary system event",
            note="scenario has no system event; L2 state assertion not applicable",
        )

    if event_count == 1:
        boundary_index = 0
    elif scenario.l2_boundary_index is None:
        return _l2_inconclusive(
            steps=steps,
            ref="ambiguous system-event boundaries",
            note=(
                "scenario has multiple system-event boundaries; set "
                "scenario.l2_boundary_index to select L2 state evidence"
            ),
        )
    else:
        boundary_index = scenario.l2_boundary_index

    if boundary_index >= event_count:
        return _l2_inconclusive(
            steps=steps,
            ref="invalid L2 boundary selection",
            note=(
                f"scenario.l2_boundary_index={boundary_index} does not select one of "
                f"{event_count} system-event boundaries"
            ),
        )

    before_name = f"after-segment-{boundary_index}"
    after_name = f"after-event-{boundary_index}"
    before_cp = checkpoints.get(before_name)
    after_cp = checkpoints.get(after_name)
    if before_cp is None or after_cp is None:
        return _l2_inconclusive(
            steps=steps,
            ref="missing selected L2 checkpoints",
            note=(
                f"selected boundary {boundary_index} requires {before_name} and "
                f"{after_name} checkpoints"
            ),
        )

    return judge_l2_from_android_layout(
        before_cp.layout_path.read_text(encoding="utf-8"),
        after_cp.layout_path.read_text(encoding="utf-8"),
        scenario.assertions,
        trigger_steps=steps,
    )


def _build_metric_context(spec: RunSpec, *, l1: dict, l2: dict, l3: dict | None) -> dict:
    """Build top-level benchmark metric context without changing oracle verdicts."""
    oracle_verdicts = {"L1": l1, "L2": l2, "L3": l3}
    oracle_outcomes = {
        level: verdict["outcome"] if verdict is not None else "not_run"
        for level, verdict in oracle_verdicts.items()
    }
    oracle_defect_classes = {
        level: verdict["defect_class_hypothesis"] if verdict is not None else None
        for level, verdict in oracle_verdicts.items()
    }
    failed_oracles = [
        level for level, outcome in oracle_outcomes.items() if outcome == "fail"
    ]
    detected = bool(failed_oracles)
    metric_spec = spec.scenario.metric_context
    seed_kind = metric_spec.seed_kind

    if seed_kind == "injected_defect":
        seed_outcome = "caught" if detected else "missed"
    elif seed_kind == "baseline_control":
        seed_outcome = "false_positive" if detected else "passed_control"
    else:
        seed_outcome = "detected" if detected else "not_detected"

    return {
        "seed_id": spec.scenario.id,
        "seed_kind": seed_kind,
        "seed_outcome": seed_outcome,
        "taxonomy_category": metric_spec.taxonomy_category,
        "taxonomy_pattern_id": metric_spec.taxonomy_pattern_id,
        "expected_oracle_level": metric_spec.expected_oracle_level,
        "expected_oracle_defect_class": metric_spec.expected_oracle_defect_class,
        "oracle_outcomes": oracle_outcomes,
        "oracle_defect_classes": oracle_defect_classes,
        "failed_oracles": failed_oracles,
    }


def _non_accountable_metric_context(spec: RunSpec) -> dict:
    """Describe a seed that has no eligible oracle outcome."""
    metric = spec.scenario.metric_context
    return {
        "seed_id": spec.scenario.id,
        "seed_kind": metric.seed_kind,
        "seed_outcome": "not_accountable",
        "taxonomy_category": metric.taxonomy_category,
        "taxonomy_pattern_id": metric.taxonomy_pattern_id,
        "expected_oracle_level": metric.expected_oracle_level,
        "expected_oracle_defect_class": metric.expected_oracle_defect_class,
        "oracle_outcomes": {"L1": "not_run", "L2": "not_run", "L3": "not_run"},
        "oracle_defect_classes": {"L1": None, "L2": None, "L3": None},
        "failed_oracles": [],
    }


def _write_live_validation_gate(result: GateResult, *, artifact_dir: Path) -> Path:
    """Persist runner preflight evidence next to the run verdict."""
    evidence_dir = artifact_dir.parent
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / "live-validation-gate.json"
    write_json_artifact(path, result.to_dict())
    return path


def _live_validation_gate_summary(result: GateResult, *, path: Path) -> dict:
    summary = {
        "status": result.status,
        "artifact": str(path),
        "failed_checks": list(result.failed_checks),
    }
    payload = result.to_dict()
    if "app" in payload:
        summary["app"] = payload["app"]
    return summary


def _run_live_validation_preflight(
    spec: RunSpec,
    *,
    device: str,
    artifact_dir: Path,
    runner: CommandRunner | None,
) -> tuple[GateResult, Path, dict, dict]:
    """Run and persist the mandatory live-validation gate before app driving."""
    preflight_start = time.monotonic()
    live_validation = spec.live_validation
    app_smoke = live_validation.app_smoke
    app_package = None
    app_activity = None
    target_resource_id = None
    target_text = None
    target_content_desc = None
    app_settle_seconds = 3.0
    if app_smoke is not None:
        app_package = app_smoke.package or spec.package
        app_activity = app_smoke.activity or spec.activity
        target_resource_id = app_smoke.target_resource_id
        target_text = app_smoke.target_text
        target_content_desc = app_smoke.target_content_desc
        app_settle_seconds = app_smoke.app_settle_seconds

    result = run_live_validation_gate(
        device=device,
        runner=runner,
        android_bin=live_validation.android_bin,
        adb_bin=live_validation.adb_bin,
        timeout_seconds=live_validation.timeout_seconds,
        snippet_chars=live_validation.snippet_chars,
        app_package=app_package,
        app_activity=app_activity,
        target_resource_id=target_resource_id,
        target_text=target_text,
        target_content_desc=target_content_desc,
        app_settle_seconds=app_settle_seconds,
    )
    path = _write_live_validation_gate(result, artifact_dir=artifact_dir)
    timing = {
        "phase": "live-validation-preflight",
        "kind": "preflight",
        "seconds": round(time.monotonic() - preflight_start, 3),
    }
    return result, path, _live_validation_gate_summary(result, path=path), timing


def _require_runner_setup_success(operation: str, result: AdbResult) -> None:
    """Reject a setup command whose ADB process reported a non-zero exit."""
    if not isinstance(result, AdbResult):
        raise RuntimeError(f"{operation} command did not return an AdbResult")
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        raise RuntimeError(
            f"{operation} command returned return code {result.returncode}: {detail}"
        )


def _portable_evidence_ref(path: str | Path, *, run_dir: Path) -> str:
    """Return a run-relative reference when an artifact belongs to this attempt."""
    source = Path(path)
    try:
        return source.resolve().relative_to(run_dir.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def _flow_evidence_refs(
    flow: JourneySegmentFlow, *, run_dir: Path
) -> dict[str, object]:
    refs: dict[str, object] = {
        "journey_results": [
            _portable_evidence_ref(result.result_path, run_dir=run_dir)
            for result in flow.journey_results
        ],
        "checkpoints": [
            _portable_evidence_ref(checkpoint.directory, run_dir=run_dir)
            for checkpoint in flow.checkpoints
        ],
    }
    if flow.system_event_evidence:
        refs["system_events"] = [
            _portable_evidence_ref(path, run_dir=run_dir)
            for path in flow.system_event_evidence
        ]
    return refs


def _write_preflight_non_accountable_verdict(
    *,
    spec: RunSpec,
    gate_result: GateResult,
    gate_path: Path,
    preflight_summary: dict | None,
    preflight_timing: dict | None,
    artifact_dir: Path,
    started_at: str,
    run_start: float,
    execution_record: ExecutionRecordStore,
) -> dict:
    failed_checks = ", ".join(gate_result.failed_checks)
    message = (
        f"live-validation preflight failed: {failed_checks}"
        if failed_checks
        else "live-validation preflight failed"
    )
    verdict = {
        "scenario": spec.scenario.id,
        "execution": {
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": "live_validation_preflight_failed",
            "message": message,
        },
        "preflight": {"live_validation_gate": preflight_summary},
        "metric_context": _non_accountable_metric_context(spec),
        "l1": None,
        "l2": None,
        "l3": None,
        "diagnostic_artifacts": {"live_validation_gate": str(gate_path)},
        "journey_results": [],
        "checkpoints": [],
        "injected_events": [],
        "timing": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_seconds": round(time.monotonic() - run_start, 3),
            "phases": [preflight_timing],
        },
        "execution_record": str(execution_record.path),
    }
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    phase_errors = [
        {
            "phase": "live-validation-preflight",
            "kind": "preflight",
            "reason": "live_validation_preflight_failed",
            "message": message,
        }
    ]
    try:
        write_json_artifact(artifact_dir.parent / "verdict.json", verdict)
    except Exception as error:
        return _finalize_output_failure(
            spec=spec,
            error=error,
            started_at=started_at,
            run_start=run_start,
            execution_record=execution_record,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            prior_phase_errors=phase_errors,
        )
    execution_record.finalize(
        lifecycle_state="preflight_rejected",
        execution=verdict["execution"],
        process_exit_code=2,
        timing=verdict["timing"],
        phase_errors=phase_errors,
        evidence_refs={
            "live_validation_gate": _portable_evidence_ref(
                gate_path, run_dir=artifact_dir.parent
            ),
            "verdict": _portable_evidence_ref(
                artifact_dir.parent / "verdict.json",
                run_dir=artifact_dir.parent,
            ),
        },
    )
    return verdict


def _write_preflight_exception_verdict(
    *,
    spec: RunSpec,
    error: Exception,
    artifact_dir: Path,
    started_at: str,
    run_start: float,
    preflight_start: float,
    execution_record: ExecutionRecordStore,
) -> dict:
    message = f"{type(error).__name__}: {error}"
    timing = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_seconds": round(time.monotonic() - run_start, 3),
        "phases": [
            {
                "phase": "live-validation-preflight",
                "kind": "preflight",
                "status": "failed",
                "seconds": round(time.monotonic() - preflight_start, 3),
            }
        ],
    }
    execution = {
        "status": "non_accountable",
        "accounting_eligible": False,
        "reason": "live_validation_preflight_failed",
        "message": message,
    }
    verdict = {
        "scenario": spec.scenario.id,
        "execution": execution,
        "preflight": {"live_validation_gate": None},
        "metric_context": _non_accountable_metric_context(spec),
        "l1": None,
        "l2": None,
        "l3": None,
        "diagnostic_artifacts": {},
        "journey_results": [],
        "checkpoints": [],
        "injected_events": [],
        "timing": timing,
        "execution_record": str(execution_record.path),
    }
    verdict_path = artifact_dir.parent / "verdict.json"
    phase_errors = [
        {
            "phase": "live-validation-preflight",
            "kind": "preflight",
            "reason": "live_validation_preflight_failed",
            "message": message,
        }
    ]
    try:
        write_json_artifact(verdict_path, verdict)
    except Exception as output_error:
        return _finalize_output_failure(
            spec=spec,
            error=output_error,
            started_at=started_at,
            run_start=run_start,
            execution_record=execution_record,
            preflight_timing=timing["phases"][0],
            prior_phase_errors=phase_errors,
        )
    execution_record.finalize(
        lifecycle_state="failed",
        execution=execution,
        process_exit_code=2,
        timing=timing,
        phase_errors=phase_errors,
        evidence_refs={
            "verdict": _portable_evidence_ref(
                verdict_path, run_dir=artifact_dir.parent
            )
        },
    )
    return verdict


def _write_failed_run_verdict(
    *,
    spec: RunSpec,
    reason: str,
    phase: str,
    kind: str,
    error: Exception,
    artifact_dir: Path,
    started_at: str,
    run_start: float,
    phase_start: float,
    preflight_summary: dict,
    preflight_timing: dict,
    execution_record: ExecutionRecordStore,
    flow: JourneySegmentFlow | None = None,
    lifecycle_state: str = "failed",
) -> dict:
    message = f"{type(error).__name__}: {error}"
    failed_timing = {
        "phase": phase,
        "kind": kind,
        "status": "failed",
        "seconds": round(time.monotonic() - phase_start, 3),
    }
    timing = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_seconds": round(time.monotonic() - run_start, 3),
        "phases": [
            *([preflight_timing] if preflight_timing is not None else []),
            *(flow.timings if flow is not None else []),
            failed_timing,
        ],
    }
    execution = {
        "status": "non_accountable",
        "accounting_eligible": False,
        "reason": reason,
        "message": message,
    }
    verdict = {
        "scenario": spec.scenario.id,
        "execution": execution,
        "preflight": {"live_validation_gate": preflight_summary},
        "metric_context": _non_accountable_metric_context(spec),
        "l1": None,
        "l2": None,
        "l3": None,
        "diagnostic_artifacts": {
            **(
                {"live_validation_gate": preflight_summary["artifact"]}
                if preflight_summary is not None
                else {}
            ),
            "journey_results": (
                [str(result.result_path) for result in flow.journey_results]
                if flow is not None
                else []
            ),
            "checkpoints": (
                [str(checkpoint.directory) for checkpoint in flow.checkpoints]
                if flow is not None
                else []
            ),
        },
        "journey_results": (
            [result.data for result in flow.journey_results]
            if flow is not None
            else []
        ),
        "checkpoints": (
            [checkpoint.name for checkpoint in flow.checkpoints]
            if flow is not None
            else []
        ),
        "injected_events": (
            [
                {"event": event.event, "args": event.args}
                for event in flow.injected_events
            ]
            if flow is not None
            else []
        ),
        "timing": timing,
        "execution_record": str(execution_record.path),
    }
    verdict_path = artifact_dir.parent / "verdict.json"
    phase_errors = [
        {
            "phase": phase,
            "kind": kind,
            "reason": reason,
            "message": message,
        }
    ]
    run_dir = artifact_dir.parent
    evidence_refs: dict[str, object] = {
        "verdict": _portable_evidence_ref(verdict_path, run_dir=run_dir)
    }
    if preflight_summary is not None:
        evidence_refs["live_validation_gate"] = _portable_evidence_ref(
            preflight_summary["artifact"], run_dir=run_dir
        )
    if flow is not None:
        system_event_refs = [
            _portable_evidence_ref(path, run_dir=run_dir)
            for path in flow.system_event_evidence
        ]
        verdict["system_event_evidence"] = system_event_refs
        verdict["diagnostic_artifacts"]["system_events"] = system_event_refs
        evidence_refs.update(_flow_evidence_refs(flow, run_dir=run_dir))
    try:
        write_json_artifact(verdict_path, verdict)
    except Exception as output_error:
        return _finalize_output_failure(
            spec=spec,
            error=output_error,
            started_at=started_at,
            run_start=run_start,
            execution_record=execution_record,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            flow=flow,
            additional_timings=[failed_timing],
            prior_phase_errors=phase_errors,
        )
    execution_record.finalize(
        lifecycle_state=lifecycle_state,
        execution=execution,
        process_exit_code=2,
        timing=timing,
        phase_errors=phase_errors,
        evidence_refs=evidence_refs,
    )
    return verdict


def _finalize_output_failure(
    *,
    spec: RunSpec,
    error: Exception,
    started_at: str,
    run_start: float,
    execution_record: ExecutionRecordStore,
    output_phase: str = "verdict-output",
    preflight_summary: dict | None = None,
    preflight_timing: dict | None = None,
    flow: JourneySegmentFlow | None = None,
    additional_timings: list[dict] | None = None,
    prior_phase_errors: list[dict] | None = None,
) -> dict:
    message = f"{type(error).__name__}: {error}"
    output_timing = {
        "phase": output_phase,
        "kind": "output",
        "status": "failed",
        "seconds": 0.0,
    }
    phase_timings: list[dict] = []
    if preflight_timing is not None:
        phase_timings.append(preflight_timing)
    if flow is not None:
        phase_timings.extend(flow.timings)
    phase_timings.extend(additional_timings or [])
    phase_timings.append(output_timing)
    timing = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_seconds": round(time.monotonic() - run_start, 3),
        "phases": phase_timings,
    }
    execution = {
        "status": "non_accountable",
        "accounting_eligible": False,
        "reason": "output_finalization_error",
        "message": message,
    }
    verdict = {
        "scenario": spec.scenario.id,
        "execution": execution,
        "preflight": {"live_validation_gate": preflight_summary},
        "metric_context": _non_accountable_metric_context(spec),
        "l1": None,
        "l2": None,
        "l3": None,
        "diagnostic_artifacts": {},
        "journey_results": (
            [result.data for result in flow.journey_results]
            if flow is not None
            else []
        ),
        "checkpoints": (
            [checkpoint.name for checkpoint in flow.checkpoints]
            if flow is not None
            else []
        ),
        "injected_events": [
            {"event": event.event, "args": event.args}
            for event in (flow.injected_events if flow is not None else [])
        ],
        "timing": timing,
        "execution_record": str(execution_record.path),
    }
    run_dir = execution_record.path.parent
    evidence_refs: dict[str, object] = {}
    if preflight_summary is not None:
        gate_path = preflight_summary["artifact"]
        verdict["diagnostic_artifacts"]["live_validation_gate"] = gate_path
        evidence_refs["live_validation_gate"] = _portable_evidence_ref(
            gate_path, run_dir=run_dir
        )
    if flow is not None:
        journey_refs = [
            str(result.result_path) for result in flow.journey_results
        ]
        checkpoint_refs = [
            str(checkpoint.directory) for checkpoint in flow.checkpoints
        ]
        verdict["diagnostic_artifacts"].update(
            {"journey_results": journey_refs, "checkpoints": checkpoint_refs}
        )
        system_event_refs = [
            _portable_evidence_ref(path, run_dir=run_dir)
            for path in flow.system_event_evidence
        ]
        verdict["system_event_evidence"] = system_event_refs
        verdict["diagnostic_artifacts"]["system_events"] = system_event_refs
        evidence_refs.update(_flow_evidence_refs(flow, run_dir=run_dir))
    output_error = {
        "phase": output_phase,
        "kind": "output",
        "reason": "output_finalization_error",
        "message": message,
    }
    execution_record.finalize(
        lifecycle_state="failed",
        execution=execution,
        process_exit_code=2,
        timing=timing,
        phase_errors=[*(prior_phase_errors or []), output_error],
        evidence_refs=evidence_refs,
    )
    return verdict


def _write_non_accountable_verdict(
    *,
    spec: RunSpec,
    error: JourneyExecutionInterrupted,
    artifact_dir: Path,
    started_at: str,
    run_start: float,
    preflight_summary: dict,
    preflight_timing: dict,
    execution_record: ExecutionRecordStore,
) -> dict:
    """Persist a diagnostic run result that cannot enter benchmark accounting."""
    flow = error.flow
    run_dir = artifact_dir.parent
    system_event_refs = [
        _portable_evidence_ref(path, run_dir=run_dir)
        for path in flow.system_event_evidence
    ]
    diagnostic_artifacts = {
        "journey_results": [
            {
                "result": str(result.result_path),
                "events": str(result.events_path),
                **(
                    {"raw_result": result.metadata["raw_result_path"]}
                    if "raw_result_path" in result.metadata
                    else {}
                ),
                **(
                    {"action_lineage": result.metadata["action_lineage_path"]}
                    if "action_lineage_path" in result.metadata
                    else {}
                ),
            }
            for result in flow.journey_results
        ],
        "checkpoints": [
            {
                "name": checkpoint.name,
                "directory": str(checkpoint.directory),
                "layout": str(checkpoint.layout_path),
                "screenshot": str(checkpoint.screenshot_path),
                "annotated_screenshot": (
                    str(checkpoint.annotated_screenshot_path)
                    if checkpoint.annotated_screenshot_path is not None
                    else None
                ),
                "logcat": str(checkpoint.logcat_path),
                "commands": str(checkpoint.commands_path),
                "manifest": (
                    str(checkpoint.manifest_path)
                    if checkpoint.manifest_path is not None
                    else None
                ),
            }
            for checkpoint in flow.checkpoints
        ],
        "backend_errors": error.backend_diagnostics,
        "system_events": system_event_refs,
    }
    verdict = {
        "scenario": spec.scenario.id,
        "execution": {
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": error.reason,
            "message": str(error),
        },
        "preflight": {"live_validation_gate": preflight_summary},
        "metric_context": _non_accountable_metric_context(spec),
        "l1": None,
        "l2": None,
        "l3": None,
        "diagnostic_artifacts": diagnostic_artifacts,
        "journey_results": [result.data for result in flow.journey_results],
        "checkpoints": [checkpoint.name for checkpoint in flow.checkpoints],
        "injected_events": [
            {"event": event.event, "args": event.args} for event in flow.injected_events
        ],
        "system_event_evidence": system_event_refs,
        "timing": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_seconds": round(time.monotonic() - run_start, 3),
            "phases": [preflight_timing, *flow.timings],
        },
        "execution_record": str(execution_record.path),
    }
    failed_timings = [
        timing for timing in flow.timings if timing.get("status") == "failed"
    ]
    if failed_timings:
        phase_errors = [
            {
                "phase": timing["phase"],
                "kind": timing["kind"],
                "reason": error.reason,
                "message": str(error),
            }
            for timing in failed_timings
        ]
    else:
        kind = (
            "checkpoint"
            if error.reason == "checkpoint_capture_error"
            else "system_event"
            if error.reason == "system_event_error"
            else "journey"
        )
        phase_errors = [
            {
                "phase": kind,
                "kind": kind,
                "reason": error.reason,
                "message": str(error),
            }
        ]
    artifact_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        write_json_artifact(artifact_dir.parent / "verdict.json", verdict)
    except Exception as output_error:
        return _finalize_output_failure(
            spec=spec,
            error=output_error,
            started_at=started_at,
            run_start=run_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            flow=flow,
            execution_record=execution_record,
            prior_phase_errors=phase_errors,
        )
    execution_record.finalize(
        lifecycle_state="interrupted",
        execution=verdict["execution"],
        process_exit_code=2,
        timing=verdict["timing"],
        phase_errors=phase_errors,
        evidence_refs={
            "live_validation_gate": _portable_evidence_ref(
                preflight_summary["artifact"], run_dir=run_dir
            ),
            "verdict": _portable_evidence_ref(
                artifact_dir.parent / "verdict.json", run_dir=run_dir
            ),
            **_flow_evidence_refs(flow, run_dir=run_dir),
        },
    )
    return verdict


def run(spec: RunSpec, *, device: str, artifact_dir: Path, workdir: Path,
        launch: bool = True, model: str | None = None,
        l3_model: str | None = None,
        instruction_prefix: str | None = None,
        preflight_command_runner: CommandRunner | None = None,
        run_spec_path: Path | None = None,
        identity_command_runner: CommandRunner | None = None,
        identity_collector: ExecutionIdentityCollector | None = None,
        allow_host_project_subdir: bool = False) -> dict:
    artifact_dir = Path(artifact_dir).resolve()
    workdir = Path(workdir).resolve()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_start = time.monotonic()
    execution_record = ExecutionRecordStore.establish(
        artifact_dir.parent,
        artifact_dir=artifact_dir,
        scenario=spec.scenario.id,
        started_at=started_at,
    )
    identity_start = time.monotonic()
    if identity_collector is None:
        identity_collector = ExecutionIdentityCollector(
            run_dir=artifact_dir.parent,
            artifact_dir=artifact_dir,
            attempt_id=execution_record.attempt_id,
            spec=spec,
            run_spec_path=(
                Path(run_spec_path)
                if run_spec_path is not None
                else spec.source_path or Path("<programmatic-run-spec>")
            ),
            workdir=workdir,
            device=device,
            requested_driver_model=model,
            requested_l3_model=l3_model,
            command_runner=identity_command_runner,
            android_bin=spec.live_validation.android_bin,
            adb_bin=spec.live_validation.adb_bin,
            allow_host_project_subdir=allow_host_project_subdir,
        )
    try:
        identity_collector.capture_static()
    except Exception as error:
        return _write_failed_run_verdict(
            spec=spec,
            reason="execution_identity_error",
            phase="execution-identity-capture",
            kind="identity",
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            phase_start=identity_start,
            preflight_summary=None,
            preflight_timing=None,
            execution_record=execution_record,
        )
    preflight_start = time.monotonic()
    try:
        (
            preflight_result,
            preflight_path,
            preflight_summary,
            preflight_timing,
        ) = _run_live_validation_preflight(
            spec,
            device=device,
            artifact_dir=artifact_dir,
            runner=preflight_command_runner,
        )
    except ArtifactStorageError as error:
        return _finalize_output_failure(
            spec=spec,
            error=error,
            started_at=started_at,
            run_start=run_start,
            execution_record=execution_record,
            output_phase="live-validation-gate-output",
        )
    except Exception as error:
        return _write_preflight_exception_verdict(
            spec=spec,
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            preflight_start=preflight_start,
            execution_record=execution_record,
        )
    if preflight_result.status != "passed":
        return _write_preflight_non_accountable_verdict(
            spec=spec,
            gate_result=preflight_result,
            gate_path=preflight_path,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            execution_record=execution_record,
        )

    deployment_start = time.monotonic()
    try:
        identity_collector.deploy()
        identity_collector.verify_ready_for_agent()
    except Exception as error:
        return _write_failed_run_verdict(
            spec=spec,
            reason="execution_identity_error",
            phase="deployment-identity",
            kind="identity",
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            phase_start=deployment_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            execution_record=execution_record,
        )

    setup_start = time.monotonic()
    try:
        controller = DeviceController(serial=device)
        # clear logcat so L1 only sees this run's events, not stale crashes from prior runs
        _require_runner_setup_success("logcat_clear", controller.logcat_clear())
        if launch:
            _require_runner_setup_success(
                "launch", controller.launch(spec.package, spec.activity)
            )

        runner = JourneySegmentRunner(
            backend=CodexCliBackend(),
            checkpoint_collector=AndroidEvidenceCollector(),
            system_event_injector=DeviceSystemEventInjector(
                device=controller, package=spec.package, activity=spec.activity
            ),
        )
    except Exception as error:
        return _write_failed_run_verdict(
            spec=spec,
            reason="runner_setup_error",
            phase="runner-setup",
            kind="runner",
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            phase_start=setup_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            execution_record=execution_record,
        )
    journey_start = time.monotonic()
    try:
        flow = runner.run(
            scenario=spec.scenario,
            workdir=workdir,
            artifact_dir=artifact_dir,
            output_schema=_DEFAULT_SCHEMA_PATH,
            device=device,
            instruction_prefix=(
                build_instruction_prefix(device)
                if instruction_prefix is None
                else instruction_prefix
            ),
            model=model,
        )
    except JourneyExecutionInterrupted as error:
        return _write_non_accountable_verdict(
            spec=spec,
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            execution_record=execution_record,
        )
    except Exception as error:
        return _write_failed_run_verdict(
            spec=spec,
            reason="journey_execution_error",
            phase="journey-execution",
            kind="journey",
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            phase_start=journey_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            execution_record=execution_record,
            lifecycle_state="interrupted",
        )

    oracle_start = time.monotonic()
    try:
        checkpoints = {c.name: c for c in flow.checkpoints}
        steps = _trigger_steps(spec)

        # L1 scans every checkpoint's logcat, so a crash/ANR during any segment or after any
        # event is caught — not only the post-event checkpoint (e.g. an ANR while typing).
        all_logcat = "\n".join(
            cp.logcat_path.read_text(encoding="utf-8") for cp in flow.checkpoints
        )
        l1 = L1Oracle().judge(all_logcat, trigger_steps=steps)

        l2 = _judge_l2_from_checkpoints(spec.scenario, checkpoints, steps=steps)

        l3 = _judge_l3(
            spec,
            flow,
            l1=l1,
            l2=l2,
            steps=steps,
            workdir=workdir,
            artifact_dir=artifact_dir,
            model=l3_model,
        )
    except Exception as error:
        return _write_failed_run_verdict(
            spec=spec,
            reason="oracle_execution_error",
            phase="oracle-evaluation",
            kind="oracle",
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            phase_start=oracle_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            execution_record=execution_record,
            flow=flow,
        )

    identity_finalize_start = time.monotonic()
    try:
        execution_provenance = identity_collector.finalize(
            l1=l1,
            l2=l2,
            l3=l3,
            l3_configured=bool(spec.scenario.l3_spec),
        )
    except Exception as error:
        return _write_failed_run_verdict(
            spec=spec,
            reason="execution_identity_error",
            phase="execution-identity-finalize",
            kind="identity",
            error=error,
            artifact_dir=artifact_dir,
            started_at=started_at,
            run_start=run_start,
            phase_start=identity_finalize_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            execution_record=execution_record,
            flow=flow,
        )

    verdict = {
        "scenario": spec.scenario.id,
        "execution": {
            "status": "completed",
            "accounting_eligible": True,
            "reason": None,
            "message": None,
        },
        "preflight": {"live_validation_gate": preflight_summary},
        "metric_context": _build_metric_context(spec, l1=l1, l2=l2, l3=l3),
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "journey_results": [r.data for r in flow.journey_results],
        "checkpoints": [c.name for c in flow.checkpoints],
        "injected_events": [{"event": e.event, "args": e.args} for e in flow.injected_events],
        "system_event_evidence": [
            _portable_evidence_ref(path, run_dir=artifact_dir.parent)
            for path in flow.system_event_evidence
        ],
        "timing": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_seconds": round(time.monotonic() - run_start, 3),
            "phases": [preflight_timing, *flow.timings],
        },
        "execution_record": str(execution_record.path),
        "execution_provenance": execution_provenance,
    }
    try:
        write_json_artifact(artifact_dir.parent / "verdict.json", verdict)
    except Exception as error:
        return _finalize_output_failure(
            spec=spec,
            error=error,
            started_at=started_at,
            run_start=run_start,
            preflight_summary=preflight_summary,
            preflight_timing=preflight_timing,
            flow=flow,
            execution_record=execution_record,
        )
    process_exit_code = 1 if any(
        value is not None and value["outcome"] == "fail"
        for value in (l1, l2, l3)
    ) else 0
    execution_record.finalize(
        lifecycle_state="completed",
        execution=verdict["execution"],
        process_exit_code=process_exit_code,
        timing=verdict["timing"],
        phase_errors=[],
        evidence_refs={
            "live_validation_gate": _portable_evidence_ref(
                preflight_path, run_dir=artifact_dir.parent
            ),
            "verdict": _portable_evidence_ref(
                artifact_dir.parent / "verdict.json",
                run_dir=artifact_dir.parent,
            ),
            **_flow_evidence_refs(flow, run_dir=artifact_dir.parent),
            "execution_provenance": execution_provenance,
        },
    )
    return verdict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aiverify.runner", description=__doc__)
    ap.add_argument("run_spec", help="Path to a run-spec.yaml")
    ap.add_argument("--device", required=True, help="adb device serial, e.g. emulator-5554")
    ap.add_argument("--artifact-dir", required=True, type=Path, help="Directory for evidence checkpoints")
    ap.add_argument(
        "--host-project",
        type=Path,
        help="Resolve a structured portable host locator to this repository root",
    )
    ap.add_argument(
        "--workdir",
        type=Path,
        default=None,
        help="Codex --cd working directory (defaults to the resolved host project)",
    )
    ap.add_argument("--no-launch", action="store_true", help="Do not launch the app first")
    ap.add_argument("--model", default=None, help="Override Codex model")
    ap.add_argument("--l3-model", default=None, help="Override Codex model for the L3 judge")
    args = ap.parse_args(argv)

    load_kwargs = (
        {"host_project_override": args.host_project}
        if args.host_project is not None
        else {}
    )
    spec = load_run_spec(args.run_spec, **load_kwargs)
    workdir = args.workdir if args.workdir is not None else spec.host_project
    try:
        verdict = run(
            spec,
            device=args.device,
            artifact_dir=args.artifact_dir,
            workdir=workdir,
            launch=not args.no_launch,
            model=args.model,
            l3_model=args.l3_model,
            run_spec_path=Path(args.run_spec),
        )
    except ExecutionRecordStorageError as error:
        print(f"ExecutionRecord storage failed: {error}", file=sys.stderr)
        return 2
    if verdict["execution"]["status"] != "completed":
        execution = verdict["execution"]
        print(
            f"scenario: {verdict['scenario']}\n"
            f"execution: {execution['status']} ({execution['reason']})"
        )
        return 2
    l1_class = verdict["l1"]["defect_class_hypothesis"]
    l2_class = verdict["l2"]["defect_class_hypothesis"]
    print(f"scenario: {verdict['scenario']}")
    l3 = verdict["l3"]
    l3_desc = f"{l3['outcome']} ({l3['defect_class_hypothesis']})" if l3 else "not run"
    print(
        f"L1: {verdict['l1']['outcome']} ({l1_class})  |  L2: {verdict['l2']['outcome']} ({l2_class})"
        f"  |  L3: {l3_desc}"
    )
    # non-zero exit when a defect is detected by any oracle, so CI can gate on it
    detected = any(
        v is not None and v["outcome"] == "fail"
        for v in (verdict["l1"], verdict["l2"], verdict["l3"])
    )
    return 1 if detected else 0


if __name__ == "__main__":
    sys.exit(main())
