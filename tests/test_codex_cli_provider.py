"""CodexCliProvider（codex exec 适配 LLMProvider）的单测。"""

from pathlib import Path

import pytest

from aiverify.providers.codex_cli import CodexCliProvider, CodexCliProviderError
from aiverify.runner.command import CommandResult, CommandRunner


class FakeRunner(CommandRunner):
    """按脚本回放的 CommandRunner：记录调用并把'最终回答'写到 --output-last-message。"""

    def __init__(self, *, answer: str = "", returncode: int = 0, write_result: bool = True):
        self.answer = answer
        self.returncode = returncode
        self.write_result = write_result
        self.calls: list[dict] = []

    def run(self, args, *, cwd=None, timeout_seconds=None, input_text=None):
        self.calls.append(
            {"args": list(args), "cwd": cwd, "timeout": timeout_seconds, "stdin": input_text}
        )
        if self.write_result and self.returncode == 0:
            out_path = Path(args[args.index("--output-last-message") + 1])
            out_path.write_text(self.answer, encoding="utf-8")
        return CommandResult(
            args=list(args), stdout='{"event":"x"}\n', stderr="boom", returncode=self.returncode
        )


def test_complete_returns_last_message_and_openai_provider_id(tmp_path):
    runner = FakeRunner(answer='{"outcome": "pass"}')
    p = CodexCliProvider(workdir=tmp_path, runner=runner)
    result = p.complete("judge this", system="you are a judge")

    assert p.provider_id == "openai"
    assert result.text == '{"outcome": "pass"}'
    args = runner.calls[0]["args"]
    # system 无独立通道，与 prompt 拼接为最后一个位置参数
    assert args[-1] == "you are a judge\n\njudge this"
    assert args[:3] == ["codex", "exec", "--json"]
    # judge 只读证据，不得操作设备
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert ["--cd", str(tmp_path)] == args[args.index("--cd"):args.index("--cd") + 2]
    # 空 stdin，避免 codex exec 阻塞
    assert runner.calls[0]["stdin"] == ""


def test_complete_without_system_passes_prompt_verbatim(tmp_path):
    runner = FakeRunner(answer="ok")
    p = CodexCliProvider(workdir=tmp_path, runner=runner)
    p.complete("raw prompt")
    assert runner.calls[0]["args"][-1] == "raw prompt"


def test_model_override_adds_flag(tmp_path):
    runner = FakeRunner(answer="ok")
    p = CodexCliProvider(workdir=tmp_path, model="gpt-5.1-codex", runner=runner)
    result = p.complete("x")
    args = runner.calls[0]["args"]
    assert args[args.index("--model") + 1] == "gpt-5.1-codex"
    assert result.model == "gpt-5.1-codex"


def test_artifact_dir_persists_answer_and_events_per_call(tmp_path):
    runner = FakeRunner(answer="verdict-1")
    art = tmp_path / "l3"
    p = CodexCliProvider(workdir=tmp_path, artifact_dir=art, runner=runner)
    p.complete("first")
    runner.answer = "verdict-2"
    p.complete("second")

    assert (art / "l3-judge-call-1.md").read_text(encoding="utf-8") == "verdict-1"
    assert (art / "l3-judge-call-2.md").read_text(encoding="utf-8") == "verdict-2"
    assert (art / "l3-judge-call-1.events.jsonl").read_text(encoding="utf-8") == '{"event":"x"}\n'
    assert (art / "l3-judge-call-1.prompt.md").read_text(encoding="utf-8") == "first"
    assert (art / "l3-judge-call-2.prompt.md").read_text(encoding="utf-8") == "second"


def test_nonzero_exit_raises(tmp_path):
    runner = FakeRunner(returncode=3)
    p = CodexCliProvider(workdir=tmp_path, runner=runner)
    with pytest.raises(CodexCliProviderError, match="exit code 3"):
        p.complete("x")


def test_missing_result_file_raises(tmp_path):
    runner = FakeRunner(write_result=False)
    p = CodexCliProvider(workdir=tmp_path, runner=runner)
    with pytest.raises(CodexCliProviderError, match="最终回答"):
        p.complete("x")
