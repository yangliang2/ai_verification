"""Codex CLI 作为 LLMProvider 的适配器（L3 judge 后端）。

复用已装好的 `codex exec`（0.139.0），把一次 complete() 映射为一次
非交互 codex 调用：prompt 从命令行传入，最终回答经 --output-last-message
落盘后读回。provider_id="openai"，与 Claude 编写的注入 patch 异源，
满足 providers/base.py 的定标异源约束。

judge 只读证据、不得操作设备，因此 sandbox 固定为 read-only
（对比 runner/codex_backend.py 的 driver 需要 bypass 才能碰 adb）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from aiverify.providers.base import CompletionResult, LLMProvider
from aiverify.runner.command import CommandRunner, SubprocessCommandRunner


class CodexCliProviderError(RuntimeError):
    """codex exec 调用失败或未产出最终回答时抛出。"""


class CodexCliProvider(LLMProvider):
    """经 Codex CLI 完成同步补全的 LLMProvider 实现。"""

    provider_id = "openai"

    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        workdir: Path | None = None,
        model: str | None = None,
        timeout_seconds: int = 600,
        artifact_dir: Path | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        """
        参数
        ----
        workdir:
            codex --cd 的工作目录；judge 需要读取证据文件时应指向仓库根。
        artifact_dir:
            若给定，每次调用的完整输入、最终回答与事件流落盘到该目录
            （l3-judge-call-<n>.prompt.md / .md / .events.jsonl），作为可审计证据。
        """
        self.codex_bin = codex_bin
        self.workdir = workdir
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.artifact_dir = artifact_dir
        self.runner = runner if runner is not None else SubprocessCommandRunner()
        self._call_index = 0

    def complete(self, prompt: str, *, system: str = "") -> CompletionResult:
        # codex exec 没有独立 system 通道，system 前置拼接进同一 prompt。
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        self._call_index += 1
        if self.artifact_dir is not None:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            result_path = self.artifact_dir / f"l3-judge-call-{self._call_index}.md"
            events_path = self.artifact_dir / f"l3-judge-call-{self._call_index}.events.jsonl"
            prompt_path = self.artifact_dir / f"l3-judge-call-{self._call_index}.prompt.md"
            prompt_path.write_text(full_prompt, encoding="utf-8")
        else:
            tmpdir = Path(tempfile.mkdtemp(prefix="codex-provider-"))
            result_path = tmpdir / "last-message.md"
            events_path = None

        args = [
            self.codex_bin,
            "exec",
            "--json",
            "--output-last-message",
            str(result_path),
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
        ]
        if self.workdir is not None:
            args += ["--cd", str(self.workdir)]
        if self.model:
            args += ["--model", self.model]
        args.append(full_prompt)

        result = self.runner.run(
            args,
            cwd=self.workdir,
            timeout_seconds=self.timeout_seconds,
            # 空 stdin，避免 codex exec 阻塞在读取父进程 stdin 上
            input_text="",
        )
        if events_path is not None:
            events_path.write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0:
            raise CodexCliProviderError(
                f"codex exec 失败，exit code {result.returncode}: {result.stderr.strip()}"
            )
        if not result_path.is_file():
            raise CodexCliProviderError(f"codex exec 未写出最终回答文件：{result_path}")

        text = result_path.read_text(encoding="utf-8")
        return CompletionResult(
            text=text,
            model=self.model or "codex-default",
            raw={"command": args, "returncode": result.returncode},
        )
