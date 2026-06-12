"""Batcher 单元测试。

覆盖路径：
- 全不相交：所有 patch 可进同一批次
- 两两相交：每个 patch 各自一批
- 单文件冲突链：A-B 相交、B-C 相交、A-C 不相交
- K 上限截断：超过 max_batch_size 时新建批次
- touched_files_from_diff 工具函数：新建/修改/删除文件解析
- 空输入返回空列表
"""

from __future__ import annotations

import pytest

from aiverify.harness.build import (
    Batcher,
    Batch,
    PatchItem,
    touched_files_from_diff,
)


# ---------------------------------------------------------------------------
# touched_files_from_diff 工具函数测试
# ---------------------------------------------------------------------------

def test_touched_files_modify() -> None:
    """修改已存在文件时解析出文件路径。"""
    diff = (
        "--- a/src/Foo.java\n"
        "+++ b/src/Foo.java\n"
        "@@ -1,2 +1,2 @@\n"
        "-old\n"
        "+new\n"
    )
    assert touched_files_from_diff(diff) == frozenset({"src/Foo.java"})


def test_touched_files_new_file() -> None:
    """新建文件（/dev/null 来源）只解析目标路径。"""
    diff = (
        "--- /dev/null\n"
        "+++ b/src/Bar.java\n"
        "@@ -0,0 +1,2 @@\n"
        "+line1\n"
        "+line2\n"
    )
    assert touched_files_from_diff(diff) == frozenset({"src/Bar.java"})


def test_touched_files_delete_file() -> None:
    """删除文件（+++ /dev/null）只解析来源路径。"""
    diff = (
        "--- a/src/Old.java\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-line1\n"
        "-line2\n"
    )
    assert touched_files_from_diff(diff) == frozenset({"src/Old.java"})


def test_touched_files_multi_file_diff() -> None:
    """多文件 diff 解析出所有触碰文件。"""
    diff = (
        "--- a/src/A.java\n"
        "+++ b/src/A.java\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
        "--- a/src/B.java\n"
        "+++ b/src/B.java\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
    )
    assert touched_files_from_diff(diff) == frozenset({"src/A.java", "src/B.java"})


def test_touched_files_empty_diff() -> None:
    """空 diff 返回空集合。"""
    assert touched_files_from_diff("") == frozenset()


# ---------------------------------------------------------------------------
# Batcher 测试
# ---------------------------------------------------------------------------

def _item(id: str, files: set[str], patch_text: str = "") -> PatchItem:
    return PatchItem(id=id, touched_files=frozenset(files), patch_text=patch_text)


def test_batch_empty_input() -> None:
    """空输入返回空列表。"""
    batcher = Batcher(max_batch_size=4)
    assert batcher.batch([]) == []


def test_batch_all_disjoint() -> None:
    """所有 patch 文件集不相交时，全部进入同一批次（K 足够大）。"""
    patches = [
        _item("p1", {"a.java"}),
        _item("p2", {"b.java"}),
        _item("p3", {"c.java"}),
    ]
    batcher = Batcher(max_batch_size=8)
    batches = batcher.batch(patches)

    assert len(batches) == 1
    assert len(batches[0].items) == 3
    ids = {item.id for item in batches[0].items}
    assert ids == {"p1", "p2", "p3"}


def test_batch_all_overlapping() -> None:
    """所有 patch 均触碰同一文件，每个 patch 各自一批。"""
    patches = [
        _item("p1", {"shared.java"}),
        _item("p2", {"shared.java"}),
        _item("p3", {"shared.java"}),
    ]
    batcher = Batcher(max_batch_size=8)
    batches = batcher.batch(patches)

    assert len(batches) == 3
    for batch in batches:
        assert len(batch.items) == 1


def test_batch_conflict_chain() -> None:
    """单文件冲突链：A-B 相交、B-C 相交、A-C 不相交。

    A={x}, B={x,y}, C={y}
    - p1(A) 进 batch0
    - p2(B) 与 batch0 相交（x），新建 batch1
    - p3(C) 与 batch0 不相交（A={x}, C={y} 不相交），进 batch0
    结果：batch0=[p1,p3], batch1=[p2]
    """
    patches = [
        _item("p1", {"x.java"}),
        _item("p2", {"x.java", "y.java"}),
        _item("p3", {"y.java"}),
    ]
    batcher = Batcher(max_batch_size=8)
    batches = batcher.batch(patches)

    assert len(batches) == 2
    batch0_ids = {item.id for item in batches[0].items}
    batch1_ids = {item.id for item in batches[1].items}
    assert batch0_ids == {"p1", "p3"}
    assert batch1_ids == {"p2"}


def test_batch_k_limit_truncation() -> None:
    """K=2 上限截断：4 个不相交 patch 应分成 2 批，每批 2 个。"""
    patches = [
        _item("p1", {"a.java"}),
        _item("p2", {"b.java"}),
        _item("p3", {"c.java"}),
        _item("p4", {"d.java"}),
    ]
    batcher = Batcher(max_batch_size=2)
    batches = batcher.batch(patches)

    assert len(batches) == 2
    assert len(batches[0].items) == 2
    assert len(batches[1].items) == 2
    # 每批内文件不相交（验证不变式）
    for batch in batches:
        all_files: list[frozenset[str]] = [item.touched_files for item in batch.items]
        for i, fi in enumerate(all_files):
            for j, fj in enumerate(all_files):
                if i != j:
                    assert fi.isdisjoint(fj), f"批内文件冲突：{fi} ∩ {fj}"


def test_batch_deterministic() -> None:
    """相同输入顺序两次调用结果完全相同。"""
    patches = [
        _item("p1", {"a.java", "b.java"}),
        _item("p2", {"c.java"}),
        _item("p3", {"b.java"}),
        _item("p4", {"d.java"}),
    ]
    batcher = Batcher(max_batch_size=4)
    result1 = batcher.batch(patches)
    result2 = batcher.batch(patches)

    assert len(result1) == len(result2)
    for b1, b2 in zip(result1, result2):
        ids1 = [item.id for item in b1.items]
        ids2 = [item.id for item in b2.items]
        assert ids1 == ids2


def test_batch_k1_each_patch_own_batch() -> None:
    """K=1 时每个 patch 独占一个批次。"""
    patches = [_item(f"p{i}", {f"f{i}.java"}) for i in range(5)]
    batcher = Batcher(max_batch_size=1)
    batches = batcher.batch(patches)

    assert len(batches) == 5
    for batch in batches:
        assert len(batch.items) == 1


def test_batcher_invalid_k() -> None:
    """max_batch_size < 1 时应抛 ValueError。"""
    with pytest.raises(ValueError):
        Batcher(max_batch_size=0)


def test_batch_invariant_no_file_overlap_in_batch() -> None:
    """验证任意分批结果中批内文件集两两不相交（不变式检查）。"""
    import random
    rng = random.Random(42)
    files = [f"f{i}.java" for i in range(10)]

    patches = []
    for i in range(20):
        chosen = frozenset(rng.sample(files, k=rng.randint(1, 3)))
        patches.append(PatchItem(id=f"p{i}", touched_files=chosen))

    batcher = Batcher(max_batch_size=4)
    batches = batcher.batch(patches)

    for batch_idx, batch in enumerate(batches):
        assert len(batch.items) <= 4, f"批次 {batch_idx} 超过 K=4"
        items = batch.items
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                assert items[i].touched_files.isdisjoint(items[j].touched_files), (
                    f"批次 {batch_idx} 中 {items[i].id} 与 {items[j].id} 文件集相交"
                )
