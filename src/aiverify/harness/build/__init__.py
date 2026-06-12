"""harness.build：批量构建管线（US-003）。

导出：
- :class:`Patcher` / :class:`PatchError` — unified diff 应用与回滚
- :func:`touched_files_from_diff` — 从 diff 文本解析触碰文件
- :class:`PatchItem` / :class:`Batch` / :class:`Batcher` — 分批器
- :class:`Builder` / :class:`BuildError` — gradle 构建封装与缓存
"""

from .patcher import Patcher, PatchError
from .batcher import touched_files_from_diff, PatchItem, Batch, Batcher
from .builder import Builder, BuildError

__all__ = [
    "Patcher",
    "PatchError",
    "touched_files_from_diff",
    "PatchItem",
    "Batch",
    "Batcher",
    "Builder",
    "BuildError",
]
