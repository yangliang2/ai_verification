from __future__ import annotations

from pathlib import Path

import pytest

from aiverify.runner.codex_backend import JourneyExecutionRequest, JourneyExecutionResult
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.journey import (
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
        result_path.write_text('{"journey":"x","results":[]}', encoding="utf-8")
        events_path.write_text("", encoding="utf-8")
        return JourneyExecutionResult(
            data={"journey": "x", "results": []},
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
