from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path

import pytest

from aiverify.runner.codex_backend import CodexCliError, JourneyExecutionRequest, JourneyExecutionResult
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.evidence import AndroidEvidenceCollector, EvidenceCheckpoint
from aiverify.runner.journey import (
    JourneyExecutionInterrupted,
    JourneySegmentRunner,
    scenario_to_segments,
    segment_to_journey_xml,
)
from aiverify.runner.run_spec import ScenarioSpec, SystemEventSpec
from aiverify.runner.system_events import SystemEventObservation


def test_scenario_to_segments_splits_after_event_step() -> None:
    scenario = ScenarioSpec(
        id="smoke",
        user_actions=["Open search", "Type text", "Verify text"],
        system_events=[SystemEventSpec(step_index=1, event="rotate")],
    )

    segments = scenario_to_segments(scenario)

    assert [s.actions for s in segments] == [
        ["Open search", "Type text"],
        ["Verify text"],
    ]
    assert segments[0].system_event_after is not None
    assert segments[0].system_event_after.event == "rotate"


def test_scenario_to_segments_rejects_out_of_range_event() -> None:
    scenario = ScenarioSpec(
        id="bad",
        user_actions=["one"],
        system_events=[SystemEventSpec(step_index=1, event="rotate")],
    )

    with pytest.raises(ValueError, match="exceeds"):
        scenario_to_segments(scenario)


def test_segment_to_journey_xml_escapes_actions() -> None:
    xml = segment_to_journey_xml(
        scenario_to_segments(
            ScenarioSpec(id="smoke", user_actions=["Tap A & B"])
        )[0]
    )

    assert "<journey" in xml
    assert "Tap A &amp; B" in xml


def test_segment_to_journey_xml_assigns_stable_action_ids() -> None:
    xml = segment_to_journey_xml(
        scenario_to_segments(
            ScenarioSpec(id="smoke", user_actions=["Open search", "Type text"])
        )[0]
    )

    assert '<action id="action-1">Open search</action>' in xml
    assert '<action id="action-2">Type text</action>' in xml


class FakeBackend:
    def __init__(self) -> None:
        self.requests: list[JourneyExecutionRequest] = []

    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        self.requests.append(request)
        request.artifact_dir.mkdir(parents=True, exist_ok=True)
        result_path = request.artifact_dir / "result.json"
        events_path = request.artifact_dir / "events.jsonl"
        actions = [
            (action_id, html.unescape(action))
            for action_id, action in re.findall(
                r'<action id="([^"]+)">(.*?)</action>',
                request.journey_instructions,
            )
        ]
        results = [
            {
                "action_id": action_id,
                "status": "PASSED",
                "commands": [],
                "comment": "completed",
            }
            for action_id, action in actions
        ]
        journey = re.search(
            r'<journey name="([^"]+)">', request.journey_instructions
        ).group(1)
        data = {"journey": journey, "results": results}
        result_path.write_text(
            json.dumps(data), encoding="utf-8"
        )
        events_path.write_text("", encoding="utf-8")
        return JourneyExecutionResult(
            data=data,
            result_path=result_path,
            events_path=events_path,
            command=["codex"],
        )


class FailedActionBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0]["status"] = "FAILED"
        result.data["results"][0]["comment"] = "target surface was unavailable"
        return result


class RaisingBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        raise RuntimeError("Codex CLI exited unexpectedly")


class ArtifactRaisingBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        events_path = request.artifact_dir / "codex-events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text("partial event stream", encoding="utf-8")
        raise CodexCliError(
            "Codex CLI exited unexpectedly",
            events_path=events_path,
            command=["codex", "exec"],
        )


class SkippedActionBackend(FailedActionBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0]["status"] = "SKIPPED"
        return result


class FailSecondSegmentBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        self.calls += 1
        result = super().execute(request)
        if self.calls == 2:
            result.data["results"][0]["status"] = "FAILED"
        return result


class MissingActionBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"] = result.data["results"][:-1]
        return result


class WrongActionBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0]["action_id"] = "action-99"
        return result


class UnknownStatusBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0]["status"] = "OBSERVED"
        return result


class MissingActionIdBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0].pop("action_id")
        return result


class UnrelatedActionTextBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0]["action"] = "Delete the account"
        return result


class DuplicateActionIdBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][1]["action_id"] = "action-1"
        return result


class ReorderedActionBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"].reverse()
        return result


class ContradictoryActionBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["results"][0]["action"] = "Type text"
        return result


class WrongJourneyBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        result.data["journey"] = "another-segment"
        return result


class StableActionIdBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        request.artifact_dir.mkdir(parents=True, exist_ok=True)
        result_path = request.artifact_dir / "codex-journey-result.json"
        events_path = request.artifact_dir / "codex-events.jsonl"
        data = {
            "journey": "search-card-segment-0",
            "results": [
                {
                    "action_id": "action-1",
                    "status": "PASSED",
                    "commands": ["android layout", "adb shell input tap 540 2232"],
                    "comment": "Search is selected and search_card is visible.",
                }
            ],
        }
        result_path.write_text(json.dumps(data), encoding="utf-8")
        events_path.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
        return JourneyExecutionResult(
            data=data,
            result_path=result_path,
            events_path=events_path,
            command=["codex"],
        )


class FakeCollector:
    def __init__(self) -> None:
        self.names: list[str] = []

    def capture_checkpoint(
        self,
        *,
        name: str,
        output_dir: Path,
        device: str | None = None,
        annotated: bool = True,
    ) -> EvidenceCheckpoint:
        self.names.append(name)
        directory = output_dir / name
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "x"
        path.write_text("", encoding="utf-8")
        return EvidenceCheckpoint(
            name=name,
            directory=directory,
            layout_path=path,
            screenshot_path=path,
            annotated_screenshot_path=path,
            logcat_path=path,
            commands_path=path,
        )


class FakeInjector:
    def __init__(self) -> None:
        self.events: list[SystemEventSpec] = []

    def inject(self, event: SystemEventSpec) -> None:
        self.events.append(event)


class ObservingInjector(FakeInjector):
    def inject(self, event: SystemEventSpec) -> SystemEventObservation:
        self.events.append(event)
        return SystemEventObservation(
            event=event.event,
            requested={
                "package": "org.example",
                "permission": "android.permission.ACCESS_FINE_LOCATION",
            },
            observed={"granted": False, "flags": ["USER_SET"]},
        )


class RaisingCollector(FakeCollector):
    def capture_checkpoint(
        self,
        *,
        name: str,
        output_dir: Path,
        device: str | None = None,
        annotated: bool = True,
    ) -> EvidenceCheckpoint:
        raise RuntimeError("Android layout timed out")


class RaisingInjector(FakeInjector):
    def inject(self, event: SystemEventSpec) -> None:
        raise RuntimeError("Unable to rotate device")


class TimingOutInjector(FakeInjector):
    def inject(self, event: SystemEventSpec) -> None:
        raise subprocess.TimeoutExpired(
            ["adb", "shell", "settings", "put", "system", "user_rotation", "1"],
            30,
        )


class HistoricalAnrCaptureRunner(CommandRunner):
    """Reproduce defect-1 attempt-2's rc=0/empty-layout failure shape."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
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


def test_journey_segment_runner_orders_segments_events_and_checkpoints(tmp_path: Path) -> None:
    backend = FakeBackend()
    collector = FakeCollector()
    injector = FakeInjector()
    runner = JourneySegmentRunner(
        backend=backend,
        checkpoint_collector=collector,
        system_event_injector=injector,
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    scenario = ScenarioSpec(
        id="smoke",
        user_actions=["Open search", "Type text", "Verify text"],
        system_events=[SystemEventSpec(step_index=1, event="rotate")],
    )

    flow = runner.run(
        scenario=scenario,
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=schema,
        device="emulator-5554",
        model="gpt-5.1-codex",
    )

    assert len(backend.requests) == 2
    assert [request.model for request in backend.requests] == [
        "gpt-5.1-codex",
        "gpt-5.1-codex",
    ]
    assert [event.event for event in injector.events] == ["rotate"]
    assert collector.names == ["after-segment-0", "after-event-0", "after-segment-1"]
    assert len(flow.checkpoints) == 3


def test_journey_persists_permission_event_observation(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=FakeBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=ObservingInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    flow = runner.run(
        scenario=ScenarioSpec(
            id="permission",
            user_actions=["Deny the permission dialog"],
            system_events=[
                SystemEventSpec(step_index=0, event="observe_permission")
            ],
        ),
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=schema,
    )

    assert len(flow.event_observations) == 1
    artifact = Path(flow.event_observations[0]["artifact"])
    assert artifact.name == "system-event-0.json"
    assert json.loads(artifact.read_text(encoding="utf-8")) == {
        "event": "observe_permission",
        "requested": {
            "package": "org.example",
            "permission": "android.permission.ACCESS_FINE_LOCATION",
        },
        "observed": {"granted": False, "flags": ["USER_SET"]},
    }


def test_journey_segment_runner_times_every_phase(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=FakeBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    scenario = ScenarioSpec(
        id="smoke",
        user_actions=["Open search", "Type text", "Verify text"],
        system_events=[SystemEventSpec(step_index=1, event="process_death")],
    )

    flow = runner.run(
        scenario=scenario,
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=schema,
        device="emulator-5554",
    )

    assert [(t["phase"], t["kind"]) for t in flow.timings] == [
        ("smoke-segment-0", "journey"),
        ("after-segment-0", "checkpoint"),
        ("event-0", "system_event"),
        ("after-event-0", "checkpoint"),
        ("smoke-segment-1", "journey"),
        ("after-segment-1", "checkpoint"),
    ]
    assert all(isinstance(t["seconds"], float) and t["seconds"] >= 0 for t in flow.timings)
    event_entry = next(t for t in flow.timings if t["kind"] == "system_event")
    assert event_entry["event"] == "process_death"


def test_journey_segment_runner_prepends_instruction_prefix(tmp_path: Path) -> None:
    backend = FakeBackend()
    runner = JourneySegmentRunner(
        backend=backend,
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    runner.run(
        scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=schema,
        device="emulator-5554",
        instruction_prefix="DRIVER GUIDANCE HERE\n",
    )

    instructions = backend.requests[0].journey_instructions
    assert instructions.startswith("DRIVER GUIDANCE HERE\n")
    assert "<journey" in instructions


def test_failed_journey_action_stops_before_event_and_keeps_checkpoint(tmp_path: Path) -> None:
    collector = FakeCollector()
    injector = FakeInjector()
    runner = JourneySegmentRunner(
        backend=FailedActionBackend(),
        checkpoint_collector=collector,
        system_event_injector=injector,
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")
    scenario = ScenarioSpec(
        id="smoke",
        user_actions=["Open search"],
        system_events=[SystemEventSpec(step_index=0, event="rotate")],
    )

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=scenario,
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
            device="emulator-5554",
        )

    assert raised.value.reason == "journey_action_failed"
    assert [result.data["results"][0]["status"] for result in raised.value.flow.journey_results] == [
        "FAILED"
    ]
    assert collector.names == ["after-segment-0"]
    assert injector.events == []


def test_skipped_journey_action_is_non_accountable(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=SkippedActionBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_action_failed"
    assert raised.value.flow.journey_results[0].data["results"][0]["status"] == "SKIPPED"


def test_missing_action_result_is_non_accountable(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=MissingActionBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_action_incomplete"


def test_mismatched_action_result_is_non_accountable(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=WrongActionBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_action_incomplete"


def test_stable_action_id_restores_exact_requested_action(
    tmp_path: Path,
) -> None:
    requested = (
        "Navigate from the main feed to the bottom Search tab and confirm the Search "
        "tab is selected with search_card visible."
    )
    runner = JourneySegmentRunner(
        backend=StableActionIdBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    flow = runner.run(
        scenario=ScenarioSpec(id="search-card", user_actions=[requested]),
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=schema,
    )

    result = flow.journey_results[0]
    assert result.data["results"] == [
        {
            "action_id": "action-1",
            "action": requested,
            "status": "PASSED",
            "commands": ["android layout", "adb shell input tap 540 2232"],
            "comment": "Search is selected and search_card is visible.",
        }
    ]
    assert result.result_path.name == "codex-journey-result.normalized.json"
    assert json.loads(result.result_path.read_text(encoding="utf-8")) == result.data
    assert Path(result.metadata["raw_result_path"]).name == "codex-journey-result.json"
    lineage_path = Path(result.metadata["action_lineage_path"])
    assert lineage_path.name == "codex-journey-action-lineage.json"
    assert json.loads(lineage_path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "journey": "search-card-segment-0",
        "raw_result": str(Path(result.metadata["raw_result_path"])),
        "events": str(result.events_path),
        "results": [
            {
                "action_id": "action-1",
                "requested_action": requested,
                "status": "PASSED",
            }
        ],
    }


def test_unknown_action_status_fails_closed_when_backend_bypasses_schema(
    tmp_path: Path,
) -> None:
    runner = JourneySegmentRunner(
        backend=UnknownStatusBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_action_incomplete"
    assert "invalid status" in str(raised.value)


@pytest.mark.parametrize(
    "backend",
    [
        MissingActionIdBackend(),
        UnrelatedActionTextBackend(),
        DuplicateActionIdBackend(),
        ReorderedActionBackend(),
        ContradictoryActionBackend(),
        WrongJourneyBackend(),
    ],
    ids=[
        "missing-id",
        "unrelated-action-text",
        "duplicated-id",
        "reordered-results",
        "contradictory-action-text",
        "wrong-journey",
    ],
)
def test_invalid_action_lineage_fails_closed(tmp_path: Path, backend: FakeBackend) -> None:
    runner = JourneySegmentRunner(
        backend=backend,
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(
                id="smoke", user_actions=["Open search", "Type text"]
            ),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_action_incomplete"
    assert not list((tmp_path / "artifacts").rglob("*normalized.json"))
    assert not list((tmp_path / "artifacts").rglob("*action-lineage.json"))


def test_multi_segment_interruption_keeps_completed_prior_boundary_evidence(tmp_path: Path) -> None:
    collector = FakeCollector()
    injector = FakeInjector()
    runner = JourneySegmentRunner(
        backend=FailSecondSegmentBackend(),
        checkpoint_collector=collector,
        system_event_injector=injector,
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(
                id="smoke",
                user_actions=["Open search", "Type text"],
                system_events=[SystemEventSpec(step_index=0, event="rotate")],
            ),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_action_failed"
    assert [checkpoint.name for checkpoint in raised.value.flow.checkpoints] == [
        "after-segment-0",
        "after-event-0",
        "after-segment-1",
    ]
    assert [event.event for event in raised.value.flow.injected_events] == ["rotate"]


def test_backend_failure_becomes_non_accountable_journey_interruption(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=RaisingBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "journey_backend_error"
    assert raised.value.flow.journey_results == []
    assert raised.value.flow.checkpoints == []
    assert raised.value.flow.timings[0]["phase"] == "smoke-segment-0"
    assert raised.value.flow.timings[0]["status"] == "failed"


def test_backend_failure_retains_codex_artifact_references(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=ArtifactRaisingBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.backend_diagnostics == [
        {
            "result": None,
            "events": str(tmp_path / "artifacts" / "smoke-segment-0" / "codex-events.jsonl"),
            "command": ["codex", "exec"],
        }
    ]


def test_checkpoint_failure_keeps_completed_journey_for_diagnostics(tmp_path: Path) -> None:
    runner = JourneySegmentRunner(
        backend=FakeBackend(),
        checkpoint_collector=RaisingCollector(),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="smoke", user_actions=["Open search"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "checkpoint_capture_error"
    assert len(raised.value.flow.journey_results) == 1
    assert raised.value.flow.checkpoints == []
    assert raised.value.flow.timings[-1]["status"] == "failed"


def test_anr_layout_failure_retains_bounded_checkpoint_diagnostics(tmp_path: Path) -> None:
    command_runner = HistoricalAnrCaptureRunner()
    runner = JourneySegmentRunner(
        backend=FakeBackend(),
        checkpoint_collector=AndroidEvidenceCollector(
            runner=command_runner,
            layout_attempts=2,
            layout_retry_sleep_seconds=0,
        ),
        system_event_injector=FakeInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(id="anr-defect-1", user_actions=["Trigger ANR"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
            device="emulator-5554",
        )

    assert raised.value.reason == "checkpoint_capture_error"
    assert raised.value.flow.journey_results[0].data["results"][0]["status"] == "PASSED"
    assert [checkpoint.name for checkpoint in raised.value.flow.checkpoints] == [
        "after-segment-0"
    ]
    checkpoint = raised.value.flow.checkpoints[0]
    manifest = json.loads(checkpoint.manifest_path.read_text(encoding="utf-8"))
    commands = json.loads(checkpoint.commands_path.read_text(encoding="utf-8"))

    assert manifest["status"] == "failed"
    assert manifest["failed_phase"] == "layout"
    assert manifest["artifact_exists"] == {
        "layout": False,
        "screen": True,
        "screen_annotated": True,
        "logcat": True,
        "commands": True,
    }
    assert [entry["phase"] for entry in commands] == [
        "layout",
        "layout",
        "screenshot",
        "annotated_screenshot",
        "logcat",
    ]
    assert checkpoint.logcat_path.read_text(encoding="utf-8") == (
        "ANR in org.wikipedia.dev\n"
    )


def test_system_event_failure_keeps_pre_event_checkpoint(tmp_path: Path) -> None:
    collector = FakeCollector()
    runner = JourneySegmentRunner(
        backend=FakeBackend(),
        checkpoint_collector=collector,
        system_event_injector=RaisingInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(
                id="smoke",
                user_actions=["Open search"],
                system_events=[SystemEventSpec(step_index=0, event="rotate")],
            ),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "system_event_error"
    assert [checkpoint.name for checkpoint in raised.value.flow.checkpoints] == [
        "after-segment-0"
    ]
    assert raised.value.flow.injected_events == []


def test_system_event_timeout_uses_canonical_reason_and_keeps_pre_event_evidence(
    tmp_path: Path,
) -> None:
    runner = JourneySegmentRunner(
        backend=FakeBackend(),
        checkpoint_collector=FakeCollector(),
        system_event_injector=TimingOutInjector(),
    )
    schema = tmp_path / "schema.json"
    schema.write_text("{}", encoding="utf-8")

    with pytest.raises(JourneyExecutionInterrupted) as raised:
        runner.run(
            scenario=ScenarioSpec(
                id="timeout",
                user_actions=["Open search"],
                system_events=[SystemEventSpec(step_index=0, event="rotate")],
            ),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=schema,
        )

    assert raised.value.reason == "system_event_error"
    assert [checkpoint.name for checkpoint in raised.value.flow.checkpoints] == [
        "after-segment-0"
    ]
    assert raised.value.flow.timings[-1]["status"] == "failed"
    assert "timed out after 30 seconds" in str(raised.value)
