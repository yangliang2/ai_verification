"""Patcher 单元测试。

覆盖路径：
- 正常应用 patch
- 回滚已应用 patch
- 预验证失败（--check 失败）工作区无残留
- 通过真实 git 工程（tmp_path git init）验证
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aiverify.harness.build import Patcher, PatchError


# ---------------------------------------------------------------------------
# 辅助：在 tmp_path 里建立真实最小 git 工程
# ---------------------------------------------------------------------------

def _init_repo(base: Path) -> Path:
    """在 base 下初始化 git 仓库，提交初始文件，返回仓库路径。"""
    repo = base / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

    # 创建初始文件并提交
    hello = repo / "hello.txt"
    hello.write_text("line1\nline2\nline3\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
    return repo


def _make_patch(old_content: str, new_content: str, filepath: str = "hello.txt") -> str:
    """生成一段简单 unified diff patch 文本（不依赖外部工具，手工构造）。"""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # 简单逐行 diff（测试用，文件很小）
    import difflib
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
    ))
    return "".join(diff)


# ---------------------------------------------------------------------------
# 测试：正常应用
# ---------------------------------------------------------------------------

def test_apply_success(tmp_path: Path) -> None:
    """应用有效 patch 后文件内容应已变更。"""
    repo = _init_repo(tmp_path)
    patcher = Patcher(repo)

    old = "line1\nline2\nline3\n"
    new = "line1\nline2_modified\nline3\n"
    patch = _make_patch(old, new)

    patcher.apply(patch)

    assert (repo / "hello.txt").read_text() == new


# ---------------------------------------------------------------------------
# 测试：回滚
# ---------------------------------------------------------------------------

def test_revert_restores_original(tmp_path: Path) -> None:
    """apply 之后 revert 应恢复原始内容。"""
    repo = _init_repo(tmp_path)
    patcher = Patcher(repo)

    old = "line1\nline2\nline3\n"
    new = "line1\nline2_modified\nline3\n"
    patch = _make_patch(old, new)

    patcher.apply(patch)
    assert (repo / "hello.txt").read_text() == new

    patcher.revert(patch)
    assert (repo / "hello.txt").read_text() == old


# ---------------------------------------------------------------------------
# 测试：预验证失败 —— 工作区无残留
# ---------------------------------------------------------------------------

def test_apply_invalid_patch_no_residue(tmp_path: Path) -> None:
    """无效 patch 应抛 PatchError，且文件内容不变（工作区干净）。"""
    repo = _init_repo(tmp_path)
    patcher = Patcher(repo)

    original = (repo / "hello.txt").read_text()

    # 构造错误 patch：行号不匹配，git apply --check 必然失败
    bad_patch = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -99,3 +99,3 @@\n"
        " nonexistent_line\n"
        "-old\n"
        "+new\n"
    )

    with pytest.raises(PatchError):
        patcher.apply(bad_patch)

    # 工作区无残留
    assert (repo / "hello.txt").read_text() == original


# ---------------------------------------------------------------------------
# 测试：patch 不存在文件 —— 预验证失败
# ---------------------------------------------------------------------------

def test_apply_nonexistent_file_patch_fails_cleanly(tmp_path: Path) -> None:
    """patch 指向不存在文件时，--check 失败，工作区干净。"""
    repo = _init_repo(tmp_path)
    patcher = Patcher(repo)

    bad_patch = (
        "--- a/no_such_file.java\n"
        "+++ b/no_such_file.java\n"
        "@@ -1,3 +1,3 @@\n"
        " a\n"
        "-b\n"
        "+c\n"
    )

    with pytest.raises(PatchError):
        patcher.apply(bad_patch)

    assert not (repo / "no_such_file.java").exists()
