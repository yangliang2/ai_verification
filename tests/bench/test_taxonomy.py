"""分类法不变量校验的单测（AC2）。

覆盖真实 taxonomy.yaml 的全部不变量，以及用 tmp_path 写畸形 YAML 验证报错路径。
"""

from __future__ import annotations

import textwrap

import pytest

from aiverify.bench.taxonomy import (
    MIN_PATTERNS_PER_CATEGORY,
    REQUIRED_CATEGORIES,
    REQUIRED_PATTERN_FIELDS,
    TaxonomyError,
    load_taxonomy,
)


# --- 真实 taxonomy.yaml 的不变量 ------------------------------------------------


def test_real_taxonomy_loads():
    tax = load_taxonomy()
    assert tax.version >= 1
    assert {c.key for c in tax.categories} == set(REQUIRED_CATEGORIES)


def test_real_taxonomy_has_all_five_categories_in_order():
    tax = load_taxonomy()
    assert [c.key for c in tax.categories] == list(REQUIRED_CATEGORIES)


def test_real_taxonomy_each_category_meets_minimum():
    tax = load_taxonomy()
    for cat in tax.categories:
        assert len(cat.patterns) >= MIN_PATTERNS_PER_CATEGORY, (
            f"{cat.key} 只有 {len(cat.patterns)} 个模式"
        )


def test_real_taxonomy_ids_globally_unique():
    tax = load_taxonomy()
    ids = [p.id for p in tax.patterns]
    assert len(ids) == len(set(ids))
    assert len(tax.by_id) == len(ids)


def test_real_taxonomy_ids_carry_category_prefix():
    tax = load_taxonomy()
    for cat in tax.categories:
        for pat in cat.patterns:
            assert pat.id.startswith(f"{cat.key}-")
            assert pat.category == cat.key


def test_real_taxonomy_patterns_have_all_required_fields_nonempty():
    tax = load_taxonomy()
    for pat in tax.patterns:
        for f in REQUIRED_PATTERN_FIELDS:
            value = getattr(pat, f)
            if f == "device_state_dimensions":
                assert isinstance(value, list)
            else:
                assert isinstance(value, str) and value.strip(), (
                    f"{pat.id}.{f} 为空"
                )


def test_real_taxonomy_before_after_examples_differ():
    tax = load_taxonomy()
    for pat in tax.patterns:
        assert pat.kotlin_example_before.strip() != pat.kotlin_example_after.strip(), (
            f"{pat.id} 的 before/after 示例相同，未体现变异"
        )


def test_lookup_by_id_and_category_helpers():
    tax = load_taxonomy()
    first = tax.patterns[0]
    assert tax.by_id[first.id] is first
    assert tax.category(first.category).key == first.category
    with pytest.raises(KeyError):
        tax.category("does-not-exist")


# --- 畸形 YAML 的报错路径（tmp_path） ------------------------------------------


def _write(tmp_path, content: str):
    p = tmp_path / "taxonomy.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _full_pattern(pid: str, *, prefix: str) -> str:
    return textwrap.indent(
        textwrap.dedent(
            f"""\
            - id: {pid}
              name: n
              description: d
              kotlin_example_before: "a"
              kotlin_example_after: "b"
              trigger_scenario: t
              expected_failure: f
              device_state_dimensions: [low-memory]
            """
        ),
        "      ",
    )


def _valid_doc(patterns_per_cat: int = MIN_PATTERNS_PER_CATEGORY) -> str:
    lines = ["version: 1", "categories:"]
    for key in REQUIRED_CATEGORIES:
        lines.append(f"  {key}:")
        lines.append(f"    title: {key}")
        lines.append("    patterns:")
        for i in range(patterns_per_cat):
            lines.append(_full_pattern(f"{key}-{i:02d}", prefix=key).rstrip("\n"))
    return "\n".join(lines) + "\n"


def test_handcrafted_valid_doc_passes(tmp_path):
    p = _write(tmp_path, _valid_doc())
    tax = load_taxonomy(p)
    assert len(tax.patterns) == MIN_PATTERNS_PER_CATEGORY * len(REQUIRED_CATEGORIES)


def test_missing_file_raises(tmp_path):
    with pytest.raises(TaxonomyError, match="不存在"):
        load_taxonomy(tmp_path / "nope.yaml")


def test_top_level_not_mapping_raises(tmp_path):
    p = _write(tmp_path, "- just\n- a\n- list\n")
    with pytest.raises(TaxonomyError, match="顶层必须是映射"):
        load_taxonomy(p)


def test_missing_categories_key_raises(tmp_path):
    p = _write(tmp_path, "version: 1\n")
    with pytest.raises(TaxonomyError, match="categories"):
        load_taxonomy(p)


def test_missing_one_category_raises(tmp_path):
    doc = _valid_doc()
    # 删掉 navigation 整段
    doc = doc.replace("  navigation:\n", "  _removed:\n")
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError) as exc:
        load_taxonomy(p)
    assert "缺少必需类" in str(exc.value)
    assert "navigation" in str(exc.value)
    assert "未知类" in str(exc.value)


def test_too_few_patterns_raises(tmp_path):
    # 让每类只有 MIN-1 个模式
    p = _write(tmp_path, _valid_doc(patterns_per_cat=MIN_PATTERNS_PER_CATEGORY - 1))
    with pytest.raises(TaxonomyError) as exc:
        load_taxonomy(p)
    msg = str(exc.value)
    assert "模式数" in msg
    # 五类都不足，应全部报告
    for key in REQUIRED_CATEGORIES:
        assert key in msg


def test_duplicate_id_raises(tmp_path):
    doc = _valid_doc()
    # 把 lifecycle-01 这个 id 也用到第二个模式上，制造重复
    doc = doc.replace("id: lifecycle-01", "id: lifecycle-00", 1)
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError, match="id 重复"):
        load_taxonomy(p)


def test_missing_required_field_raises(tmp_path):
    doc = _valid_doc()
    doc = doc.replace("        expected_failure: f\n", "", 1)
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError, match="缺少或为空的字段.*expected_failure"):
        load_taxonomy(p)


def test_empty_field_treated_as_missing(tmp_path):
    doc = _valid_doc()
    doc = doc.replace("        description: d\n", '        description: "   "\n', 1)
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError, match="description"):
        load_taxonomy(p)


def test_wrong_id_prefix_raises(tmp_path):
    doc = _valid_doc()
    doc = doc.replace("id: lifecycle-00", "id: wrong-00", 1)
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError, match="前缀"):
        load_taxonomy(p)


def test_device_dimensions_must_be_string_list(tmp_path):
    doc = _valid_doc()
    doc = doc.replace(
        "device_state_dimensions: [low-memory]",
        "device_state_dimensions: 123",
        1,
    )
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError, match="device_state_dimensions 必须是字符串列表"):
        load_taxonomy(p)


def test_error_message_aggregates_multiple_problems(tmp_path):
    # 同时制造：缺类 + id 前缀错。验证一次性汇总而非只报第一条。
    doc = _valid_doc()
    doc = doc.replace("  process-death:\n", "  _gone:\n")
    doc = doc.replace("id: lifecycle-00", "id: bad-00", 1)
    p = _write(tmp_path, doc)
    with pytest.raises(TaxonomyError) as exc:
        load_taxonomy(p)
    msg = str(exc.value)
    assert "缺少必需类" in msg
    assert "前缀" in msg
