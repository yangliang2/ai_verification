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
        if len(args) == 2 and args[1] == "--version":
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


def _write_codex_session(
    session_root: Path,
    *,
    thread_id: str,
    model: str,
    cwd: Path,
) -> Path:
    session_path = session_root / f"rollout-2026-07-17T00-00-00-{thread_id}.jsonl"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": thread_id,
                            "cwd": str(cwd),
                            "cli_version": "0.139.0",
                            "source": "exec",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn_context",
                        "payload": {
                            "turn_id": "turn-1",
                            "model": model,
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return session_path


def _backend_with_identity(
    tmp_path: Path,
    runner: FakeRunner,
    *,
    cwd: Path | None = None,
    effective_model: str = "gpt-5.1-codex",
) -> CodexCliBackend:
    thread_id = "019f7118-9441-72f2-8831-8c46759ca86d"
    session_root = tmp_path / "sessions"
    _write_codex_session(
        session_root,
        thread_id=thread_id,
        model=effective_model,
        cwd=cwd or tmp_path,
    )
    original_run = runner.run

    def run_with_thread(args, **kwargs):
        result = original_run(args, **kwargs)
        if len(args) >= 2 and args[1] == "exec":
            return CommandResult(
                args=result.args,
                stdout=json.dumps({"type": "thread.started", "thread_id": thread_id})
                + "\n"
                + json.dumps({"type": "turn.completed"})
                + "\n",
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return result

    runner.run = run_with_thread
    return CodexCliBackend(runner=runner, session_root=session_root)


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
    backend = _backend_with_identity(tmp_path, runner)

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


def test_codex_backend_binds_requested_model_to_effective_session_model(
    tmp_path: Path,
) -> None:
    thread_id = "019f7118-9441-72f2-8831-8c46759ca86c"
    session_root = tmp_path / "sessions"
    session_path = _write_codex_session(
        session_root,
        thread_id=thread_id,
        model="gpt-5.1-codex",
        cwd=tmp_path,
    )
    runner = FakeRunner(
        result_json={"journey": "smoke", "results": []},
    )
    codex_bin = tmp_path / "codex"
    codex_bin.write_bytes(b"fake codex binary\n")
    codex_bin.chmod(0o755)
    original_run = runner.run

    def run_with_thread(args, **kwargs):
        result = original_run(args, **kwargs)
        if args[:2] == [str(codex_bin), "exec"]:
            return CommandResult(
                args=result.args,
                stdout=json.dumps({"type": "thread.started", "thread_id": thread_id})
                + "\n"
                + json.dumps({"type": "turn.completed"})
                + "\n",
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return result

    runner.run = run_with_thread
    backend = CodexCliBackend(
        codex_bin=str(codex_bin),
        runner=runner,
        session_root=session_root,
    )
    request = JourneyExecutionRequest(
        journey_instructions='<journey name="smoke" />',
        workdir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        model="gpt-5.1-codex",
    )

    result = backend.execute(request)

    command = runner.calls[0]
    assert command[command.index("--model") + 1] == "gpt-5.1-codex"
    identity_path = Path(result.metadata["identity_receipt_path"])
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    assert identity["role"] == "journey_driver"
    assert identity["requested_model"] == "gpt-5.1-codex"
    assert identity["effective_model"] == "gpt-5.1-codex"
    assert identity["effective_model_source"] == {
        "kind": "codex_session_turn_context",
        "session_path": str(session_path),
        "session_sha256": identity["effective_model_source"]["session_sha256"],
        "thread_id": thread_id,
        "turn_id": "turn-1",
    }


def test_codex_backend_rejects_requested_effective_model_mismatch(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(result_json={"journey": "smoke", "results": []})
    backend = _backend_with_identity(
        tmp_path,
        runner,
        effective_model="gpt-5.2-codex",
    )

    with pytest.raises(CodexCliError, match="effective model contradicts"):
        backend.execute(
            JourneyExecutionRequest(
                journey_instructions='<journey name="smoke" />',
                workdir=tmp_path,
                artifact_dir=tmp_path / "artifacts",
                model="gpt-5.1-codex",
            )
        )


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

    result = _backend_with_identity(tmp_path, runner, cwd=host_workdir).execute(
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
