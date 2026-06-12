"""Builder 单元测试。

覆盖路径：
- 缓存未命中：调用构建命令，产物写入缓存目录，返回缓存路径
- 缓存命中：不再调用构建命令，直接返回已有缓存路径
- 构建命令失败：抛 BuildError
- 构建成功但无 APK 产物：抛 BuildError
- 不同批次内容产生不同缓存 key（隔离验证）
- stub gradlew 脚本验证调用参数（命令模板注入）

所有测试均使用 stub 命令，不依赖真实 gradle。
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from aiverify.harness.build import Batch, Batcher, Builder, BuildError, PatchItem


# ---------------------------------------------------------------------------
# 辅助：创建 stub 工程与 stub gradlew
# ---------------------------------------------------------------------------

def _make_project(base: Path, apk_name: str = "app-debug.apk") -> Path:
    """创建最小 stub 工程目录，含一个生成固定 APK 的 stub gradlew 脚本。"""
    project = base / "project"
    project.mkdir()

    # stub gradlew：执行后在 build/outputs/ 下生成假 APK
    apk_dir = project / "build" / "outputs"
    gradlew = project / "gradlew"
    gradlew.write_text(
        "#!/bin/sh\n"
        f'mkdir -p "{apk_dir}"\n'
        f'echo "fake apk" > "{apk_dir}/{apk_name}"\n'
        'echo "BUILD SUCCESSFUL"\n'
        "exit 0\n"
    )
    gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return project


def _make_failing_project(base: Path) -> Path:
    """创建构建必然失败的 stub 工程。"""
    project = base / "failing_project"
    project.mkdir()
    gradlew = project / "gradlew"
    gradlew.write_text(
        "#!/bin/sh\n"
        'echo "BUILD FAILED" >&2\n'
        "exit 1\n"
    )
    gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return project


def _make_no_apk_project(base: Path) -> Path:
    """构建命令成功但不生成 APK 产物的 stub 工程。"""
    project = base / "no_apk_project"
    project.mkdir()
    gradlew = project / "gradlew"
    gradlew.write_text(
        "#!/bin/sh\n"
        'echo "BUILD SUCCESSFUL"\n'
        "exit 0\n"
    )
    gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return project


def _simple_batch(*ids_and_files: tuple[str, set[str]]) -> Batch:
    """快速构造 Batch，不经过 Batcher。"""
    items = [
        PatchItem(id=pid, touched_files=frozenset(files), patch_text=f"patch:{pid}")
        for pid, files in ids_and_files
    ]
    return Batch(items=items)


# ---------------------------------------------------------------------------
# 测试：缓存未命中 —— 构建并写缓存
# ---------------------------------------------------------------------------

def test_build_cache_miss_runs_command(tmp_path: Path) -> None:
    """缓存未命中时应执行构建命令，并将 APK 写入缓存目录。"""
    project = _make_project(tmp_path)
    cache_dir = tmp_path / "cache"
    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./gradlew", "assembleDebug"],
        apk_glob="**/*.apk",
    )

    batch = _simple_batch(("p1", {"a.java"}), ("p2", {"b.java"}))

    assert not builder.cache_hit(batch)

    result_path = builder.build(batch)

    assert result_path.exists()
    apks = list(result_path.glob("*.apk"))
    assert len(apks) == 1
    assert apks[0].name == "app-debug.apk"


# ---------------------------------------------------------------------------
# 测试：缓存命中 —— 跳过构建
# ---------------------------------------------------------------------------

def test_build_cache_hit_skips_command(tmp_path: Path) -> None:
    """缓存命中时不再调用构建命令：用计数脚本验证调用次数。"""
    project = _make_project(tmp_path)
    cache_dir = tmp_path / "cache"

    # 使用计数脚本：每次调用在 call_count 文件追加一行
    call_count_file = tmp_path / "call_count.txt"
    apk_dir = project / "build" / "outputs"
    gradlew = project / "gradlew"
    gradlew.write_text(
        "#!/bin/sh\n"
        f'echo "called" >> "{call_count_file}"\n'
        f'mkdir -p "{apk_dir}"\n'
        f'echo "fake" > "{apk_dir}/app-debug.apk"\n'
        "exit 0\n"
    )
    gradlew.chmod(gradlew.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./gradlew", "assembleDebug"],
        apk_glob="**/*.apk",
    )

    batch = _simple_batch(("p1", {"a.java"}))

    # 第一次构建
    builder.build(batch)
    assert call_count_file.read_text().strip().count("called") == 1

    # 第二次：缓存命中，不应再调用
    assert builder.cache_hit(batch)
    builder.build(batch)
    assert call_count_file.read_text().strip().count("called") == 1  # 仍为 1


# ---------------------------------------------------------------------------
# 测试：构建失败 —— 抛 BuildError
# ---------------------------------------------------------------------------

def test_build_failure_raises_build_error(tmp_path: Path) -> None:
    """构建命令退出码非零时应抛 BuildError。"""
    project = _make_failing_project(tmp_path)
    cache_dir = tmp_path / "cache"
    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./gradlew", "assembleDebug"],
        apk_glob="**/*.apk",
    )

    batch = _simple_batch(("p1", {"a.java"}))

    with pytest.raises(BuildError, match="构建失败"):
        builder.build(batch)


# ---------------------------------------------------------------------------
# 测试：构建成功但无 APK 产物
# ---------------------------------------------------------------------------

def test_build_success_no_apk_raises_build_error(tmp_path: Path) -> None:
    """构建命令成功但找不到 APK 时应抛 BuildError。"""
    project = _make_no_apk_project(tmp_path)
    cache_dir = tmp_path / "cache"
    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./gradlew", "assembleDebug"],
        apk_glob="**/*.apk",
    )

    batch = _simple_batch(("p1", {"a.java"}))

    with pytest.raises(BuildError, match="未找到任何 APK"):
        builder.build(batch)


# ---------------------------------------------------------------------------
# 测试：不同批次内容产生不同缓存 key
# ---------------------------------------------------------------------------

def test_different_batches_different_cache_keys(tmp_path: Path) -> None:
    """不同内容批次的缓存路径应不同（隔离验证）。"""
    project = _make_project(tmp_path)
    cache_dir = tmp_path / "cache"
    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./gradlew", "assembleDebug"],
        apk_glob="**/*.apk",
    )

    batch_a = _simple_batch(("p1", {"a.java"}))
    batch_b = _simple_batch(("p2", {"b.java"}))

    # 两批次哈希不同 → 缓存路径不同
    hash_a = builder._batch_hash(batch_a)
    hash_b = builder._batch_hash(batch_b)
    assert hash_a != hash_b


# ---------------------------------------------------------------------------
# 测试：相同内容批次产生相同缓存 key（幂等）
# ---------------------------------------------------------------------------

def test_same_batch_content_same_cache_key(tmp_path: Path) -> None:
    """相同内容的批次哈希应一致（缓存 key 幂等）。"""
    project = _make_project(tmp_path)
    cache_dir = tmp_path / "cache"
    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./gradlew", "assembleDebug"],
        apk_glob="**/*.apk",
    )

    batch1 = _simple_batch(("p1", {"a.java"}), ("p2", {"b.java"}))
    batch2 = _simple_batch(("p2", {"b.java"}), ("p1", {"a.java"}))  # 顺序不同

    # 哈希以 id 排序，顺序无关
    assert builder._batch_hash(batch1) == builder._batch_hash(batch2)


# ---------------------------------------------------------------------------
# 测试：命令模板注入 —— 验证实际调用参数
# ---------------------------------------------------------------------------

def test_custom_command_template(tmp_path: Path) -> None:
    """自定义命令模板被实际执行（验证调用路径正确）。"""
    project = tmp_path / "proj"
    project.mkdir()
    cache_dir = tmp_path / "cache"

    # 自定义构建脚本
    apk_dir = project / "out"
    custom_script = project / "mybuild.sh"
    custom_script.write_text(
        "#!/bin/sh\n"
        f'mkdir -p "{apk_dir}"\n'
        f'echo "custom" > "{apk_dir}/custom.apk"\n'
        "exit 0\n"
    )
    custom_script.chmod(custom_script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    builder = Builder(
        project_dir=project,
        cache_dir=cache_dir,
        command_template=["./mybuild.sh"],
        apk_glob="**/*.apk",
    )

    batch = _simple_batch(("p1", {"x.java"}))
    result = builder.build(batch)

    apks = list(result.glob("*.apk"))
    assert len(apks) == 1
    assert apks[0].name == "custom.apk"
