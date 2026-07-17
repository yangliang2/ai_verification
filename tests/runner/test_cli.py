"""runner CLI 的 L3 门控与降级逻辑单测（不触真机）。"""

import json
import re
import subprocess
from pathlib import Path

import pytest

import aiverify.runner.cli as cli
import aiverify.runner.execution_record as execution_record_module
from aiverify.harness.device import AdbResult
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.providers.base import MockProvider
from aiverify.runner.codex_backend import JourneyExecutionResult
from aiverify.runner.evidence import AndroidEvidenceCollector, EvidenceCheckpoint
from aiverify.runner.execution_record import ExecutionRecordStorageError
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


class StaticCheckpointCollector:
    def __init__(self, *, logcat_text: str = "") -> None:
        self.logcat_text = logcat_text

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
        layout.write_text('[{"resource-id":"search_card"}]', encoding="utf-8")
        screenshot = directory / "screen.png"
        screenshot.write_bytes(b"png")
        logcat = directory / "logcat.txt"
        logcat.write_text(self.logcat_text, encoding="utf-8")
        commands = directory / "commands.json"
        commands.write_text("[]", encoding="utf-8")
        return EvidenceCheckpoint(
            name=name,
            directory=directory,
            layout_path=layout,
            screenshot_path=screenshot,
            annotated_screenshot_path=None,
            logcat_path=logcat,
            commands_path=commands,
        )


class HistoricalLineageBackend:
    def __init__(
        self,
        *,
        status: str,
        commands: list[str],
        comment: str,
    ) -> None:
        self.status = status
        self.commands = commands
        self.comment = comment

    def execute(self, request) -> JourneyExecutionResult:
        request.artifact_dir.mkdir(parents=True, exist_ok=True)
        journey = re.search(
            r'<journey name="([^"]+)">', request.journey_instructions
        ).group(1)
        action_id = re.search(
            r'<action id="([^"]+)">', request.journey_instructions
        ).group(1)
        data = {
            "journey": journey,
            "results": [
                {
                    "action_id": action_id,
                    "status": self.status,
                    "commands": self.commands,
                    "comment": self.comment,
                }
            ],
        }
        result_path = request.artifact_dir / "codex-journey-result.json"
        events_path = request.artifact_dir / "codex-events.jsonl"
        result_path.write_text(json.dumps(data), encoding="utf-8")
        events_path.write_text(json.dumps(data) + "\n", encoding="utf-8")
        return JourneyExecutionResult(
            data=data,
            result_path=result_path,
            events_path=events_path,
            command=["codex", "exec"],
        )


class FakeDeviceController:
    def __init__(self, serial: str) -> None:
        self.serial = serial

    def logcat_clear(self) -> None:
        return None

    def launch(self, package: str, activity: str | None) -> None:
        return None


def _passing_preflight_responses() -> list[dict[str, object]]:
    return [
        {"stdout": "List of devices attached\nemulator-5554 device product:sdk\n"},
        {"stdout": "1\n"},
        {"stdout": "stopped\n"},
        {"stdout": '[{"resource-id":"launcher"}]'},
        {"stdout": "UI hierchary dumped to: /sdcard/window_dump.xml\n"},
    ]


def test_instruction_prefix_separates_action_dispatch_from_product_outcome() -> None:
    prefix = " ".join(cli.build_instruction_prefix("emulator-5554").split())

    assert "copy its stable id into action_id" in prefix
    assert "PASSED means the requested UI interaction was dispatched" in prefix
    assert "A crash, ANR, or incorrect UI after that dispatch is product evidence" in prefix
    assert "Do not infer dispatch from apparent UI side effects" in prefix


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
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "interrupted"
    assert record["execution"] == verdict["execution"]
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"] == [
        {
            "phase": "journey",
            "kind": "journey",
            "reason": "journey_action_failed",
            "message": "Search card was unavailable",
        }
    ]
    assert record["evidence_refs"]["checkpoints"] == [
        str(flow.checkpoints[0].directory)
    ]
    assert record["evidence_refs"]["journey_results"] == [
        str(flow.journey_results[0].result_path)
    ]
    assert verdict["execution_record"] == str(
        artifact_dir.parent / "execution-record.json"
    )


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


def test_public_run_restores_search_card_action_from_stable_id(
    tmp_path, monkeypatch
):
    requested = (
        "Navigate from the main feed to the bottom Search tab and confirm the Search "
        "tab is selected with search_card visible."
    )
    spec = RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.wikipedia.dev",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(id="search-card", user_actions=[requested]),
    )
    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(
        cli,
        "CodexCliBackend",
        lambda: HistoricalLineageBackend(
            status="PASSED",
            commands=["android layout", "adb shell input tap 540 2232"],
            comment="Search is selected and search_card is visible.",
        ),
    )
    monkeypatch.setattr(
        cli, "AndroidEvidenceCollector", lambda: StaticCheckpointCollector()
    )

    verdict = cli.run(
        spec,
        device="emulator-5554",
        artifact_dir=tmp_path / "run" / "artifacts",
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["status"] == "completed"
    assert verdict["execution"]["accounting_eligible"] is True
    assert verdict["journey_results"][0]["results"][0] == {
        "action_id": "action-1",
        "action": requested,
        "status": "PASSED",
        "commands": ["android layout", "adb shell input tap 540 2232"],
        "comment": "Search is selected and search_card is visible.",
    }
    segment_dir = tmp_path / "run" / "artifacts" / "search-card-segment-0"
    assert (segment_dir / "codex-journey-result.json").is_file()
    assert (segment_dir / "codex-journey-result.normalized.json").is_file()
    assert (segment_dir / "codex-events.jsonl").is_file()


def test_public_run_keeps_dispatched_anr_trigger_accountable_for_l1(
    tmp_path, monkeypatch
):
    requested = "点搜索输入框 search_src_text，输入文本 'anrtest'"
    spec = RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.wikipedia.dev",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(
            id="anr-trigger",
            user_actions=[requested],
            metric_context=MetricContextSpec(
                seed_kind="injected_defect",
                taxonomy_category="coroutine-concurrency",
                taxonomy_pattern_id="coroutine-concurrency-03",
                expected_oracle_level="L1",
                expected_oracle_defect_class="crash_stability",
            ),
        ),
    )
    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(
        cli,
        "CodexCliBackend",
        lambda: HistoricalLineageBackend(
            status="PASSED",
            commands=[
                "adb -s emulator-5554 shell input tap 542 146",
                'adb -s emulator-5554 shell input text "anrtest"',
            ],
            comment=(
                "The input command was dispatched; the app then stopped responding, "
                "which is retained as product evidence."
            ),
        ),
    )
    monkeypatch.setattr(
        cli,
        "AndroidEvidenceCollector",
        lambda: StaticCheckpointCollector(
            logcat_text="ActivityManager: ANR in org.wikipedia.dev\n"
        ),
    )

    verdict = cli.run(
        spec,
        device="emulator-5554",
        artifact_dir=tmp_path / "run" / "artifacts",
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["status"] == "completed"
    assert verdict["execution"]["accounting_eligible"] is True
    assert verdict["l1"]["outcome"] == "fail"
    assert verdict["l1"]["defect_class_hypothesis"] == "crash_stability"
    assert verdict["metric_context"]["seed_outcome"] == "caught"
    assert verdict["journey_results"][0]["results"][0]["status"] == "PASSED"


def test_public_run_system_event_failure_is_canonical_and_skips_all_oracles(
    tmp_path, monkeypatch
):
    class FailingRotateController(FakeDeviceController):
        def rotate(self, rotation):
            return (
                AdbResult(stdout="", stderr="", returncode=0),
                AdbResult(
                    stdout="", stderr="settings service unavailable", returncode=13
                ),
            )

    spec = RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.wikipedia.dev",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(
            id="rotate-failure",
            user_actions=["Open search"],
            system_events=[SystemEventSpec(step_index=0, event="rotate")],
        ),
    )
    monkeypatch.setattr(cli, "DeviceController", FailingRotateController)
    monkeypatch.setattr(
        cli,
        "CodexCliBackend",
        lambda: HistoricalLineageBackend(
            status="PASSED", commands=["android layout"], comment="Search opened."
        ),
    )
    monkeypatch.setattr(
        cli, "AndroidEvidenceCollector", lambda: StaticCheckpointCollector()
    )
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        spec,
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["reason"] == "system_event_error"
    assert verdict["execution"]["accounting_eligible"] is False
    assert verdict["metric_context"]["oracle_outcomes"] == {
        "L1": "not_run",
        "L2": "not_run",
        "L3": "not_run",
    }
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    assert verdict["checkpoints"] == ["after-segment-0"]
    assert verdict["injected_events"] == []
    assert not (artifact_dir / "after-event-0").exists()

    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "interrupted"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"] == [
        {
            "phase": "event-0",
            "kind": "system_event",
            "reason": "system_event_error",
            "message": (
                "SystemEventInjectionError: rotate command returned return code 13: "
                "settings service unavailable"
            ),
        }
    ]


def test_public_run_reproduces_historical_anr_failed_status(
    tmp_path, monkeypatch
):
    requested = "点搜索输入框 search_src_text，输入文本 'anrtest'"
    spec = RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.wikipedia.dev",
        activity=None,
        diff=None,
        spec=None,
        scenario=ScenarioSpec(id="historical-anr-failed", user_actions=[requested]),
    )
    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(
        cli,
        "CodexCliBackend",
        lambda: HistoricalLineageBackend(
            status="FAILED",
            commands=[
                "adb -s emulator-5554 shell input tap 542 146",
                'adb -s emulator-5554 shell input text "anrtest"',
            ],
            comment=(
                "search_src_text was focused before typing, but the text command "
                "stalled and the app returned to the Search tab."
            ),
        ),
    )
    monkeypatch.setattr(
        cli,
        "AndroidEvidenceCollector",
        lambda: StaticCheckpointCollector(
            logcat_text="ActivityManager: ANR in org.wikipedia.dev\n"
        ),
    )

    verdict = cli.run(
        spec,
        device="emulator-5554",
        artifact_dir=tmp_path / "run" / "artifacts",
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["status"] == "non_accountable"
    assert verdict["execution"]["reason"] == "journey_action_failed"
    assert verdict["l1"] is None
    diagnostic = verdict["diagnostic_artifacts"]["journey_results"][0]
    assert Path(diagnostic["result"]).name == "codex-journey-result.normalized.json"
    assert Path(diagnostic["raw_result"]).name == "codex-journey-result.json"
    assert Path(diagnostic["action_lineage"]).name == (
        "codex-journey-action-lineage.json"
    )
    assert all(Path(path).is_file() for path in diagnostic.values())


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


def test_public_run_establishes_one_execution_record_before_preflight_and_finalizes_it(
    tmp_path, monkeypatch
):
    flow = _flow(tmp_path)
    artifact_dir = tmp_path / "run" / "artifacts"
    record_path = artifact_dir.parent / "execution-record.json"
    observed_record: dict[str, object] = {}

    class InspectingPreflightRunner(FakePreflightRunner):
        def run(self, *args, **kwargs):
            if not observed_record:
                observed_record.update(
                    json.loads(record_path.read_text(encoding="utf-8"))
                )
            return super().run(*args, **kwargs)

    class SuccessfulRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return flow

    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", SuccessfulRunner)

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=InspectingPreflightRunner(
            _passing_preflight_responses()
        ),
    )

    assert observed_record["lifecycle_state"] == "in_progress"
    assert observed_record["finished_at"] is None
    attempt_id = observed_record["attempt_id"]
    assert isinstance(attempt_id, str) and attempt_id

    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["attempt_id"] == attempt_id
    assert record["lifecycle_state"] == "completed"
    assert record["execution"] == verdict["execution"]
    assert record["process_outcome"] == {"exit_code": 0}
    assert record["phase_errors"] == []
    assert record["evidence_refs"] == {
        "live_validation_gate": str(artifact_dir.parent / "live-validation-gate.json"),
        "verdict": str(artifact_dir.parent / "verdict.json"),
        "journey_results": [str(flow.journey_results[0].result_path)],
        "checkpoints": [str(flow.checkpoints[0].directory)],
    }
    assert verdict["execution_record"] == str(record_path)
    assert not list(artifact_dir.parent.glob(".execution-record.*.tmp"))


def test_public_run_rejects_reused_attempt_directory_before_preflight(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    prior_verdict = run_dir / "verdict.json"
    prior_verdict.write_text('{"prior": true}\n', encoding="utf-8")

    class UnexpectedPreflightRunner(CommandRunner):
        def run(self, *args, **kwargs):
            raise AssertionError("preflight must not run without fresh record storage")

    with pytest.raises(ExecutionRecordStorageError, match="existing runner output"):
        cli.run(
            _spec(tmp_path, l3_spec=""),
            device="emulator-5554",
            artifact_dir=run_dir / "artifacts",
            workdir=tmp_path,
            preflight_command_runner=UnexpectedPreflightRunner(),
        )

    assert prior_verdict.read_text(encoding="utf-8") == '{"prior": true}\n'
    assert not (run_dir / "execution-record.json").exists()


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
    record_path = artifact_dir.parent / "execution-record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["lifecycle_state"] == "preflight_rejected"
    assert record["execution"] == verdict["execution"]
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"] == [
        {
            "phase": "live-validation-preflight",
            "kind": "preflight",
            "reason": "live_validation_preflight_failed",
            "message": "live-validation preflight failed: android-layout-json",
        }
    ]
    assert record["evidence_refs"] == {
        "live_validation_gate": str(gate_path),
        "verdict": str(artifact_dir.parent / "verdict.json"),
    }
    assert verdict["execution_record"] == str(record_path)


def test_live_validation_gate_output_failure_finalizes_as_non_accountable(
    tmp_path, monkeypatch
):
    artifact_dir = tmp_path / "run" / "artifacts"
    gate_path = artifact_dir.parent / "live-validation-gate.json"

    class GateBlockingPreflightRunner(FakePreflightRunner):
        def run(self, *args, **kwargs):
            result = super().run(*args, **kwargs)
            if not self.responses:
                gate_path.mkdir()
            return result

    class UnexpectedController:
        def __init__(self, serial):
            raise AssertionError("device setup must not follow gate output failure")

    monkeypatch.setattr(cli, "DeviceController", UnexpectedController)

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=GateBlockingPreflightRunner(
            _passing_preflight_responses()
        ),
    )

    assert verdict["execution"]["reason"] == "output_finalization_error"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "failed"
    assert record["phase_errors"][0]["phase"] == "live-validation-gate-output"
    assert "ArtifactStorageError" in record["phase_errors"][0]["message"]
    assert record["evidence_refs"] == {}


def test_preflight_rejection_verdict_output_failure_preserves_ordered_errors(
    tmp_path, monkeypatch
):
    artifact_dir = tmp_path / "run" / "artifacts"
    verdict_path = artifact_dir.parent / "verdict.json"
    responses = _passing_preflight_responses()
    responses[3] = {"stdout": "not json"}

    class VerdictBlockingPreflightRunner(FakePreflightRunner):
        def run(self, *args, **kwargs):
            result = super().run(*args, **kwargs)
            if not self.responses:
                verdict_path.mkdir()
            return result

    class UnexpectedController:
        def __init__(self, serial):
            raise AssertionError("device setup must not follow rejected preflight")

    monkeypatch.setattr(cli, "DeviceController", UnexpectedController)

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=VerdictBlockingPreflightRunner(responses),
    )

    assert verdict["execution"]["reason"] == "output_finalization_error"
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "failed"
    assert [error["reason"] for error in record["phase_errors"]] == [
        "live_validation_preflight_failed",
        "output_finalization_error",
    ]
    assert record["evidence_refs"] == {
        "live_validation_gate": str(
            artifact_dir.parent / "live-validation-gate.json"
        )
    }


def test_preflight_timeout_finalizes_non_accountable_execution_record(
    tmp_path, monkeypatch
):
    class UnexpectedController:
        def __init__(self, serial):
            raise AssertionError("device setup must not run after preflight exception")

    class TimeoutPreflightRunner(CommandRunner):
        def run(
            self,
            args,
            *,
            cwd=None,
            timeout_seconds=None,
            input_text=None,
        ):
            raise subprocess.TimeoutExpired(args, timeout_seconds)

    monkeypatch.setattr(cli, "DeviceController", UnexpectedController)
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=TimeoutPreflightRunner(),
    )

    assert verdict["execution"]["status"] == "non_accountable"
    assert verdict["execution"]["reason"] == "live_validation_preflight_failed"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "preflight_rejected"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"][0]["phase"] == "live-validation-preflight"
    assert record["phase_errors"][0]["reason"] == "live_validation_preflight_failed"
    gate = json.loads(
        (artifact_dir.parent / "live-validation-gate.json").read_text(encoding="utf-8")
    )
    assert gate["checks"][0]["status"] == "timeout"
    assert "timed out" in gate["checks"][0]["error"]
    assert record["evidence_refs"]["live_validation_gate"] == str(
        artifact_dir.parent / "live-validation-gate.json"
    )


def test_unhandled_preflight_exception_becomes_a_terminal_non_accountable_run(
    tmp_path, monkeypatch
):
    class UnexpectedController:
        def __init__(self, serial):
            raise AssertionError("device setup must not run after preflight exception")

    class BrokenPreflightRunner(CommandRunner):
        def run(self, *args, **kwargs):
            raise OSError("adb binary vanished")

    monkeypatch.setattr(cli, "DeviceController", UnexpectedController)
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=BrokenPreflightRunner(),
    )

    assert verdict["execution"]["reason"] == "live_validation_preflight_failed"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "failed"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"] == [
        {
            "phase": "live-validation-preflight",
            "kind": "preflight",
            "reason": "live_validation_preflight_failed",
            "message": "OSError: adb binary vanished",
        }
    ]
    assert record["evidence_refs"] == {
        "verdict": str(artifact_dir.parent / "verdict.json")
    }


def test_runner_setup_failure_finalizes_record_before_journey_or_oracles(
    tmp_path, monkeypatch
):
    class FailingController:
        def __init__(self, serial):
            self.serial = serial

        def logcat_clear(self):
            raise OSError("logcat transport closed")

        def launch(self, package, activity):
            raise AssertionError("launch must not follow failed logcat clear")

    class UnexpectedJourneyRunner:
        def __init__(self, **kwargs):
            raise AssertionError("Journey must not start after runner setup failure")

    monkeypatch.setattr(cli, "DeviceController", FailingController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", UnexpectedJourneyRunner)
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["reason"] == "runner_setup_error"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "failed"
    assert record["phase_errors"] == [
        {
            "phase": "runner-setup",
            "kind": "runner",
            "reason": "runner_setup_error",
            "message": "OSError: logcat transport closed",
        }
    ]
    assert record["evidence_refs"]["live_validation_gate"] == str(
        artifact_dir.parent / "live-validation-gate.json"
    )


def test_oracle_exception_preserves_flow_evidence_but_skips_oracle_accounting(
    tmp_path, monkeypatch
):
    flow = _flow(tmp_path)

    class SuccessfulRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return flow

    class FailingL1Oracle:
        def judge(self, *args, **kwargs):
            raise RuntimeError("oracle parser exploded")

    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", SuccessfulRunner)
    monkeypatch.setattr(cli, "L1Oracle", FailingL1Oracle)
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["reason"] == "oracle_execution_error"
    assert verdict["metric_context"]["seed_outcome"] == "not_accountable"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    assert verdict["checkpoints"] == ["after-segment-0"]
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "failed"
    assert record["phase_errors"] == [
        {
            "phase": "oracle-evaluation",
            "kind": "oracle",
            "reason": "oracle_execution_error",
            "message": "RuntimeError: oracle parser exploded",
        }
    ]
    assert record["evidence_refs"]["checkpoints"] == [
        str(flow.checkpoints[0].directory)
    ]
    assert record["evidence_refs"]["journey_results"] == [
        str(flow.journey_results[0].result_path)
    ]


def test_unexpected_journey_exception_becomes_an_interrupted_attempt(
    tmp_path, monkeypatch
):
    class BrokenJourneyRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            raise ValueError("invalid segment boundary")

    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", BrokenJourneyRunner)
    artifact_dir = tmp_path / "run" / "artifacts"

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["reason"] == "journey_execution_error"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "interrupted"
    assert record["phase_errors"] == [
        {
            "phase": "journey-execution",
            "kind": "journey",
            "reason": "journey_execution_error",
            "message": "ValueError: invalid segment boundary",
        }
    ]


def test_verdict_output_failure_finalizes_record_without_oracle_accounting(
    tmp_path, monkeypatch
):
    flow = _flow(tmp_path)
    artifact_dir = tmp_path / "run" / "artifacts"

    class OutputBlockingRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            (artifact_dir.parent / "verdict.json").mkdir()
            return flow

    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", OutputBlockingRunner)

    verdict = cli.run(
        _spec(tmp_path, l3_spec=""),
        device="emulator-5554",
        artifact_dir=artifact_dir,
        workdir=tmp_path,
        preflight_command_runner=FakePreflightRunner(_passing_preflight_responses()),
    )

    assert verdict["execution"]["reason"] == "output_finalization_error"
    assert verdict["metric_context"]["seed_outcome"] == "not_accountable"
    assert verdict["l1"] is verdict["l2"] is verdict["l3"] is None
    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "failed"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["phase_errors"][0]["phase"] == "verdict-output"
    assert record["phase_errors"][0]["reason"] == "output_finalization_error"
    assert "ArtifactStorageError" in record["phase_errors"][0]["message"]
    assert "verdict.json" in record["phase_errors"][0]["message"]
    assert "verdict" not in record["evidence_refs"]
    assert record["evidence_refs"]["checkpoints"] == [
        str(flow.checkpoints[0].directory)
    ]


def test_record_finalization_failure_leaves_original_nonterminal_record(
    tmp_path, monkeypatch
):
    flow = _flow(tmp_path)

    class SuccessfulRunner:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return flow

    def fail_replace(source, target):
        raise OSError("atomic replace denied")

    monkeypatch.setattr(cli, "DeviceController", FakeDeviceController)
    monkeypatch.setattr(cli, "JourneySegmentRunner", SuccessfulRunner)
    monkeypatch.setattr(execution_record_module.os, "replace", fail_replace)
    artifact_dir = tmp_path / "run" / "artifacts"

    with pytest.raises(ExecutionRecordStorageError, match="atomic replace denied"):
        cli.run(
            _spec(tmp_path, l3_spec=""),
            device="emulator-5554",
            artifact_dir=artifact_dir,
            workdir=tmp_path,
            preflight_command_runner=FakePreflightRunner(
                _passing_preflight_responses()
            ),
        )

    record = json.loads(
        (artifact_dir.parent / "execution-record.json").read_text(encoding="utf-8")
    )
    assert record["lifecycle_state"] == "in_progress"
    assert record["finished_at"] is None
    assert record["process_outcome"] is None
    assert (artifact_dir.parent / "verdict.json").is_file()
    assert not list(artifact_dir.parent.glob(".execution-record.*.tmp"))


def test_main_returns_nonzero_when_execution_record_storage_fails(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(cli, "load_run_spec", lambda path: object())
    monkeypatch.setattr(
        cli,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ExecutionRecordStorageError("record fsync failed")
        ),
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
    assert "ExecutionRecord storage failed: record fsync failed" in capsys.readouterr().err


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
