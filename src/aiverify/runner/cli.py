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
from aiverify.providers.codex_cli import CodexCliProvider, CodexCliProviderError
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.codex_backend import CodexCliBackend, _DEFAULT_SCHEMA_PATH
from aiverify.runner.evidence import AndroidEvidenceCollector
from aiverify.runner.journey import JourneySegmentRunner
from aiverify.runner.run_spec import RunSpec, load_run_spec
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

FINAL OUTPUT: a JSON object matching the provided schema — a "journey" name and a
"results" array with one entry per <action> ("action", "status" PASSED/FAILED/SKIPPED,
the "commands" you ran, and a short "comment").

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


def run(spec: RunSpec, *, device: str, artifact_dir: Path, workdir: Path,
        launch: bool = True, model: str | None = None,
        l3_model: str | None = None) -> dict:
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_start = time.monotonic()
    controller = DeviceController(serial=device)
    # clear logcat so L1 only sees this run's events, not stale crashes from prior runs
    controller.logcat_clear()
    if launch:
        controller.launch(spec.package, spec.activity)

    runner = JourneySegmentRunner(
        backend=CodexCliBackend(),
        checkpoint_collector=AndroidEvidenceCollector(),
        system_event_injector=DeviceSystemEventInjector(
            device=controller, package=spec.package, activity=spec.activity
        ),
    )
    flow = runner.run(
        scenario=spec.scenario,
        workdir=workdir,
        artifact_dir=artifact_dir,
        output_schema=_DEFAULT_SCHEMA_PATH,
        device=device,
        instruction_prefix=build_instruction_prefix(device),
    )

    checkpoints = {c.name: c for c in flow.checkpoints}
    steps = _trigger_steps(spec)

    # L1 scans every checkpoint's logcat, so a crash/ANR during any segment or after any
    # event is caught — not only the post-event checkpoint (e.g. an ANR while typing).
    all_logcat = "\n".join(cp.logcat_path.read_text(encoding="utf-8") for cp in flow.checkpoints)
    l1 = L1Oracle().judge(all_logcat, trigger_steps=steps)

    # L2 needs a before/after pair around a boundary event; scenarios without a system
    # event (e.g. a crash/ANR triggered by a user action) are not L2-assertable.
    event_names = sorted(n for n in checkpoints if n.startswith("after-event-"))
    if event_names:
        idx = event_names[0].rsplit("-", 1)[1]
        before_cp = checkpoints[f"after-segment-{idx}"]
        after_cp = checkpoints[f"after-event-{idx}"]
        l2 = judge_l2_from_android_layout(
            before_cp.layout_path.read_text(encoding="utf-8"),
            after_cp.layout_path.read_text(encoding="utf-8"),
            spec.scenario.assertions,
            trigger_steps=steps,
        )
    else:
        l2 = {
            "verdict_id": "L2-na", "level": "L2", "outcome": "inconclusive",
            "defect_class_hypothesis": None, "trigger_steps": steps,
            "evidence": [{"type": "state_diff", "ref": "no boundary system event",
                          "note": "scenario has no system event; L2 state assertion not applicable"}],
            "confidence": 0.0,
        }
        validate_verdict(l2)

    l3 = _judge_l3(
        spec, flow, l1=l1, l2=l2, steps=steps,
        workdir=workdir, artifact_dir=artifact_dir, model=l3_model,
    )

    verdict = {
        "scenario": spec.scenario.id,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "journey_results": [r.data for r in flow.journey_results],
        "checkpoints": [c.name for c in flow.checkpoints],
        "injected_events": [{"event": e.event, "args": e.args} for e in flow.injected_events],
        "timing": {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "total_seconds": round(time.monotonic() - run_start, 3),
            "phases": flow.timings,
        },
    }
    (artifact_dir.parent / "verdict.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return verdict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aiverify.runner", description=__doc__)
    ap.add_argument("run_spec", help="Path to a run-spec.yaml")
    ap.add_argument("--device", required=True, help="adb device serial, e.g. emulator-5554")
    ap.add_argument("--artifact-dir", required=True, type=Path, help="Directory for evidence checkpoints")
    ap.add_argument("--workdir", type=Path, default=Path.cwd(), help="Codex --cd working directory")
    ap.add_argument("--no-launch", action="store_true", help="Do not launch the app first")
    ap.add_argument("--model", default=None, help="Override Codex model")
    ap.add_argument("--l3-model", default=None, help="Override Codex model for the L3 judge")
    args = ap.parse_args(argv)

    spec = load_run_spec(args.run_spec)
    verdict = run(
        spec,
        device=args.device,
        artifact_dir=args.artifact_dir,
        workdir=args.workdir,
        launch=not args.no_launch,
        model=args.model,
        l3_model=args.l3_model,
    )
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
