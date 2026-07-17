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
            "results": [
                {
                    "action_id": "action-1",
                    "status": "PASSED",
                    "commands": ["android layout --device=emulator-5554 --pretty"],
                    "comment": "search opened",
                }
            ],
        }
    )
    backend = CodexCliBackend(runner=runner)

    result = backend.execute(_request(tmp_path))

    command = runner.calls[0]
    assert command[:2] == ["codex", "exec"]
    assert "--json" in command
    assert "--output-schema" in command
    assert "--output-last-message" in command
    # codex 0.139.0 exec rejects --ask-for-approval; must use the bypass flag instead
    assert "--ask-for-approval" not in command
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--skip-git-repo-check" in command
    assert result.data["journey"] == "smoke"
    assert result.events_path.read_text(encoding="utf-8").strip()
    assert result.metadata["codex_version"] == "codex-cli 0.139.0"


def test_codex_backend_resolves_artifact_paths_before_changing_to_host_workdir(
    tmp_path: Path, monkeypatch
) -> None:
    host_workdir = tmp_path / "host"
    host_workdir.mkdir()
    monkeypatch.chdir(tmp_path)
    runner = FakeRunner(
        result_json={
            "journey": "smoke",
            "results": [
                {
                    "action_id": "action-1",
                    "status": "PASSED",
                    "commands": ["android layout --device=emulator-5554 --pretty"],
                    "comment": "visible UI found",
                }
            ],
        }
    )

    result = CodexCliBackend(runner=runner).execute(
        JourneyExecutionRequest(
            journey_instructions='<journey name="smoke" />',
            workdir=host_workdir,
            artifact_dir=Path("run/artifacts"),
        )
    )

    command = runner.calls[0]
    output_path = Path(command[command.index("--output-last-message") + 1])
    assert output_path == (tmp_path / "run/artifacts/codex-journey-result.json")
    assert output_path.is_absolute()
    assert result.result_path == output_path


def test_codex_backend_raises_on_nonzero_exit(tmp_path: Path) -> None:
    backend = CodexCliBackend(runner=FakeRunner(returncode=2))

    with pytest.raises(CodexCliError, match="exit code 2"):
        backend.execute(_request(tmp_path))


def test_codex_backend_raises_on_invalid_schema(tmp_path: Path) -> None:
    backend = CodexCliBackend(runner=FakeRunner(result_json={"journey": "smoke"}))

    with pytest.raises(CodexCliError, match="schema"):
        backend.execute(_request(tmp_path))


def test_codex_backend_rejects_historical_action_text_without_action_id(
    tmp_path: Path,
) -> None:
    backend = CodexCliBackend(
        runner=FakeRunner(
            result_json={
                "journey": "smoke",
                "results": [
                    {
                        "action": (
                            "Navigate from the main feed to the bottom Search tab and "
                            "confirm it is selected with search_card visible."
                        ),
                        "status": "PASSED",
                        "commands": [],
                        "comment": "completed",
                    }
                ],
            }
        )
    )

    with pytest.raises(CodexCliError, match="schema"):
        backend.execute(_request(tmp_path))


def test_codex_backend_raises_on_malformed_json(tmp_path: Path) -> None:
    backend = CodexCliBackend(runner=FakeRunner(result_json="{not-json"))

    with pytest.raises(CodexCliError, match="not JSON"):
        backend.execute(_request(tmp_path))
