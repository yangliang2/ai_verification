"""Codex CLI 作为 LLMProvider 的适配器（L3 judge 后端）。

复用已装好的 `codex exec`（0.139.0），把一次 complete() 映射为一次
非交互 codex 调用：prompt 从命令行传入，最终回答经 --output-last-message
落盘后读回。provider_id="openai"，与 Claude 编写的注入 patch 异源，
满足 providers/base.py 的定标异源约束。

judge 只读证据、不得操作设备，因此 sandbox 固定为 read-only
（对比 runner/codex_backend.py 的 driver 需要 bypass 才能碰 adb）。
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from aiverify.providers.base import CompletionResult, LLMProvider
from aiverify.runner.codex_identity import (
    CodexIdentityError,
    capture_codex_invocation_identity,
    default_codex_session_root,
)
from aiverify.runner.command import CommandRunner, SubprocessCommandRunner
from aiverify.runner.execution_record import write_json_artifact


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
        session_root: Path | None = None,
        role: str = "l3_semantic_judge",
        artifact_prefix: str = "l3-judge-call",
        output_schema: Path | None = None,
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
        self.session_root = session_root or default_codex_session_root()
        self.role = role
        self.artifact_prefix = artifact_prefix
        self.output_schema = output_schema
        self._call_index = 0
        self.identity_receipts: list[Path] = []

    def complete(self, prompt: str, *, system: str = "") -> CompletionResult:
        # codex exec 没有独立 system 通道，system 前置拼接进同一 prompt。
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        self._call_index += 1
        if self.artifact_dir is not None:
            self.artifact_dir.mkdir(parents=True, exist_ok=True)
            stem = f"{self.artifact_prefix}-{self._call_index}"
            result_path = self.artifact_dir / f"{stem}.md"
            events_path = self.artifact_dir / f"{stem}.events.jsonl"
            prompt_path = self.artifact_dir / f"{stem}.prompt.md"
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
        if self.output_schema is not None:
            args += ["--output-schema", str(self.output_schema.resolve())]
        if self.workdir is not None:
            args += ["--cd", str(self.workdir)]
        if self.model:
            args += ["--model", self.model]
        args.append(full_prompt)

        if self.artifact_dir is not None:
            write_json_artifact(
                self.artifact_dir
                / f"{stem}.invocation.json",
                {
                    "schema_version": 1,
                    "role": self.role,
                    "call_index": self._call_index,
                    "requested_model": self.model,
                    "argv_without_prompt": args[:-1],
                    "prompt_sha256": hashlib.sha256(
                        full_prompt.encode("utf-8")
                    ).hexdigest(),
                },
            )

        result = self.runner.run(
            args,
            cwd=self.workdir,
            timeout_seconds=self.timeout_seconds,
            # 空 stdin，避免 codex exec 阻塞在读取父进程 stdin 上
            input_text="",
        )
        if events_path is not None:
            events_path.write_text(result.stdout, encoding="utf-8")
        identity_path: Path | None = None
        identity_error: CodexIdentityError | None = None
        effective_model = self.model or "codex-default"
        if events_path is not None:
            identity_path = (
                self.artifact_dir
                / f"{stem}.identity.json"
            )
            try:
                identity = capture_codex_invocation_identity(
                    role=self.role,
                    requested_model=self.model,
                    command=args,
                    codex_bin=self.codex_bin,
                    runner=self.runner,
                    events_path=events_path,
                    receipt_path=identity_path,
                    session_root=self.session_root,
                )
            except CodexIdentityError as error:
                identity_error = error
            else:
                effective_model = identity["effective_model"]
                self.identity_receipts.append(identity_path)
        if result.returncode != 0:
            raise CodexCliProviderError(
                f"codex exec 失败，exit code {result.returncode}: {result.stderr.strip()}"
            )
        if not result_path.is_file():
            raise CodexCliProviderError(f"codex exec 未写出最终回答文件：{result_path}")

        if identity_error is not None:
            raise CodexCliProviderError(
                f"codex exec identity capture failed: {identity_error}"
            ) from identity_error

        text = result_path.read_text(encoding="utf-8")
        return CompletionResult(
            text=text,
            model=effective_model,
            raw={
                "command": args,
                "returncode": result.returncode,
                **(
                    {"identity_receipt_path": str(identity_path)}
                    if identity_path is not None
                    else {}
                ),
            },
        )
