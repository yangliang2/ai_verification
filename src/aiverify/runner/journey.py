"""Journey conversion and segment-boundary orchestration."""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aiverify.runner.codex_backend import (
    CodexCliError,
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
    """Result of executing segmented Journey instructions.

    timings: per-phase wall-clock durations in execution order. Each entry has
    "phase" (segment/checkpoint/event name), "kind" ("journey" | "checkpoint" |
    "system_event"), "seconds", and for system events the "event" name.
    """

    journey_results: list[JourneyExecutionResult]
    checkpoints: list[EvidenceCheckpoint]
    injected_events: list[SystemEventSpec] = field(default_factory=list)
    timings: list[dict[str, Any]] = field(default_factory=list)


class JourneyExecutionInterrupted(RuntimeError):
    """A Journey cannot continue without contaminating benchmark evidence."""

    def __init__(
        self,
        *,
        reason: str,
        message: str,
        journey_results: list[JourneyExecutionResult],
        checkpoints: list[EvidenceCheckpoint],
        injected_events: list[SystemEventSpec],
        timings: list[dict[str, Any]],
        backend_diagnostics: list[dict[str, str | list[str] | None]] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.flow = JourneySegmentFlow(
            journey_results=list(journey_results),
            checkpoints=list(checkpoints),
            injected_events=list(injected_events),
            timings=list(timings),
        )
        self.backend_diagnostics = list(backend_diagnostics or [])


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
        instruction_prefix: str = "",
    ) -> JourneySegmentFlow:
        """Run all segments and capture checkpoints around boundary events.

        instruction_prefix is prepended to each segment's Journey XML — used to give
        the backend agent its driver guidance (tools, device serial, output contract).
        """
        journey_results: list[JourneyExecutionResult] = []
        checkpoints: list[EvidenceCheckpoint] = []
        injected_events: list[SystemEventSpec] = []
        timings: list[dict[str, Any]] = []

        def _timed(phase: str, kind: str, fn, **extra: Any):
            start = time.monotonic()
            entry: dict[str, Any] = {
                "phase": phase,
                "kind": kind,
            }
            entry.update(extra)
            try:
                value = fn()
            except Exception:
                entry["status"] = "failed"
                entry["seconds"] = round(time.monotonic() - start, 3)
                timings.append(entry)
                raise
            entry["seconds"] = round(time.monotonic() - start, 3)
            timings.append(entry)
            return value

        def _interrupt(reason: str, exc: Exception) -> JourneyExecutionInterrupted:
            backend_diagnostics: list[dict[str, str | list[str] | None]] = []
            if isinstance(exc, CodexCliError):
                backend_diagnostics.append(
                    {
                        "result": str(exc.result_path) if exc.result_path is not None else None,
                        "events": str(exc.events_path) if exc.events_path is not None else None,
                        "command": exc.command,
                    }
                )
            return JourneyExecutionInterrupted(
                reason=reason,
                message=f"{type(exc).__name__}: {exc}",
                journey_results=journey_results,
                checkpoints=checkpoints,
                injected_events=injected_events,
                timings=timings,
                backend_diagnostics=backend_diagnostics,
            )

        for index, segment in enumerate(scenario_to_segments(scenario)):
            journey_xml = instruction_prefix + segment_to_journey_xml(segment)
            segment_dir = artifact_dir / segment.id
            try:
                result = _timed(
                    segment.id,
                    "journey",
                    lambda: self.backend.execute(
                        JourneyExecutionRequest(
                            journey_instructions=journey_xml,
                            workdir=workdir,
                            artifact_dir=segment_dir,
                            output_schema=output_schema,
                        )
                    ),
                )
            except Exception as exc:
                raise _interrupt("journey_backend_error", exc) from exc
            journey_results.append(result)
            try:
                checkpoints.append(
                    _timed(
                        f"after-segment-{index}",
                        "checkpoint",
                        lambda: self.checkpoint_collector.capture_checkpoint(
                            name=f"after-segment-{index}",
                            output_dir=artifact_dir,
                            device=device,
                        ),
                    )
                )
            except Exception as exc:
                raise _interrupt("checkpoint_capture_error", exc) from exc

            reported_actions = result.data.get("results", [])
            if len(reported_actions) != len(segment.actions):
                raise JourneyExecutionInterrupted(
                    reason="journey_action_incomplete",
                    message=(
                        f"Journey segment {segment.id} reported {len(reported_actions)} "
                        f"of {len(segment.actions)} requested action result(s)"
                    ),
                    journey_results=journey_results,
                    checkpoints=checkpoints,
                    injected_events=injected_events,
                    timings=timings,
                )

            reported_action_names = [item.get("action") for item in reported_actions]
            if reported_action_names != segment.actions:
                raise JourneyExecutionInterrupted(
                    reason="journey_action_incomplete",
                    message=(
                        f"Journey segment {segment.id} reported action names that do not "
                        "match the requested action order"
                    ),
                    journey_results=journey_results,
                    checkpoints=checkpoints,
                    injected_events=injected_events,
                    timings=timings,
                )

            failed_actions = [
                item
                for item in reported_actions
                if item.get("status") in {"FAILED", "SKIPPED"}
            ]
            if failed_actions:
                statuses = ", ".join(item["status"] for item in failed_actions)
                raise JourneyExecutionInterrupted(
                    reason="journey_action_failed",
                    message=(
                        f"Journey segment {segment.id} reported non-passing action "
                        f"status(es): {statuses}"
                    ),
                    journey_results=journey_results,
                    checkpoints=checkpoints,
                    injected_events=injected_events,
                    timings=timings,
                )

            if segment.system_event_after is not None:
                event = segment.system_event_after
                try:
                    _timed(
                        f"event-{index}",
                        "system_event",
                        lambda: self.system_event_injector.inject(event),
                        event=event.event,
                    )
                except Exception as exc:
                    raise _interrupt("system_event_injection_error", exc) from exc
                injected_events.append(event)
                try:
                    checkpoints.append(
                        _timed(
                            f"after-event-{index}",
                            "checkpoint",
                            lambda: self.checkpoint_collector.capture_checkpoint(
                                name=f"after-event-{index}",
                                output_dir=artifact_dir,
                                device=device,
                            ),
                        )
                    )
                except Exception as exc:
                    raise _interrupt("checkpoint_capture_error", exc) from exc

        return JourneySegmentFlow(
            journey_results=journey_results,
            checkpoints=checkpoints,
            injected_events=injected_events,
            timings=timings,
        )
