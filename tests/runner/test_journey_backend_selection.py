from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.runner import cli
from aiverify.runner.admission import (
    PlannedRunnerOptions,
    ProductionSeamAdmissionError,
    admit_production_seam,
    verify_admitted_receipt,
)
from aiverify.runner.codex_backend import JourneyExecutionResult
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.evidence import EvidenceCheckpoint
from aiverify.runner.journey import JourneyExecutionInterrupted, JourneySegmentRunner
from aiverify.runner.journey_backend import (
    CODEX_CLI,
    DEFAULT_JOURNEY_BACKEND,
    DETERMINISTIC_ANDROID_V1,
    SUPPORTED_JOURNEY_BACKENDS,
    JourneyBackendSelectionError,
    JourneyDriverSelection,
    create_journey_backend,
)
from aiverify.runner.run_spec import RunSpec, ScenarioSpec, load_run_spec


class GitOnlyRunner(CommandRunner):
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
        self.calls.append(list(args))
        if Path(args[0]).name != "git":
            raise AssertionError(f"non-git command reached admission: {args}")
        process = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandResult(
            args=list(args),
            stdout=process.stdout,
            stderr=process.stderr,
            returncode=process.returncode,
        )


def _fixture(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Journey backend test"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "journey@example.invalid"],
        cwd=repository,
        check=True,
    )
    (repository / "README.md").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repository, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repository, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/project.git"],
        cwd=repository,
        check=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    source = tmp_path / "run-spec.yaml"
    source.write_text(
        "host_project:\n"
        "  root: ${PROJECT_SOURCE}\n"
        "  origin: https://example.invalid/project.git\n"
        f"  commit: {commit}\n"
        "apk_glob: build/outputs/apk/**/*.apk\n"
        "package: org.example.project\n"
        "activity: org.example.project.MainActivity\n"
        "scenario:\n"
        "  id: selection-smoke\n"
        "  user_actions:\n"
        "    - wait for resource id oneButton\n",
        encoding="utf-8",
    )
    spec = load_run_spec(source, environ={"PROJECT_SOURCE": str(repository)})
    binaries: dict[str, Path] = {}
    for name in ("android", "adb", "codex"):
        path = tmp_path / "bin" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        binaries[name] = path
    options = PlannedRunnerOptions(
        device="emulator-5554",
        workdir=repository,
        artifact_dir=tmp_path / "run" / "artifacts",
        android_bin=str(binaries["android"]),
        adb_bin=str(binaries["adb"]),
        codex_bin=str(binaries["codex"]),
    )
    return spec, options, binaries


def _write_strict_wait_plan(spec, path: Path) -> None:
    run_spec_bytes = spec.source_path.read_bytes()
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_kind": "deterministic_driver_plan",
                "family_id": "selection-test",
                "family_version": "v1",
                "lane_id": "selection-smoke-lane",
                "plan_id": "selection-smoke-driver-plan",
                "run_spec_path": "run-spec.yaml",
                "run_spec_sha256": hashlib.sha256(run_spec_bytes).hexdigest(),
                "actions": [
                    {
                        "action_id": "action-01",
                        "kind": "wait_for_resource_id",
                        "resource_id": "oneButton",
                        "timeout_ms": 5000,
                        "observation_interval_ms": 350,
                        "settle_ms": 0,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_closed_backend_identities_and_legacy_default_are_explicit() -> None:
    assert DEFAULT_JOURNEY_BACKEND == CODEX_CLI
    assert SUPPORTED_JOURNEY_BACKENDS == {CODEX_CLI, DETERMINISTIC_ANDROID_V1}
    assert PlannedRunnerOptions(
        device="device",
        workdir=Path("/repo"),
        artifact_dir=Path("/run/artifacts"),
    ).backend == CODEX_CLI


def test_deterministic_selection_binds_plan_and_forbids_journey_model(
    tmp_path: Path,
) -> None:
    spec, options, _ = _fixture(tmp_path)
    plan = tmp_path / "driver-plan.json"
    _write_strict_wait_plan(spec, plan)
    selected = replace(
        options,
        backend=DETERMINISTIC_ANDROID_V1,
        driver_plan_path=plan,
    )

    result = admit_production_seam(spec, selected, command_runner=GitOnlyRunner())

    assert result.admitted is True
    policy = result.receipt["runner_policy"]
    assert policy["backend"] == DETERMINISTIC_ANDROID_V1
    assert policy["driver_plan"] == {
        "path": str(plan.resolve()),
        "sha256": hashlib.sha256(plan.read_bytes()).hexdigest(),
        "bytes": plan.stat().st_size,
    }
    assert policy["tools"]["model_selection"]["journey_driver"] == {
        "policy": "deterministic_android_v1_no_model",
        "requested_model": None,
        "model_override_present": False,
    }

    rejected = admit_production_seam(
        spec,
        replace(
            selected,
            requested_driver_model="must-not-reach-deterministic-driver",
        ),
        command_runner=GitOnlyRunner(),
    )
    assert rejected.admitted is False
    assert any("forbids a requested driver model" in reason for reason in rejected.reasons)


def test_codex_selection_rejects_a_driver_plan_before_external_work(
    tmp_path: Path,
) -> None:
    spec, options, _ = _fixture(tmp_path)
    plan = tmp_path / "driver-plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    runner = GitOnlyRunner()

    result = admit_production_seam(
        spec,
        replace(options, driver_plan_path=plan),
        command_runner=runner,
    )

    assert result.admitted is False
    assert "Codex CLI does not accept a Driver Plan" in result.reasons
    assert all(Path(call[0]).name == "git" for call in runner.calls)


def test_unknown_backend_is_rejected_without_resolving_backend_tools(
    tmp_path: Path,
) -> None:
    spec, options, _ = _fixture(tmp_path)
    result = admit_production_seam(
        spec,
        replace(options, backend="unknown-backend"),
        command_runner=GitOnlyRunner(),
    )

    assert result.admitted is False
    assert any("unsupported Journey Driver backend" in reason for reason in result.reasons)


def test_admitted_selection_receipt_rejects_driver_plan_drift(tmp_path: Path) -> None:
    spec, options, _ = _fixture(tmp_path)
    plan = tmp_path / "driver-plan.json"
    _write_strict_wait_plan(spec, plan)
    selected = replace(
        options,
        backend=DETERMINISTIC_ANDROID_V1,
        driver_plan_path=plan,
    )
    runner = GitOnlyRunner()
    admitted = admit_production_seam(spec, selected, command_runner=runner)
    plan.write_text('{"drifted": true}\n', encoding="utf-8")

    with pytest.raises(ProductionSeamAdmissionError, match="runner-option drift"):
        verify_admitted_receipt(
            admitted,
            spec,
            selected,
            command_runner=runner,
        )


class FakeSelectedBackend:
    def __init__(self, identity: str) -> None:
        self.backend_id = identity


class RequestlessDeterministicBackend:
    backend_id = DETERMINISTIC_ANDROID_V1

    def execute(self, request) -> JourneyExecutionResult:
        raise AssertionError("deterministic backend received a Codex request")


def test_selected_non_codex_backend_cannot_receive_legacy_codex_request(
    tmp_path: Path,
) -> None:
    runner = JourneySegmentRunner(
        backend=RequestlessDeterministicBackend(),
        checkpoint_collector=RecordingCheckpointCollector(),
        system_event_injector=lambda event: None,
    )

    with pytest.raises(
        JourneyExecutionInterrupted,
        match="selected non-Codex Journey backend has no request builder",
    ) as raised:
        runner.run(
            scenario=ScenarioSpec(id="deterministic-request-boundary", user_actions=["opaque"]),
            workdir=tmp_path,
            artifact_dir=tmp_path / "artifacts",
            output_schema=tmp_path / "schema.json",
        )

    assert raised.value.flow.journey_results == []


def test_factory_dispatches_only_to_the_explicit_selected_backend(
    tmp_path: Path,
) -> None:
    codex = FakeSelectedBackend(CODEX_CLI)
    deterministic = FakeSelectedBackend(DETERMINISTIC_ANDROID_V1)
    plan = tmp_path / "driver-plan.json"
    plan.write_text("{}\n", encoding="utf-8")

    assert create_journey_backend(
        JourneyDriverSelection(backend=CODEX_CLI),
        codex_factory=lambda: codex,
    ) is codex
    assert create_journey_backend(
        JourneyDriverSelection(
            backend=DETERMINISTIC_ANDROID_V1,
            driver_plan_path=plan,
        ),
        deterministic_backend=deterministic,
    ) is deterministic

    with pytest.raises(
        JourneyBackendSelectionError,
        match="identity contradicts runner policy",
    ):
        create_journey_backend(
            JourneyDriverSelection(backend=CODEX_CLI),
            codex_factory=lambda: deterministic,
        )


class RecordingCheckpointCollector:
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
        layout.write_text("[]", encoding="utf-8")
        screen = directory / "screen.png"
        screen.write_bytes(b"png")
        logcat = directory / "logcat.txt"
        logcat.write_text("", encoding="utf-8")
        commands = directory / "commands.json"
        commands.write_text("[]", encoding="utf-8")
        return EvidenceCheckpoint(
            name=name,
            directory=directory,
            layout_path=layout,
            screenshot_path=screen,
            annotated_screenshot_path=None,
            logcat_path=logcat,
            commands_path=commands,
        )


class RecordingCodexBackend:
    backend_id = CODEX_CLI

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
                    "status": "PASSED",
                    "commands": ["android layout"],
                    "comment": "dispatched",
                }
            ],
        }
        raw_result = request.artifact_dir / "codex-journey-result.json"
        raw_events = request.artifact_dir / "codex-events.jsonl"
        raw_result.write_text(json.dumps(data), encoding="utf-8")
        raw_events.write_text('{"type":"turn.completed"}\n', encoding="utf-8")
        return JourneyExecutionResult(
            data=data,
            result_path=raw_result,
            events_path=raw_events,
            command=["codex", "exec"],
            backend=CODEX_CLI,
        )


def test_runner_separates_backend_raw_evidence_from_canonical_normalized_output(
    tmp_path: Path,
) -> None:
    runner = JourneySegmentRunner(
        backend=RecordingCodexBackend(),
        checkpoint_collector=RecordingCheckpointCollector(),
        system_event_injector=lambda event: None,
    )

    flow = runner.run(
        scenario=ScenarioSpec(id="selection-evidence", user_actions=["Tap target"]),
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        output_schema=tmp_path / "schema.json",
    )

    result = flow.journey_results[0]
    segment_dir = tmp_path / "artifacts" / "selection-evidence-segment-0"
    raw_result = segment_dir / "codex-journey-result.json"
    raw_events = segment_dir / "codex-events.jsonl"
    normalized = segment_dir / "journey-result.normalized.json"
    lineage = segment_dir / "journey-action-lineage.json"
    legacy_normalized = segment_dir / "codex-journey-result.normalized.json"
    legacy_lineage = segment_dir / "codex-journey-action-lineage.json"

    assert raw_result.is_file()
    assert raw_events.is_file()
    assert normalized.is_file()
    assert lineage.is_file()
    assert legacy_normalized.is_file()
    assert legacy_lineage.is_file()
    assert result.result_path == legacy_normalized
    assert result.raw_result_path == raw_result
    assert result.raw_events_path == raw_events
    assert result.normalized_result_path == normalized
    assert result.action_lineage_path == lineage
    assert result.metadata["action_lineage_path"] == str(legacy_lineage)
    assert result.metadata["canonical_action_lineage_path"] == str(lineage)
    assert json.loads(raw_result.read_text(encoding="utf-8"))["results"][0].get(
        "action"
    ) is None
    assert json.loads(normalized.read_text(encoding="utf-8"))["results"][0][
        "action"
    ] == "Tap target"
    assert json.loads(lineage.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "backend": CODEX_CLI,
        "journey": "selection-evidence-segment-0",
        "raw_result": str(raw_result),
        "events": str(raw_events),
        "results": [
            {
                "action_id": "action-1",
                "requested_action": "Tap target",
                "status": "PASSED",
            }
        ],
    }


def test_cli_does_not_fallback_to_codex_for_unwired_deterministic_selection(
    tmp_path: Path,
) -> None:
    plan = tmp_path / "driver-plan.json"
    plan.write_text("{}\n", encoding="utf-8")
    spec = RunSpec(
        host_project=tmp_path,
        apk_glob="*.apk",
        package="org.example.project",
        activity="org.example.project.MainActivity",
        diff=None,
        spec=None,
        scenario=ScenarioSpec(id="deterministic-selection"),
    )

    with pytest.raises(
        ProductionSeamAdmissionError,
        match="requires exact source-backed Run Spec bytes",
    ):
        cli.run(
            spec,
            device="emulator-5554",
            artifact_dir=tmp_path / "run" / "artifacts",
            workdir=tmp_path,
            backend=DETERMINISTIC_ANDROID_V1,
            driver_plan_path=plan,
        )

    assert not (tmp_path / "run" / "execution-record.json").exists()
