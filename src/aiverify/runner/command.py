"""Command runner seam used by runner integrations."""

from __future__ import annotations

import abc
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """Result of a command execution."""

    args: list[str]
    stdout: str
    stderr: str
    returncode: int


class CommandRunner(abc.ABC):
    """Abstract command runner for tests and subprocess-backed integrations."""

    @abc.abstractmethod
    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        """Run a command and return captured output."""


class SubprocessCommandRunner(CommandRunner):
    """Production command runner using subprocess.run."""

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        proc = subprocess.run(
            args,
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        return CommandResult(
            args=list(args),
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
        )
