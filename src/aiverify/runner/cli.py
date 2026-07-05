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
from pathlib import Path

from aiverify.agent.oracle import L1Oracle
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

FINAL OUTPUT: a JSON object matching the provided schema — a "journey" name and a
"results" array with one entry per <action> ("action", "status" PASSED/FAILED/SKIPPED,
the "commands" you ran, and a short "comment").

--- JOURNEY SEGMENT TO EXECUTE ---
"""


def build_instruction_prefix(device: str) -> str:
    return _DRIVER_PREAMBLE.format(device=device)


def _trigger_steps(spec: RunSpec) -> list[str]:
    steps = list(spec.scenario.user_actions)
    for ev in spec.scenario.system_events:
        steps.append(f"[boundary] inject {ev.event} {ev.args}")
    return steps


def run(spec: RunSpec, *, device: str, artifact_dir: Path, workdir: Path,
        launch: bool = True, model: str | None = None) -> dict:
    controller = DeviceController(serial=device)
    # clear logcat so L1 only sees this run's events, not stale crashes from prior runs
    controller.logcat_clear()
    if launch:
        controller.launch(spec.package, spec.activity)

    runner = JourneySegmentRunner(
        backend=CodexCliBackend(),
        checkpoint_collector=AndroidEvidenceCollector(),
        system_event_injector=DeviceSystemEventInjector(device=controller, package=spec.package),
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
    # before = state after the segment that carries the boundary event; after = post-event.
    event_names = sorted(n for n in checkpoints if n.startswith("after-event-"))
    if not event_names:
        raise SystemExit("run spec has no boundary system event to compare around")
    idx = event_names[0].rsplit("-", 1)[1]
    before_cp = checkpoints[f"after-segment-{idx}"]
    after_cp = checkpoints[f"after-event-{idx}"]

    steps = _trigger_steps(spec)
    l2 = judge_l2_from_android_layout(
        before_cp.layout_path.read_text(encoding="utf-8"),
        after_cp.layout_path.read_text(encoding="utf-8"),
        spec.scenario.assertions,
        trigger_steps=steps,
    )
    l1 = L1Oracle().judge(after_cp.logcat_path.read_text(encoding="utf-8"), trigger_steps=steps)

    verdict = {
        "scenario": spec.scenario.id,
        "l1": l1,
        "l2": l2,
        "journey_results": [r.data for r in flow.journey_results],
        "checkpoints": [c.name for c in flow.checkpoints],
        "injected_events": [{"event": e.event, "args": e.args} for e in flow.injected_events],
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
    args = ap.parse_args(argv)

    spec = load_run_spec(args.run_spec)
    verdict = run(
        spec,
        device=args.device,
        artifact_dir=args.artifact_dir,
        workdir=args.workdir,
        launch=not args.no_launch,
        model=args.model,
    )
    print(f"scenario: {verdict['scenario']}")
    print(f"L1: {verdict['l1']['outcome']}  |  L2: {verdict['l2']['outcome']}"
          f"  (defect_class={verdict['l2']['defect_class_hypothesis']})")
    # non-zero exit when a defect is detected, so CI can gate on it
    return 1 if verdict["l2"]["outcome"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
