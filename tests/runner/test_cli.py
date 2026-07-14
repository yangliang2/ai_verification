"""runner CLI 的 L3 门控与降级逻辑单测（不触真机）。"""

import json
import subprocess
from pathlib import Path

import pytest

import aiverify.runner.cli as cli
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.providers.base import MockProvider
from aiverify.runner.codex_backend import JourneyExecutionResult
from aiverify.runner.evidence import AndroidEvidenceCollector, EvidenceCheckpoint
from aiverify.runner.journey import JourneyExecutionInterrupted, JourneySegmentFlow
from aiverify.runner.run_spec import (
    AssertionSpec,
    AppSmokeSpec,
    LiveValidationSpec,
    MetricContextSpec,
    RunSpec,
    ScenarioSpec,
    SystemEventSpec,
)


def _spec(
    tmp_path,
    l3_spec: str,
    metric_context: MetricContextSpec | None = None,
) -> RunSpec:
    return RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.wikipedia.dev",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(
            id="ui-rendering-test",
            user_actions=["走完 onboarding 到主 feed，观察底部导航栏"],
            l3_spec=l3_spec,
            metric_context=metric_context or MetricContextSpec(),
        ),
    )


def _flow(tmp_path) -> JourneySegmentFlow:
    cp_dir = tmp_path / "after-segment-0"
    cp_dir.mkdir()
    layout = cp_dir / "layout.json"
    layout.write_text('[{"resource-id": "nav_tab_home", "content-desc": "Home"}]', encoding="utf-8")
    screenshot = cp_dir / "screen.png"
    screenshot.write_bytes(b"png")
    logcat = cp_dir / "logcat.txt"
    logcat.write_text("", encoding="utf-8")
    commands = cp_dir / "commands.json"
    commands.write_text("[]", encoding="utf-8")
    cp = EvidenceCheckpoint(
        name="after-segment-0", directory=cp_dir, layout_path=layout,
        screenshot_path=screenshot, annotated_screenshot_path=None,
        logcat_path=logcat, commands_path=commands,
    )
    jr = JourneyExecutionResult(
        data={"journey": "seg-0", "results": [{"action": "a", "status": "PASSED"}]},
        result_path=cp_dir / "codex-journey-result.json",
        events_path=cp_dir / "codex-events.jsonl",
        command=["codex"],
    )
    return JourneySegmentFlow(journey_results=[jr], checkpoints=[cp])


def _oracle_verdict(outcome: str, level: str) -> dict:
    return {
        "verdict_id": f"{level}-test", "level": level, "outcome": outcome,
        "defect_class_hypothesis": None, "trigger_steps": [],
        "evidence": [], "confidence": 0.5,
    }


def _l2_checkpoint(tmp_path, name: str, text: str) -> EvidenceCheckpoint:
    directory = tmp_path / name
    directory.mkdir()
    layout = directory / "layout.json"
    layout.write_text(
        json.dumps([{"resource-id": "sentinel", "text": text}]), encoding="utf-8"
    )
    return EvidenceCheckpoint(
        name=name,
        directory=directory,
        layout_path=layout,
        screenshot_path=directory / "screen.png",
        annotated_screenshot_path=None,
        logcat_path=directory / "logcat.txt",
        commands_path=directory / "commands.json",
    )


_VALID_L3_JSON = json.dumps({
    "verdict_id": "L3-deadbeef", "level": "L3", "outcome": "fail",
    "defect_class_hypothesis": "ui_rendering",
    "trigger_steps": ["observe bottom nav"],
    "evidence": [{"type": "llm_reasoning", "ref": "layout", "note": "labels swapped"}],
    "confidence": 0.9,
})


class FakePreflightRunner(CommandRunner):
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
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
        response = self.responses.pop(0)
        if response.get("timeout"):
            raise subprocess.TimeoutExpired(args, timeout_seconds)
        return CommandResult(
            args=args,
            stdout=str(response.get("stdout", "")),
            stderr=str(response.get("stderr", "")),
            returncode=int(response.get("returncode", 0)),
        )


def _passing_preflight_responses() -> list[dict[str, object]]:
    return [
        {"stdout": "List of devices attached\nemulator-5554 device product:sdk\n"},
        {"stdout": "1\n"},
        {"stdout": "stopped\n"},
        {"stdout": '[{"resource-id":"launcher"}]'},
        {"stdout": "UI hierchary dumped to: /sdcard/window_dump.xml\n"},
    ]


@pytest.fixture
def mock_provider_cls(monkeypatch):
    """把 cli.CodexCliProvider 换成返回预置响应的 MockProvider 工厂。"""
    holder: dict = {"provider": None, "responses": [], "init_kwargs": []}

    def factory(**kwargs):
        holder["init_kwargs"].append(kwargs)
        holder["provider"] = MockProvider(list(holder["responses"]))
        return holder["provider"]

    monkeypatch.setattr(cli, "CodexCliProvider", factory)
    return holder


def test_l3_skipped_without_l3_spec(tmp_path, mock_provider_cls):
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec=""), _flow(tmp_path),
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=[], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is None
    assert mock_provider_cls["provider"] is None  # 未构造 provider，零成本


@pytest.mark.parametrize("l1_outcome,l2_outcome", [("fail", "inconclusive"), ("inconclusive", "fail")])
def test_l3_skipped_when_cheaper_oracle_already_failed(tmp_path, mock_provider_cls, l1_outcome, l2_outcome):
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec="底部导航必须显示 Home/Saved/Search/Activity/More"), _flow(tmp_path),
        l1=_oracle_verdict(l1_outcome, "L1"), l2=_oracle_verdict(l2_outcome, "L2"),
        steps=[], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is None
    assert mock_provider_cls["provider"] is None


def test_l3_runs_when_gated_open_and_returns_judge_verdict(tmp_path, mock_provider_cls):
    mock_provider_cls["responses"] = [_VALID_L3_JSON]
    flow = _flow(tmp_path)
    spec = _spec(tmp_path, l3_spec="底部导航必须显示 Home/Saved/Search/Activity/More")
    verdict = cli._judge_l3(
        spec, flow,
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=["step-1"], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is not None
    assert verdict["outcome"] == "fail"
    assert verdict["defect_class_hypothesis"] == "ui_rendering"
    # judge 收到的 prompt 含轨迹事实：用户动作 + 最终 layout 全文
    prompt = mock_provider_cls["provider"].calls[0]["prompt"]
    assert "走完 onboarding" in prompt
    assert "nav_tab_home" in prompt
    assert "底部导航必须显示" in prompt
    # 且不含 expected_behavior 之类的泄题通道（spec 里本来就没设）
    # timing 增加 l3-judge phase
    assert flow.timings[-1]["phase"] == "l3-judge"
    assert flow.timings[-1]["kind"] == "oracle"


def test_l3_schema_failure_twice_degrades_to_inconclusive(tmp_path, mock_provider_cls):
    mock_provider_cls["responses"] = ['{"not": "a verdict"}', '{"still": "not"}']
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec="spec"), _flow(tmp_path),
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=["s"], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is not None
    assert verdict["verdict_id"] == "L3-error"
    assert verdict["outcome"] == "inconclusive"
    assert "VerdictValidationError" in verdict["evidence"][0]["note"]


def test_l3_unparseable_json_degrades_to_inconclusive(tmp_path, mock_provider_cls):
    mock_provider_cls["responses"] = ["this is not json at all"]
    verdict = cli._judge_l3(
        _spec(tmp_path, l3_spec="spec"), _flow(tmp_path),
        l1=_oracle_verdict("inconclusive", "L1"), l2=_oracle_verdict("inconclusive", "L2"),
        steps=["s"], workdir=tmp_path, artifact_dir=tmp_path, model=None,
    )
    assert verdict is not None
    assert verdict["verdict_id"] == "L3-error"
    assert verdict["outcome"] == "inconclusive"


def test_metric_context_separates_seed_taxonomy_from_oracle_class(tmp_path):
    spec = _spec(
        tmp_path,
        l3_spec="",
        metric_context=MetricContextSpec(
            seed_kind="injected_defect",
            taxonomy_category="navigation",
            taxonomy_pattern_id="navigation-02",
            expected_oracle_level="L2",
            expected_oracle_defect_class="state_loss",
        ),
    )
    l1 = _oracle_verdict("inconclusive", "L1")
    l2 = _oracle_verdict("fail", "L2")
    l2["defect_class_hypothesis"] = "state_loss"

    context = cli._build_metric_context(spec, l1=l1, l2=l2, l3=None)

    assert context["seed_outcome"] == "caught"
    assert context["taxonomy_category"] == "navigation"
    assert context["taxonomy_pattern_id"] == "navigation-02"
    assert context["expected_oracle_defect_class"] == "state_loss"
    assert context["oracle_defect_classes"] == {
        "L1": None,
        "L2": "state_loss",
        "L3": None,
    }
    assert context["failed_oracles"] == ["L2"]


def test_metric_context_marks_missed_injected_seed(tmp_path):
    spec = _spec(
        tmp_path,
        l3_spec="",
        metric_context=MetricContextSpec(seed_kind="injected_defect"),
    )

    context = cli._build_metric_context(
        spec,
        l1=_oracle_verdict("inconclusive", "L1"),
        l2=_oracle_verdict("pass", "L2"),
        l3=None,
    )

    assert context["seed_outcome"] == "missed"
    assert context["failed_oracles"] == []


def test_interrupted_journey_writes_non_accountable_run_result(tmp_path, monkeypatch):
    flow = _flow(tmp_path)

    class FakeController:
        def __init__(self, serial):
            self.serial = serial

        def logcat_clear(self):
            return None

        def launch(self, package, activity):
            return None

    class InterruptedRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise JourneyExecutionInterrupted(
                reason="journey_action_failed",
                message="Search card was unavailable",
                journey_results=flow.journey_results,
                checkpoints=flow.checkpoints,
                injected_events=[],
                timings=flow.timings,
                backend_diagnostics=[
                    {
                        "result": None,
                        "events": str(tmp_path / "codex-events.jsonl"),
                        "command": ["codex", "exec"],
                    }
                ],
            )

    monkeypatch.setattr(cli, "DeviceController", FakeController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", InterruptedRunner)

    artifact_dir = tmp_path / "run" / "artifacts"
    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"] == {
        "status": "non_accountable",
        "accounting_eligible": False,
        "reason": "journey_action_failed",
        "message": "Search card was unavailable",
    }
    assert verdict["metric_context"]["seed_outcome"] == "not_accountable"
    assert verdict["l1"] is None
    assert verdict["l2"] is None
    assert verdict["l3"] is None
    assert verdict["diagnostic_artifacts"]["journey_results"] == [
        {
            "result": str(flow.journey_results[0].result_path),
            "events": str(flow.journey_results[0].events_path),
        }
    ]
    assert verdict["diagnostic_artifacts"]["checkpoints"] == [
        {
            "name": "after-segment-0",
            "directory": str(flow.checkpoints[0].directory),
            "layout": str(flow.checkpoints[0].layout_path),
            "screenshot": str(flow.checkpoints[0].screenshot_path),
            "annotated_screenshot": None,
            "logcat": str(flow.checkpoints[0].logcat_path),
            "commands": str(flow.checkpoints[0].commands_path),
            "manifest": None,
        }
    ]
    assert verdict["diagnostic_artifacts"]["backend_errors"] == [
        {
            "result": None,
            "events": str(tmp_path / "codex-events.jsonl"),
            "command": ["codex", "exec"],
        }
    ]
    persisted = json.loads((artifact_dir.parent / "verdict.json").read_text(encoding="utf-8"))
    assert persisted == verdict


def test_public_run_retains_failed_anr_checkpoint_diagnostics(tmp_path, monkeypatch):
    class FakeController:
        def __init__(self, serial):
            self.serial = serial

        def logcat_clear(self):
            return None

        def launch(self, package, activity):
            return None

    class SuccessfulBackend:
        def execute(self, request):
            request.artifact_dir.mkdir(parents=True, exist_ok=True)
            result_path = request.artifact_dir / "result.json"
            events_path = request.artifact_dir / "events.jsonl"
            result_path.write_text("{}", encoding="utf-8")
            events_path.write_text("", encoding="utf-8")
            return JourneyExecutionResult(
                data={
                    "journey": "anr-defect-1-segment-0",
                    "results": [
                        {
                            "action": "走完 onboarding 到主 feed，观察底部导航栏",
                            "status": "PASSED",
                            "commands": [],
                            "comment": "completed before checkpoint failure",
                        }
                    ],
                },
                result_path=result_path,
                events_path=events_path,
                command=["codex"],
            )

    class AnrCaptureCommandRunner(CommandRunner):
        def run(
            self,
            args,
            *,
            cwd=None,
            timeout_seconds=None,
            input_text=None,
        ):
            if args[:2] == ["android", "layout"]:
                return CommandResult(
                    args=args,
                    stdout="",
                    stderr="Failed to retrieve UI dump: \n",
                    returncode=0,
                )
            if args[:3] == ["android", "screen", "capture"]:
                output = Path(args[args.index("-o") + 1])
                output.write_bytes(b"diagnostic png")
                return CommandResult(args=args, stdout=str(output), stderr="", returncode=0)
            if args[-2:] == ["logcat", "-d"]:
                return CommandResult(
                    args=args,
                    stdout="ANR in org.wikipedia.dev\n",
                    stderr="",
                    returncode=0,
                )
            raise AssertionError(f"unexpected command: {args}")

    collector = AndroidEvidenceCollector(
        runner=AnrCaptureCommandRunner(),
        layout_attempts=2,
        layout_retry_sleep_seconds=0,
    )
    monkeypatch.setattr(cli, "DeviceController", FakeController)
    monkeypatch.setattr(cli, "CodexCliBackend", SuccessfulBackend)
    monkeypatch.setattr(cli, "AndroidEvidenceCollector", lambda: collector)

    artifact_dir = tmp_path / "run" / "artifacts"
    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["status"] == "non_accountable"
    assert verdict["execution"]["accounting_eligible"] is False
    assert verdict["execution"]["reason"] == "checkpoint_capture_error"
    assert verdict["metric_context"]["seed_outcome"] == "not_accountable"
    assert verdict["l1"] is None
    checkpoint = verdict["diagnostic_artifacts"]["checkpoints"][0]
    assert checkpoint["name"] == "after-segment-0"
    assert Path(checkpoint["manifest"]).is_file()
    assert Path(checkpoint["screenshot"]).read_bytes() == b"diagnostic png"
    assert Path(checkpoint["logcat"]).read_text(encoding="utf-8") == (
        "ANR in org.wikipedia.dev\n"
    )


def test_completed_run_persists_and_links_live_validation_preflight(tmp_path, monkeypatch):
    flow = _flow(tmp_path)
    controller_calls: list[object] = []

    class FakeController:
        def __init__(self, serial):
            controller_calls.append(("init", serial))

        def logcat_clear(self):
            controller_calls.append("logcat_clear")

        def launch(self, package, activity):
            controller_calls.append(("launch", package, activity))

    class SuccessfulRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return flow

    monkeypatch.setattr(cli, "DeviceController", FakeController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", SuccessfulRunner)

    artifact_dir = tmp_path / "run" / "artifacts"
    preflight_runner = FakePreflightRunner(_passing_preflight_responses())

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=preflight_runner,
    )

    gate_path = artifact_dir.parent / "live-validation-gate.json"
    assert gate_path.is_file()
    assert json.loads(gate_path.read_text(encoding="utf-8"))["status"] == "passed"
    assert verdict["execution"]["status"] == "completed"
    assert verdict["preflight"]["live_validation_gate"] == {
        "status": "passed",
        "artifact": str(gate_path),
        "failed_checks": [],
    }
    assert verdict["metric_context"]["seed_outcome"] == "not_detected"
    assert controller_calls == [
        ("init", "emulator-5554"),
        "logcat_clear",
        ("launch", "org.wikipedia.dev", None),
    ]
    assert [call[0:2] for call in preflight_runner.calls] == [
        ["adb", "devices"],
        ["adb", "-s"],
        ["adb", "-s"],
        ["android", "layout"],
        ["adb", "-s"],
    ]


def test_failed_live_validation_preflight_is_non_accountable_and_blocks_launch(
    tmp_path, monkeypatch
):
    class UnexpectedController:
        def __init__(self, serial):
            raise AssertionError("DeviceController must not be constructed")

    class UnexpectedRunner:
        def __init__(self, **kwargs):
            raise AssertionError("JourneySegmentRunner must not be constructed")

    monkeypatch.setattr(cli, "DeviceController", UnexpectedController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", UnexpectedRunner)
    responses = _passing_preflight_responses()
    responses[3] = {"stdout": "not json"}
    preflight_runner = FakePreflightRunner(responses)
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=preflight_runner,
    )

    gate_path = artifact_dir.parent / "live-validation-gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate["status"] == "failed"
    assert gate["failed_checks"] == ["android-layout-json"]
    assert verdict["execution"] == {
        "status": "non_accountable",
        "accounting_eligible": False,
        "reason": "live_validation_preflight_failed",
        "message": "live-validation preflight failed: android-layout-json",
    }
    assert verdict["metric_context"]["seed_outcome"] == "not_accountable"
    assert verdict["l1"] is None
    assert verdict["l2"] is None
    assert verdict["l3"] is None
    assert verdict["preflight"]["live_validation_gate"]["artifact"] == str(gate_path)
    assert verdict["diagnostic_artifacts"]["live_validation_gate"] == str(gate_path)


def test_app_smoke_preflight_uses_explicit_run_spec_configuration(tmp_path, monkeypatch):
    flow = _flow(tmp_path)
    captured_preflight_kwargs: dict[str, object] = {}

    class FakeController:
        def __init__(self, serial):
            pass

        def logcat_clear(self):
            return None

        def launch(self, package, activity):
            return None

    class SuccessfulRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return flow

    def fake_gate(**kwargs):
        captured_preflight_kwargs.update(kwargs)
        return cli.GateResult(device=kwargs["device"], status="passed", checks=())

    monkeypatch.setattr(cli, "DeviceController", FakeController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", SuccessfulRunner)
    monkeypatch.setattr(cli, "run_live_validation_gate", fake_gate)

    spec = _spec(tmp_path, l3_spec="")
    spec = RunSpec(
        host_project=spec.host_project,
        apk_glob=spec.apk_glob,
        package="com.example.host",
        activity="com.example.host.MainActivity",
        diff=spec.diff,
        spec=spec.spec,
        scenario=spec.scenario,
        live_validation=LiveValidationSpec(
            timeout_seconds=11,
            app_smoke=AppSmokeSpec(
                target_text="Dashboard",
                target_content_desc="Main dashboard",
                app_settle_seconds=0,
            ),
        ),
    )

    cli.run(
        spec,
        device="emulator-5554",
        artifact_dir=tmp_path / "run" / "artifacts",
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner([]),
    )

    assert captured_preflight_kwargs["app_package"] == "com.example.host"
    assert captured_preflight_kwargs["app_activity"] == "com.example.host.MainActivity"
    assert captured_preflight_kwargs["target_text"] == "Dashboard"
    assert captured_preflight_kwargs["target_content_desc"] == "Main dashboard"
    assert captured_preflight_kwargs["app_settle_seconds"] == 0
    assert captured_preflight_kwargs["timeout_seconds"] == 11


def test_main_returns_distinct_status_for_non_accountable_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_run_spec", lambda path: object())
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: {
            "scenario": "interrupted",
            "execution": {
                "status": "non_accountable",
                "reason": "journey_action_failed",
                "message": "Search card was unavailable",
            },
            "l1": None,
            "l2": None,
            "l3": None,
        },
    )

    status = cli.main(
        [
            "run-spec.yaml",
            "--device",
            "emulator-5554",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
        ]
    )

    assert status == 2


def test_l2_is_inconclusive_for_ambiguous_multiple_boundaries(tmp_path):
    scenario = ScenarioSpec(
        id="two-boundaries",
        system_events=[
            SystemEventSpec(step_index=0, event="rotate"),
            SystemEventSpec(step_index=1, event="dark_mode"),
        ],
    )

    verdict = cli._judge_l2_from_checkpoints(scenario, {}, steps=[])

    assert verdict["outcome"] == "inconclusive"
    assert "multiple system-event boundaries" in verdict["evidence"][0]["note"]


def test_l2_keeps_eventless_scenarios_inconclusive(tmp_path):
    verdict = cli._judge_l2_from_checkpoints(ScenarioSpec(id="eventless"), {}, steps=[])

    assert verdict["outcome"] == "inconclusive"
    assert verdict["evidence"][0]["ref"] == "no boundary system event"


def test_l2_keeps_single_boundary_default_selection(tmp_path):
    scenario = ScenarioSpec(
        id="one-boundary",
        system_events=[SystemEventSpec(step_index=0, event="rotate")],
        assertions=[AssertionSpec(resource_id="sentinel", attr="text", expected="kept")],
    )
    checkpoints = {
        "after-segment-0": _l2_checkpoint(tmp_path, "after-segment-0", "kept"),
        "after-event-0": _l2_checkpoint(tmp_path, "after-event-0", "kept"),
    }

    verdict = cli._judge_l2_from_checkpoints(scenario, checkpoints, steps=[])

    assert verdict["outcome"] == "pass"


def test_l2_uses_explicitly_selected_boundary(tmp_path):
    scenario = ScenarioSpec(
        id="two-boundaries",
        system_events=[
            SystemEventSpec(step_index=0, event="rotate"),
            SystemEventSpec(step_index=1, event="dark_mode"),
        ],
        l2_boundary_index=1,
        assertions=[AssertionSpec(resource_id="sentinel", attr="text", expected="kept")],
    )
    checkpoints = {
        "after-segment-0": _l2_checkpoint(tmp_path, "after-segment-0", "lost"),
        "after-event-0": _l2_checkpoint(tmp_path, "after-event-0", "lost"),
        "after-segment-1": _l2_checkpoint(tmp_path, "after-segment-1", "kept"),
        "after-event-1": _l2_checkpoint(tmp_path, "after-event-1", "kept"),
    }

    verdict = cli._judge_l2_from_checkpoints(scenario, checkpoints, steps=[])

    assert verdict["outcome"] == "pass"


def test_l2_selection_supports_tenth_boundary_without_lexical_sorting(tmp_path):
    scenario = ScenarioSpec(
        id="many-boundaries",
        system_events=[SystemEventSpec(step_index=index, event="rotate") for index in range(11)],
        l2_boundary_index=10,
        assertions=[AssertionSpec(resource_id="sentinel", attr="text", expected="kept")],
    )
    checkpoints = {
        "after-segment-10": _l2_checkpoint(tmp_path, "after-segment-10", "kept"),
        "after-event-10": _l2_checkpoint(tmp_path, "after-event-10", "kept"),
    }

    verdict = cli._judge_l2_from_checkpoints(scenario, checkpoints, steps=[])

    assert verdict["outcome"] == "pass"
