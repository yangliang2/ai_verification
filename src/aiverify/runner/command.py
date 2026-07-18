"""Command runner seam used by runner integrations."""

from __future__ import annotations

import abc
import os
import signal
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
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(input=input_text, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            return CommandResult(args=list(args), stdout=stdout, stderr=stderr, returncode=124)
        return CommandResult(
            args=list(args),
            stdout=stdout,
            stderr=stderr,
            returncode=proc.returncode,
        )
