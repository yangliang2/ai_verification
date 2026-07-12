from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

from aiverify.runner.codex_backend import CodexCliError, JourneyExecutionRequest, JourneyExecutionResult
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.journey import (
    JourneyExecutionInterrupted,
    JourneySegmentRunner,
    scenario_to_segments,
    segment_to_journey_xml,
)
from aiverify.runner.run_spec import ScenarioSpec, SystemEventSpec


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


class FakeBackend:
    def __init__(self) -> None:
        self.requests: list[JourneyExecutionRequest] = []

    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        self.requests.append(request)
        request.artifact_dir.mkdir(parents=True, exist_ok=True)
        result_path = request.artifact_dir / "result.json"
        events_path = request.artifact_dir / "events.jsonl"
        actions = [
            html.unescape(action)
            for action in re.findall(r"<action>(.*?)</action>", request.journey_instructions)
        ]
        results = [
            {
                "action": action,
                "status": "PASSED",
                "commands": [],
                "comment": "completed",
            }
            for action in actions
        ]
        result_path.write_text(
            str({"journey": "x", "results": results}), encoding="utf-8"
        )
        events_path.write_text("", encoding="utf-8")
        return JourneyExecutionResult(
            data={"journey": "x", "results": results},
            result_path=result_path,
            events_path=events_path,
            command=["codex"],
        )


class FailedActionBackend(FakeBackend):
    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        result = super().execute(request)
        return JourneyExecutionResult(
            data={
                "journey": "x",
                "results": [
                    {
                        "action": "Open search",
                        "status": "FAILED",
                        "commands": [],
                        "comment": "target surface was unavailable",
                    }
                ],
            },
            result_path=result.result_path,
            events_path=result.events_path,
            command=result.command,
        )


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
        result.data["results"][0]["action"] = "Open an unrelated screen"
        return result


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
    )

    assert len(backend.requests) == 2
    assert [event.event for event in injector.events] == ["rotate"]
    assert collector.names == ["after-segment-0", "after-event-0", "after-segment-1"]
    assert len(flow.checkpoints) == 3


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

    assert raised.value.reason == "system_event_injection_error"
    assert [checkpoint.name for checkpoint in raised.value.flow.checkpoints] == [
        "after-segment-0"
    ]
    assert raised.value.flow.injected_events == []
