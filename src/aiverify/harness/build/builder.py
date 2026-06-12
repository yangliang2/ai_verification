"""Builder：gradle 构建调用封装，含产物缓存。

设计原则：
- 默认命令 ``./gradlew assembleDebug``，命令模板可注入（支持测试 stub）。
- 以批次内 patch 内容哈希为 key 的 APK 缓存目录，命中则跳过构建。
- 缓存 key = SHA-256(各 patch_text 按 id 排序后拼接)。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

from .batcher import Batch


class BuildError(Exception):
    """构建命令执行失败时抛出。"""


class Builder:
    """gradle 构建调用封装，含内容哈希缓存。

    参数
    ----------
    project_dir : Path
        Android 工程根目录（含 gradlew 脚本）。
    cache_dir : Path
        APK 缓存根目录；每个缓存条目为其下的子目录，名称为批次哈希值。
    command_template : list[str] | None
        构建命令模板，``None`` 时使用 ``["./gradlew", "assembleDebug"]``。
        列表元素直接传给 :func:`subprocess.run`。
    apk_glob : str
        在工程目录内搜寻产物 APK 的 glob 模式，默认
        ``"**/*.apk"``。
    """

    DEFAULT_COMMAND: list[str] = ["./gradlew", "assembleDebug"]

    def __init__(
        self,
        project_dir: Path,
        cache_dir: Path,
        command_template: list[str] | None = None,
        apk_glob: str = "**/*.apk",
    ) -> None:
        self.project_dir = Path(project_dir)
        self.cache_dir = Path(cache_dir)
        self.command_template = command_template if command_template is not None else self.DEFAULT_COMMAND
        self.apk_glob = apk_glob

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _batch_hash(self, batch: Batch) -> str:
        """计算批次内容哈希（SHA-256）。

        以各 patch 的 ``id + patch_text`` 按 id 字典序排序后拼接，
        保证相同内容不同输入顺序得到相同 key。
        """
        sorted_items = sorted(batch.items, key=lambda p: p.id)
        content = "\n".join(f"{item.id}:{item.patch_text}" for item in sorted_items)
        return hashlib.sha256(content.encode()).hexdigest()

    def _cache_path(self, batch_hash: str) -> Path:
        """返回指定哈希的缓存子目录路径。"""
        return self.cache_dir / batch_hash

    def _find_apks(self, directory: Path) -> list[Path]:
        """在 directory 内按 apk_glob 查找 APK 文件。"""
        return list(directory.glob(self.apk_glob))

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def cache_hit(self, batch: Batch) -> bool:
        """判断该批次是否已有缓存产物。

        参数
        ----------
        batch : Batch
            目标批次。

        返回
        ----------
        bool
            缓存目录存在且含 APK 文件时返回 ``True``。
        """
        cache_path = self._cache_path(self._batch_hash(batch))
        if not cache_path.exists():
            return False
        return len(self._find_apks(cache_path)) > 0

    def build(self, batch: Batch) -> Path:
        """构建批次对应的 APK，返回缓存目录路径。

        若缓存命中直接返回已有缓存目录，跳过构建。
        否则运行构建命令，将产物复制到缓存目录后返回。

        参数
        ----------
        batch : Batch
            目标批次（patch 已由 Patcher 应用到工程）。

        返回
        ----------
        Path
            存放 APK 产物的缓存子目录。

        抛出
        ----------
        BuildError
            构建命令退出码非零，或构建后找不到任何 APK 产物。
        """
        batch_hash = self._batch_hash(batch)
        cache_path = self._cache_path(batch_hash)

        # 缓存命中
        if cache_path.exists() and self._find_apks(cache_path):
            return cache_path

        # 执行构建
        result = subprocess.run(
            self.command_template,
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise BuildError(
                f"构建失败（退出码 {result.returncode}）。\n"
                f"stdout: {result.stdout.strip()}\n"
                f"stderr: {result.stderr.strip()}"
            )

        # 搜集产物
        apks = self._find_apks(self.project_dir)
        if not apks:
            raise BuildError(
                f"构建命令成功但在 {self.project_dir} 内未找到任何 APK 产物"
                f"（glob: {self.apk_glob}）。"
            )

        # 写入缓存
        cache_path.mkdir(parents=True, exist_ok=True)
        for apk in apks:
            shutil.copy2(apk, cache_path / apk.name)

        return cache_path
