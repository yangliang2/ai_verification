"""Journey conversion and segment-boundary orchestration."""

from __future__ import annotations

import html
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from aiverify.runner.codex_backend import (
    CodexCliError,
    JourneyExecutionRequest,
)
from aiverify.runner.evidence import EvidenceCaptureError, EvidenceCheckpoint
from aiverify.runner.execution_record import write_json_artifact
from aiverify.runner.journey_backend import (
    CODEX_CLI,
    DETERMINISTIC_ANDROID_V1,
    JourneyBackend,
    JourneyBackendSelectionError,
    JourneyExecutionResult,
    backend_id,
)
from aiverify.runner.run_spec import ScenarioSpec, SystemEventSpec


@dataclass(frozen=True)
class JourneySegment:
    """One Android CLI-supported Journey instruction segment."""

    id: str
    actions: list[str]
    system_event_after: SystemEventSpec | None = None
    start_index: int = 0


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
    system_event_evidence: list[Path] = field(default_factory=list)
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
        system_event_evidence: list[Path] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.flow = JourneySegmentFlow(
            journey_results=list(journey_results),
            checkpoints=list(checkpoints),
            injected_events=list(injected_events),
            system_event_evidence=list(system_event_evidence or []),
            timings=list(timings),
        )
        self.backend_diagnostics = list(backend_diagnostics or [])


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

    def inject(self, event: SystemEventSpec) -> dict[str, Any] | None:
        """Inject a system event."""


def _action_id(index: int) -> str:
    """Return the stable one-based ID for an action within one Journey segment."""
    return f"action-{index}"


def scenario_to_segments(scenario: ScenarioSpec) -> list[JourneySegment]:
    """Split scenario actions into segments around system event boundaries.

    MVP semantics: step_index N means inject the event after executing
    user_actions[N]. A trailing event at ``step_index == len(user_actions)``
    is allowed so protocols can finish with a system boundary after the final
    user action; events beyond that boundary are rejected.
    """
    actions = scenario.user_actions
    if not actions:
        return [JourneySegment(id=f"{scenario.id}-segment-0", actions=[])]

    events = sorted(scenario.system_events, key=lambda e: e.step_index)
    for event in events:
        if event.step_index > len(actions):
            raise ValueError(
                f"system event step_index {event.step_index} exceeds user_actions length {len(actions)}"
            )

    segments: list[JourneySegment] = []
    start = 0
    for idx, event in enumerate(events):
        end = min(event.step_index + 1, len(actions))
        segment_actions = actions[start:end]
        segments.append(
            JourneySegment(
                id=f"{scenario.id}-segment-{idx}",
                actions=segment_actions,
                system_event_after=event,
                start_index=start,
            )
        )
        start = end

    if start < len(actions):
        segments.append(
            JourneySegment(
                id=f"{scenario.id}-segment-{len(segments)}",
                actions=actions[start:],
                start_index=start,
            )
        )

    return segments


def segment_to_journey_xml(segment: JourneySegment) -> str:
    """Render one segment as Journey XML understood by an agent."""
    actions = "\n".join(
        f'    <action id="{_action_id(index)}">{html.escape(action)}</action>'
        for index, action in enumerate(segment.actions, start=1)
    )
    return (
        f'<journey name="{html.escape(segment.id)}">\n'
        "  <description>Execute this segment exactly as written.</description>\n"
        "  <actions>\n"
        f"{actions}\n"
        "  </actions>\n"
        "</journey>\n"
    )


def _build_backend_request(
    backend: JourneyBackend,
    *,
    segment: JourneySegment,
    journey_instructions: str,
    workdir: Path,
    artifact_dir: Path,
    output_schema: Path,
    device: str | None,
    model: str | None,
) -> Any:
    """Build a backend-specific request while retaining legacy fake support."""
    builder = getattr(backend, "build_request", None)
    if callable(builder):
        if backend_id(backend) == DETERMINISTIC_ANDROID_V1:
            return builder(
                segment_id=segment.id,
                action_offset=segment.start_index,
                action_count=len(segment.actions),
                artifact_dir=artifact_dir,
                device=device,
            )
        return builder(
            segment=segment,
            journey_instructions=journey_instructions,
            workdir=workdir,
            artifact_dir=artifact_dir,
            output_schema=output_schema,
            device=device,
            model=model,
        )
    if backend_id(backend) != CODEX_CLI:
        raise JourneyBackendSelectionError(
            "selected non-Codex Journey backend has no request builder"
        )
    return JourneyExecutionRequest(
        journey_instructions=journey_instructions,
        workdir=workdir,
        artifact_dir=artifact_dir,
        output_schema=output_schema,
        model=model,
    )


def _action_lineage_results(
    normalized_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project normalized actions into the stable lineage contract."""
    results = []
    for item in normalized_actions:
        lineage = {
            "action_id": item["action_id"],
            "requested_action": item["action"],
            "status": item["status"],
        }
        if "plan_action_id" in item:
            lineage["plan_action_id"] = item["plan_action_id"]
        results.append(lineage)
    return results


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
        model: str | None = None,
    ) -> JourneySegmentFlow:
        """Run all segments and capture checkpoints around boundary events.

        instruction_prefix is prepended to each segment's Journey XML — used to give
        the backend agent its driver guidance (tools, device serial, output contract).
        """
        journey_results: list[JourneyExecutionResult] = []
        checkpoints: list[EvidenceCheckpoint] = []
        injected_events: list[SystemEventSpec] = []
        system_event_evidence: list[Path] = []
        timings: list[dict[str, Any]] = []
        selected_backend_id = backend_id(self.backend)

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

        def _interruption(
            reason: str,
            message: str,
            *,
            backend_diagnostics: list[
                dict[str, str | list[str] | None]
            ] | None = None,
        ) -> JourneyExecutionInterrupted:
            return JourneyExecutionInterrupted(
                reason=reason,
                message=message,
                journey_results=journey_results,
                checkpoints=checkpoints,
                injected_events=injected_events,
                timings=timings,
                backend_diagnostics=backend_diagnostics,
                system_event_evidence=system_event_evidence,
            )

        def _interrupt(reason: str, exc: Exception) -> JourneyExecutionInterrupted:
            if (
                isinstance(exc, EvidenceCaptureError)
                and exc.checkpoint is not None
                and exc.checkpoint not in checkpoints
            ):
                checkpoints.append(exc.checkpoint)
            backend_diagnostics: list[dict[str, str | list[str] | None]] = []
            if isinstance(exc, CodexCliError):
                backend_diagnostics.append(
                    {
                        "result": str(exc.result_path) if exc.result_path is not None else None,
                        "events": str(exc.events_path) if exc.events_path is not None else None,
                        "command": exc.command,
                    }
                )
            else:
                result_path = getattr(exc, "result_path", None)
                events_path = getattr(exc, "events_path", None)
                invocation_path = getattr(exc, "invocation_path", None)
                command = getattr(exc, "command", None)
                if (
                    result_path is not None
                    or events_path is not None
                    or invocation_path is not None
                    or command is not None
                ):
                    backend_diagnostics.append(
                        {
                            "result": str(result_path) if result_path is not None else None,
                            "events": str(events_path) if events_path is not None else None,
                            "invocation": (
                                str(invocation_path)
                                if invocation_path is not None
                                else None
                            ),
                            "command": command,
                        }
                    )
            return _interruption(
                reason,
                f"{type(exc).__name__}: {exc}",
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
                        _build_backend_request(
                            self.backend,
                            segment=segment,
                            journey_instructions=journey_xml,
                            workdir=workdir,
                            artifact_dir=segment_dir,
                            output_schema=output_schema,
                            device=device,
                            model=model,
                        )
                    ),
                )
            except Exception as exc:
                raise _interrupt("journey_backend_error", exc) from exc
            journey_results.append(result)
            if result.backend != selected_backend_id:
                raise _interruption(
                    "journey_backend_contract",
                    (
                        f"Journey result backend {result.backend!r} does not match "
                        f"selected backend {selected_backend_id!r}"
                    ),
                )
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
            if not isinstance(reported_actions, list):
                raise _interruption(
                    "journey_action_incomplete",
                    f"Journey segment {segment.id} reported a non-list results value",
                )
            if len(reported_actions) != len(segment.actions):
                raise _interruption(
                    "journey_action_incomplete",
                    (
                        f"Journey segment {segment.id} reported {len(reported_actions)} "
                        f"of {len(segment.actions)} requested action result(s)"
                    ),
                )

            expected_action_ids = [
                _action_id(action_index)
                for action_index in range(1, len(segment.actions) + 1)
            ]
            reported_action_ids = [item.get("action_id") for item in reported_actions]
            if reported_action_ids != expected_action_ids:
                raise _interruption(
                    "journey_action_incomplete",
                    (
                        f"Journey segment {segment.id} reported action IDs that do not "
                        "match the requested action order"
                    ),
                )

            if result.data.get("journey") != segment.id:
                raise _interruption(
                    "journey_action_incomplete",
                    (
                        f"Journey result {result.data.get('journey')!r} does not match "
                        f"requested segment {segment.id!r}"
                    ),
                )

            invalid_statuses = [
                item.get("status")
                for item in reported_actions
                if item.get("status") not in {"PASSED", "FAILED", "SKIPPED"}
            ]
            if invalid_statuses:
                raise _interruption(
                    "journey_action_incomplete",
                    (
                        f"Journey segment {segment.id} reported invalid status "
                        f"value(s): {', '.join(map(str, invalid_statuses))}"
                    ),
                )

            if any("action" in item for item in reported_actions):
                raise _interruption(
                    "journey_action_incomplete",
                    (
                        f"Journey segment {segment.id} reported action text outside "
                        "the stable action-ID contract"
                    ),
                )

            normalized_actions: list[dict[str, Any]] = []
            for requested_action, reported_action in zip(
                segment.actions, reported_actions, strict=True
            ):
                normalized_actions.append(
                    {
                        **reported_action,
                        "action": requested_action,
                    }
                )

            raw_result_path = result.raw_result_path or result.result_path
            raw_events_path = result.raw_events_path or result.events_path
            normalized_data = {**result.data, "results": normalized_actions}
            normalized_path = segment_dir / "journey-result.normalized.json"
            lineage_path = segment_dir / "journey-action-lineage.json"
            legacy_normalized_path = segment_dir / "codex-journey-result.normalized.json"
            legacy_lineage_path = segment_dir / "codex-journey-action-lineage.json"
            if raw_result_path.resolve() == normalized_path.resolve():
                raise _interruption(
                    "journey_backend_contract",
                    "backend raw result path collides with canonical normalized output",
                )
            try:
                write_json_artifact(normalized_path, normalized_data)
                write_json_artifact(
                    lineage_path,
                    {
                        "schema_version": 1,
                        "backend": selected_backend_id,
                        "journey": segment.id,
                        "raw_result": str(raw_result_path),
                        "events": str(raw_events_path),
                        "results": _action_lineage_results(normalized_actions),
                    },
                )
                # Codex-named normalized aliases remain the public paths for
                # existing callers.  The neutral files above remain the
                # runner-owned canonical artifacts for every backend.
                legacy_backend = selected_backend_id == CODEX_CLI
                if selected_backend_id == CODEX_CLI:
                    write_json_artifact(legacy_normalized_path, normalized_data)
                    write_json_artifact(
                        legacy_lineage_path,
                        {
                            "schema_version": 1,
                            "journey": segment.id,
                            "raw_result": str(raw_result_path),
                            "events": str(raw_events_path),
                            "results": _action_lineage_results(normalized_actions),
                        },
                    )
            except Exception as exc:
                raise _interrupt("journey_evidence_error", exc) from exc
            public_result_path = (
                legacy_normalized_path if legacy_backend else normalized_path
            )
            public_lineage_path = legacy_lineage_path if legacy_backend else lineage_path
            result = replace(
                result,
                data=normalized_data,
                result_path=public_result_path,
                raw_result_path=raw_result_path,
                raw_events_path=raw_events_path,
                normalized_result_path=normalized_path,
                action_lineage_path=lineage_path,
                metadata={
                    **result.metadata,
                    "backend": selected_backend_id,
                    "raw_result_path": str(raw_result_path),
                    "raw_events_path": str(raw_events_path),
                    "normalized_result_path": str(normalized_path),
                    "action_lineage_path": str(public_lineage_path),
                    "canonical_action_lineage_path": str(lineage_path),
                    **(
                        {
                            "legacy_normalized_result_path": str(
                                legacy_normalized_path
                            ),
                            "legacy_action_lineage_path": str(legacy_lineage_path),
                            "public_action_lineage_path": str(public_lineage_path),
                        }
                        if legacy_backend
                        else {}
                    ),
                },
            )
            journey_results[-1] = result

            failed_actions = [
                item
                for item in reported_actions
                if item.get("status") in {"FAILED", "SKIPPED"}
            ]
            if failed_actions:
                statuses = ", ".join(item["status"] for item in failed_actions)
                raise _interruption(
                    "journey_action_failed",
                    (
                        f"Journey segment {segment.id} reported non-passing action "
                        f"status(es): {statuses}"
                    ),
                )

            if segment.system_event_after is not None:
                event = segment.system_event_after
                try:
                    event_details = _timed(
                        f"event-{index}",
                        "system_event",
                        lambda: self.system_event_injector.inject(event),
                        event=event.event,
                    )
                except Exception as exc:
                    raise _interrupt("system_event_error", exc) from exc
                injected_events.append(event)
                try:
                    if event_details is not None and not isinstance(event_details, dict):
                        raise TypeError("system event evidence must be a mapping")
                    event_path = artifact_dir / f"system-event-{index}" / "event.json"
                    event_path.parent.mkdir(parents=True, exist_ok=False)
                    write_json_artifact(
                        event_path,
                        {
                            "schema_version": 1,
                            "event": event.event,
                            "args": event.args,
                            "status": "passed",
                            "evidence": event_details or {},
                        },
                    )
                    system_event_evidence.append(event_path)
                except Exception as exc:
                    raise _interrupt("system_event_error", exc) from exc
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
            system_event_evidence=system_event_evidence,
            timings=timings,
        )
