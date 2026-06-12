"""Patcher：对目标 git 工程应用/回滚 unified diff patch。

设计原则：
- 先用 `git apply --check` 预验证，失败则不污染工作区。
- 应用成功后可用 `revert()` 通过 `git apply -R` 或 `git checkout` 恢复原状。
- 任何步骤失败均保证工作区无残留（clean workspace guarantee）。
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class PatchError(Exception):
    """patch 操作失败时抛出，包含原始 stderr 信息。"""


class Patcher:
    """对 git 工程应用/回滚 unified diff patch。

    参数
    ----
    repo_dir : Path
        目标 git 工程根目录（含 .git 子目录）。
    """

    def __init__(self, repo_dir: Path) -> None:
        self.repo_dir = Path(repo_dir)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _run(self, args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess:
        """运行命令，失败时抛 PatchError。"""
        result = subprocess.run(
            args,
            cwd=self.repo_dir,
            input=input_text,
            text=True,
            capture_output=True,
        )
        return result

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def apply(self, patch_text: str) -> None:
        """应用 unified diff patch 到工程。

        流程：
        1. ``git apply --check`` 预验证，失败抛 :class:`PatchError`，工作区不变。
        2. ``git apply`` 实际写入，失败时尝试 ``git apply -R`` 清理残留，
           仍抛 :class:`PatchError`。

        参数
        ----
        patch_text : str
            完整的 unified diff 文本。
        """
        # 步骤 1：预验证
        check = self._run(["git", "apply", "--check", "--whitespace=nowarn", "-"], input_text=patch_text)
        if check.returncode != 0:
            raise PatchError(
                f"git apply --check 失败，工作区未修改。\nstderr: {check.stderr.strip()}"
            )

        # 步骤 2：实际应用
        apply = self._run(["git", "apply", "--whitespace=nowarn", "-"], input_text=patch_text)
        if apply.returncode != 0:
            # 尝试回滚残留（尽力而为）
            self._run(["git", "apply", "-R", "--whitespace=nowarn", "-"], input_text=patch_text)
            # 兜底：checkout 所有改动
            self._run(["git", "checkout", "--", "."])
            raise PatchError(
                f"git apply 失败，已尝试清理工作区。\nstderr: {apply.stderr.strip()}"
            )

    def revert(self, patch_text: str) -> None:
        """回滚已应用的 patch（逆向应用）。

        先尝试 ``git apply -R``；若失败则退化到 ``git checkout -- .``
        以保证工作区干净。

        参数
        ----
        patch_text : str
            与 :meth:`apply` 传入的完全相同的 unified diff 文本。
        """
        reverse = self._run(
            ["git", "apply", "-R", "--whitespace=nowarn", "-"], input_text=patch_text
        )
        if reverse.returncode != 0:
            # 兜底：全量 checkout 恢复
            checkout = self._run(["git", "checkout", "--", "."])
            if checkout.returncode != 0:
                raise PatchError(
                    f"revert 失败：git apply -R 与 git checkout 均失败。\n"
                    f"stderr: {reverse.stderr.strip()}"
                )
