from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.runner.codex_backend import (
    CodexCliBackend,
    CodexCliError,
    JourneyExecutionRequest,
)
from aiverify.runner.command import CommandResult, CommandRunner


class FakeRunner(CommandRunner):
    def __init__(self, *, result_json: dict | str | None = None, returncode: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.result_json = result_json
        self.returncode = returncode

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(args)
        if args == ["codex", "--version"]:
            return CommandResult(args=args, stdout="codex-cli 0.139.0\n", stderr="", returncode=0)
        if "--output-last-message" in args and self.result_json is not None:
            out = Path(args[args.index("--output-last-message") + 1])
            if isinstance(self.result_json, str):
                out.write_text(self.result_json, encoding="utf-8")
            else:
                out.write_text(json.dumps(self.result_json), encoding="utf-8")
        return CommandResult(
            args=args,
            stdout='{"type":"turn.completed"}\n',
            stderr="boom" if self.returncode else "",
            returncode=self.returncode,
        )


def _request(tmp_path: Path) -> JourneyExecutionRequest:
    return JourneyExecutionRequest(
        journey_instructions="<journey name=\"smoke\" />",
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
    )


def test_codex_backend_invokes_exec_and_parses_result(tmp_path: Path) -> None:
    runner = FakeRunner(
        result_json={
            "journey": "smoke",
            "results": [{"action": "Open search", "status": "PASSED"}],
        }
    )
    backend = CodexCliBackend(runner=runner)

    result = backend.execute(_request(tmp_path))

    command = runner.calls[0]
    assert command[:2] == ["codex", "exec"]
    assert "--json" in command
    assert "--output-schema" in command
    assert "--output-last-message" in command
    assert result.data["journey"] == "smoke"
    assert result.events_path.read_text(encoding="utf-8").strip()
    assert result.metadata["codex_version"] == "codex-cli 0.139.0"


def test_codex_backend_raises_on_nonzero_exit(tmp_path: Path) -> None:
    backend = CodexCliBackend(runner=FakeRunner(returncode=2))

    with pytest.raises(CodexCliError, match="exit code 2"):
        backend.execute(_request(tmp_path))


def test_codex_backend_raises_on_invalid_schema(tmp_path: Path) -> None:
    backend = CodexCliBackend(runner=FakeRunner(result_json={"journey": "smoke"}))

    with pytest.raises(CodexCliError, match="schema"):
        backend.execute(_request(tmp_path))


def test_codex_backend_raises_on_malformed_json(tmp_path: Path) -> None:
    backend = CodexCliBackend(runner=FakeRunner(result_json="{not-json"))

    with pytest.raises(CodexCliError, match="not JSON"):
        backend.execute(_request(tmp_path))
