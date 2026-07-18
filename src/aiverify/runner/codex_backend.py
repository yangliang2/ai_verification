"""Codex CLI Verification Agent Backend."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

from aiverify.runner.command import CommandRunner, SubprocessCommandRunner
from aiverify.runner.codex_identity import (
    CodexIdentityError,
    capture_codex_invocation_identity,
    default_codex_session_root,
)


_DEFAULT_SCHEMA_PATH = Path(__file__).with_name("journey_result_schema.json")


class CodexCliError(RuntimeError):
    """Raised when Codex CLI execution fails or emits invalid structured output."""

    def __init__(
        self,
        message: str,
        *,
        result_path: Path | None = None,
        events_path: Path | None = None,
        command: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.result_path = result_path
        self.events_path = events_path
        self.command = list(command) if command is not None else None


@dataclass(frozen=True)
class JourneyExecutionRequest:
    """Input contract for invoking Codex CLI on Journey instructions."""

    journey_instructions: str
    workdir: Path
    artifact_dir: Path
    output_schema: Path = _DEFAULT_SCHEMA_PATH
    timeout_seconds: int = 900
    sandbox: str = "workspace-write"
    dangerously_bypass: bool = True
    model: str | None = None


@dataclass(frozen=True)
class JourneyExecutionResult:
    """Structured result emitted by the Codex CLI backend."""

    data: dict[str, Any]
    result_path: Path
    events_path: Path
    command: list[str]
    metadata: dict[str, str] = field(default_factory=dict)


class CodexCliBackend:
    """Invoke Codex CLI as a Verification Agent Backend."""

    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        runner: CommandRunner | None = None,
        session_root: Path | None = None,
    ) -> None:
        self.codex_bin = codex_bin
        self.runner = runner if runner is not None else SubprocessCommandRunner()
        self.session_root = session_root or default_codex_session_root()

    def execute(self, request: JourneyExecutionRequest) -> JourneyExecutionResult:
        """Run Codex CLI and parse its schema-constrained final response."""
        artifact_dir = request.artifact_dir.resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        result_path = artifact_dir / "codex-journey-result.json"
        events_path = artifact_dir / "codex-events.jsonl"

        args = [
            self.codex_bin,
            "exec",
            "--json",
            "--output-schema",
            str(request.output_schema),
            "--output-last-message",
            str(result_path),
            "--skip-git-repo-check",
            "--cd",
            str(request.workdir),
        ]
        # codex 0.139.0 exec has no --ask-for-approval; non-interactive access to
        # the device (adb/android are outside the workspace) needs the bypass flag.
        if request.dangerously_bypass:
            args.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            args += ["--sandbox", request.sandbox]
        if request.model:
            args += ["--model", request.model]
        args.append(request.journey_instructions)

        result = self.runner.run(
            args,
            cwd=request.workdir,
            timeout_seconds=request.timeout_seconds,
            # feed empty stdin so codex exec does not block reading the parent's stdin
            input_text="",
        )
        events_path.write_text(result.stdout, encoding="utf-8")
        identity_path = artifact_dir / "codex-invocation-identity.json"
        identity = None
        identity_error: CodexIdentityError | None = None
        try:
            identity = capture_codex_invocation_identity(
                role="journey_driver",
                requested_model=request.model,
                command=args,
                codex_bin=self.codex_bin,
                runner=self.runner,
                events_path=events_path,
                receipt_path=identity_path,
                session_root=self.session_root,
            )
        except CodexIdentityError as exc:
            identity_error = exc
        if result.returncode != 0:
            raise CodexCliError(
                f"Codex CLI failed with exit code {result.returncode}: {result.stderr.strip()}",
                result_path=result_path if result_path.is_file() else None,
                events_path=events_path,
                command=args,
            )
        if not result_path.is_file():
            raise CodexCliError(
                f"Codex CLI did not write result file: {result_path}",
                events_path=events_path,
                command=args,
            )

        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CodexCliError(
                f"Codex CLI result is not JSON: {exc}",
                result_path=result_path,
                events_path=events_path,
                command=args,
            ) from exc

        schema = json.loads(request.output_schema.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as exc:
            raise CodexCliError(
                f"Codex CLI result failed schema validation: {exc.message}",
                result_path=result_path,
                events_path=events_path,
                command=args,
            ) from exc

        if identity_error is not None or identity is None:
            raise CodexCliError(
                f"Codex CLI identity capture failed: {identity_error}",
                result_path=result_path,
                events_path=events_path,
                command=args,
            ) from identity_error

        metadata = {
            "codex_version": identity["binary"]["version"],
            "effective_model": identity["effective_model"],
            "identity_receipt_path": str(identity_path),
        }
        return JourneyExecutionResult(
            data=data,
            result_path=result_path,
            events_path=events_path,
            command=args,
            metadata=metadata,
        )
