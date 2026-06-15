"""Journey conversion and segment-boundary orchestration."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from aiverify.runner.codex_backend import (
    JourneyExecutionRequest,
    JourneyExecutionResult,
)
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.run_spec import ScenarioSpec, SystemEventSpec


@dataclass(frozen=True)
class JourneySegment:
    """One Android CLI-supported Journey instruction segment."""

    id: str
    actions: list[str]
    system_event_after: SystemEventSpec | None = None


@dataclass(frozen=True)
class JourneySegmentFlow:
    """Result of executing segmented Journey instructions."""

    journey_results: list[JourneyExecutionResult]
    checkpoints: list[EvidenceCheckpoint]
    injected_events: list[SystemEventSpec] = field(default_factory=list)


class JourneyBackend(Protocol):
    """Backend capable of executing one Journey segment."""

    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        """Execute one Journey segment."""


class CheckpointCollector(Protocol):
    """Collector capable of capturing named evidence checkpoints."""

    def capture_checkpoint(
        self,
        *,
        name: str,
        output_dir: Path,
        device: str | None = None,
        annotated: bool = True,
    ) -> EvidenceCheckpoint:
        """Capture one checkpoint."""


class SystemEventInjector(Protocol):
    """Injector for system events at Journey Segment Boundaries."""

    def inject(self, event: SystemEventSpec) -> None:
        """Inject a system event."""


def scenario_to_segments(scenario: ScenarioSpec) -> list[JourneySegment]:
    """Split scenario actions into segments around system event boundaries.

    MVP semantics: step_index N means inject the event after executing
    user_actions[N]. Events with step_index beyond the last action are rejected.
    """
    actions = scenario.user_actions
    if not actions:
        return [JourneySegment(id=f"{scenario.id}-segment-0", actions=[])]

    events = sorted(scenario.system_events, key=lambda e: e.step_index)
    for event in events:
        if event.step_index >= len(actions):
            raise ValueError(
                f"system event step_index {event.step_index} exceeds user_actions length {len(actions)}"
            )

    segments: list[JourneySegment] = []
    start = 0
    for idx, event in enumerate(events):
        end = event.step_index + 1
        segment_actions = actions[start:end]
        segments.append(
            JourneySegment(
                id=f"{scenario.id}-segment-{idx}",
                actions=segment_actions,
                system_event_after=event,
            )
        )
        start = end

    if start < len(actions):
        segments.append(
            JourneySegment(
                id=f"{scenario.id}-segment-{len(segments)}",
                actions=actions[start:],
            )
        )

    return segments


def segment_to_journey_xml(segment: JourneySegment) -> str:
    """Render one segment as Journey XML understood by an agent."""
    actions = "\n".join(
        f"    <action>{html.escape(action)}</action>" for action in segment.actions
    )
    return (
        f'<journey name="{html.escape(segment.id)}">\n'
        "  <description>Execute this segment exactly as written.</description>\n"
        "  <actions>\n"
        f"{actions}\n"
        "  </actions>\n"
        "</journey>\n"
    )


class JourneySegmentRunner:
    """Execute Journey segments, checkpoints, and boundary events in order."""

    def __init__(
        self,
        *,
        backend: JourneyBackend,
        checkpoint_collector: CheckpointCollector,
        system_event_injector: SystemEventInjector,
    ) -> None:
        self.backend = backend
        self.checkpoint_collector = checkpoint_collector
        self.system_event_injector = system_event_injector

    def run(
        self,
        *,
        scenario: ScenarioSpec,
        workdir: Path,
        artifact_dir: Path,
        output_schema: Path,
        device: str | None = None,
    ) -> JourneySegmentFlow:
        """Run all segments and capture checkpoints around boundary events."""
        journey_results: list[JourneyExecutionResult] = []
        checkpoints: list[EvidenceCheckpoint] = []
        injected_events: list[SystemEventSpec] = []

        for index, segment in enumerate(scenario_to_segments(scenario)):
            journey_xml = segment_to_journey_xml(segment)
            segment_dir = artifact_dir / segment.id
            result = self.backend.execute(
                JourneyExecutionRequest(
                    journey_instructions=journey_xml,
                    workdir=workdir,
                    artifact_dir=segment_dir,
                    output_schema=output_schema,
                )
            )
            journey_results.append(result)
            checkpoints.append(
                self.checkpoint_collector.capture_checkpoint(
                    name=f"after-segment-{index}",
                    output_dir=artifact_dir,
                    device=device,
                )
            )

            if segment.system_event_after is not None:
                self.system_event_injector.inject(segment.system_event_after)
                injected_events.append(segment.system_event_after)
                checkpoints.append(
                    self.checkpoint_collector.capture_checkpoint(
                        name=f"after-event-{index}",
                        output_dir=artifact_dir,
                        device=device,
                    )
                )

        return JourneySegmentFlow(
            journey_results=journey_results,
            checkpoints=checkpoints,
            injected_events=injected_events,
        )
