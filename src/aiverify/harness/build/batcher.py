"""Batcher：将缺陷 patch 列表分批，保证批内文件集两两不相交、批大小 ≤ K。

设计原则：
- 贪心算法，确定性（相同输入顺序输出相同）。
- 提供工具函数 :func:`touched_files_from_diff` 从 unified diff 文本解析触碰文件集合。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def touched_files_from_diff(patch_text: str) -> frozenset[str]:
    """从 unified diff 文本解析触碰文件集合。

    解析 ``--- a/<path>`` / ``+++ b/<path>`` 行，合并得到完整触碰文件列表。
    新建文件（``/dev/null`` 来源）和删除文件均被纳入。

    参数
    ----
    patch_text : str
        完整的 unified diff 文本。

    返回
    ----
    frozenset[str]
        相对路径字符串集合（去掉 ``a/`` / ``b/`` 前缀）。
    """
    files: set[str] = set()
    for line in patch_text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            # 格式：--- a/path/to/file 或 --- /dev/null
            path = line[4:].strip()
            # 去掉 a/ b/ 前缀
            if path.startswith("a/") or path.startswith("b/"):
                path = path[2:]
            if path and path != "/dev/null":
                files.add(path)
    return frozenset(files)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class PatchItem:
    """单条缺陷 patch 描述。

    属性
    ----
    id : str
        patch 唯一标识符。
    touched_files : frozenset[str]
        此 patch 触碰的文件集合（相对路径）。
    patch_text : str
        完整 unified diff 文本（可选，供 Patcher 使用）。
    """

    id: str
    touched_files: frozenset[str]
    patch_text: str = ""


@dataclass
class Batch:
    """一个批次。

    属性
    ----
    items : list[PatchItem]
        本批次包含的 patch 列表，批内文件集两两不相交。
    """

    items: list[PatchItem] = field(default_factory=list)

    @property
    def touched_files(self) -> frozenset[str]:
        """批次内所有触碰文件的并集。"""
        result: set[str] = set()
        for item in self.items:
            result |= item.touched_files
        return frozenset(result)


# ---------------------------------------------------------------------------
# Batcher
# ---------------------------------------------------------------------------

class Batcher:
    """将 patch 列表分批，保证批内文件集两两不相交且批大小 ≤ K。

    算法：贪心扫描——对每个 patch 找第一个满足容纳条件的已有批次；
    若无则新建批次。输入顺序固定则输出固定（确定性）。

    参数
    ----
    max_batch_size : int
        单批最大 patch 数量（K），默认 8。须 ≥ 1。
    """

    def __init__(self, max_batch_size: int = 8) -> None:
        if max_batch_size < 1:
            raise ValueError(f"max_batch_size 须 ≥ 1，实际传入 {max_batch_size}")
        self.max_batch_size = max_batch_size

    def batch(self, patches: list[PatchItem]) -> list[Batch]:
        """对 patch 列表分批。

        参数
        ----
        patches : list[PatchItem]
            输入缺陷 patch 列表，顺序影响分批结果（贪心，确定性）。

        返回
        ----
        list[Batch]
            分批结果列表；空输入返回空列表。
        """
        batches: list[Batch] = []

        for patch in patches:
            placed = False
            for batch in batches:
                # 检查容量
                if len(batch.items) >= self.max_batch_size:
                    continue
                # 检查文件不相交
                if batch.touched_files.isdisjoint(patch.touched_files):
                    batch.items.append(patch)
                    placed = True
                    break
            if not placed:
                new_batch = Batch(items=[patch])
                batches.append(new_batch)

        return batches
