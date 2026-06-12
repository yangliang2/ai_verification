"""行为层缺陷分类法的加载与 schema 校验。

taxonomy.yaml 是缺陷注入系统的知识核心。注入器（bench/injector）按本模块
返回的结构化对象，对宿主 Kotlin 源码定点生成变异。因此加载时强校验若干不变量，
任一不满足即抛 TaxonomyError，并在 message 中给出全部明细，便于编辑 YAML 后快速定位。

不变量（AC2）：
  - 结构完整：顶层含 categories；每个模式含全部必填字段且非空
  - 五类齐全：lifecycle / config-change / process-death / navigation / coroutine-concurrency
  - 每类 ≥5 个模式
  - id 全局唯一
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

#: 五大类的规范键（顺序即文档展示顺序）。
REQUIRED_CATEGORIES: tuple[str, ...] = (
    "lifecycle",
    "config-change",
    "process-death",
    "navigation",
    "coroutine-concurrency",
)

#: 每类要求的最少模式数（AC1）。
MIN_PATTERNS_PER_CATEGORY = 5

#: 每个模式的必填字段。
REQUIRED_PATTERN_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "description",
    "kotlin_example_before",
    "kotlin_example_after",
    "trigger_scenario",
    "expected_failure",
    "device_state_dimensions",
)

#: 默认 taxonomy.yaml 路径（与本模块同目录）。
DEFAULT_TAXONOMY_PATH = Path(__file__).with_name("taxonomy.yaml")


class TaxonomyError(ValueError):
    """taxonomy.yaml 结构或不变量校验失败。message 含全部违规明细。"""


@dataclass(frozen=True)
class Pattern:
    """单个缺陷模式。字段语义见 taxonomy.yaml 头部注释。"""

    id: str
    name: str
    description: str
    kotlin_example_before: str
    kotlin_example_after: str
    trigger_scenario: str
    expected_failure: str
    device_state_dimensions: list[str]
    category: str


@dataclass(frozen=True)
class Category:
    """一大类缺陷及其模式集合。"""

    key: str
    title: str
    patterns: list[Pattern]


@dataclass(frozen=True)
class Taxonomy:
    """加载并校验后的分类法。"""

    version: int
    categories: list[Category]
    by_id: dict[str, Pattern] = field(default_factory=dict)

    @property
    def patterns(self) -> list[Pattern]:
        """全部模式的扁平列表，按类顺序展开。"""
        return [p for c in self.categories for p in c.patterns]

    def category(self, key: str) -> Category:
        """按键取类，不存在抛 KeyError。"""
        for c in self.categories:
            if c.key == key:
                return c
        raise KeyError(key)


def load_taxonomy(path: str | Path | None = None) -> Taxonomy:
    """加载并校验 taxonomy.yaml，返回结构化 Taxonomy。

    任一不变量违规即抛 TaxonomyError，message 汇总全部问题（不止第一条），
    便于一次性修完。文件不存在抛 TaxonomyError，YAML 语法错误透出 yaml.YAMLError。
    """
    src = Path(path) if path is not None else DEFAULT_TAXONOMY_PATH
    if not src.is_file():
        raise TaxonomyError(f"taxonomy 文件不存在：{src}")

    data = yaml.safe_load(src.read_text(encoding="utf-8"))
    return _validate(data, source=str(src))


def _validate(data: object, *, source: str) -> Taxonomy:
    errors: list[str] = []

    if not isinstance(data, dict):
        raise TaxonomyError(f"{source}: 顶层必须是映射（dict），实际为 {type(data).__name__}")

    raw_categories = data.get("categories")
    if not isinstance(raw_categories, dict):
        raise TaxonomyError(f"{source}: 缺少 categories 映射或其类型非法")

    # 五类齐全 + 无多余类
    missing = [k for k in REQUIRED_CATEGORIES if k not in raw_categories]
    if missing:
        errors.append(f"缺少必需类：{', '.join(missing)}")
    extra = [k for k in raw_categories if k not in REQUIRED_CATEGORIES]
    if extra:
        errors.append(f"出现未知类（不在五大类内）：{', '.join(extra)}")

    seen_ids: dict[str, str] = {}  # id -> 首次出现的类键
    categories: list[Category] = []

    for key in REQUIRED_CATEGORIES:
        raw_cat = raw_categories.get(key)
        if raw_cat is None:
            continue  # 已在 missing 中报告
        if not isinstance(raw_cat, dict):
            errors.append(f"类 '{key}': 必须是映射")
            continue

        raw_patterns = raw_cat.get("patterns")
        if not isinstance(raw_patterns, list):
            errors.append(f"类 '{key}': 缺少 patterns 列表")
            raw_patterns = []

        if len(raw_patterns) < MIN_PATTERNS_PER_CATEGORY:
            errors.append(
                f"类 '{key}': 模式数 {len(raw_patterns)} < 要求的 {MIN_PATTERNS_PER_CATEGORY}"
            )

        patterns: list[Pattern] = []
        for idx, raw in enumerate(raw_patterns):
            pat = _validate_pattern(
                raw, key=key, idx=idx, seen_ids=seen_ids, errors=errors
            )
            if pat is not None:
                patterns.append(pat)

        title = raw_cat.get("title", key)
        categories.append(Category(key=key, title=str(title), patterns=patterns))

    if errors:
        bullet = "\n  - ".join(errors)
        raise TaxonomyError(f"{source}: 分类法校验失败（{len(errors)} 项）：\n  - {bullet}")

    by_id = {p.id: p for c in categories for p in c.patterns}
    version = data.get("version", 1)
    return Taxonomy(
        version=int(version) if isinstance(version, int) else 1,
        categories=categories,
        by_id=by_id,
    )


def _validate_pattern(
    raw: object,
    *,
    key: str,
    idx: int,
    seen_ids: dict[str, str],
    errors: list[str],
) -> Pattern | None:
    loc = f"类 '{key}' 第 {idx} 个模式"
    if not isinstance(raw, dict):
        errors.append(f"{loc}: 必须是映射")
        return None

    pid = raw.get("id")

    # 必填字段齐全且非空
    missing_fields = [
        f for f in REQUIRED_PATTERN_FIELDS if f not in raw or _is_empty(raw[f])
    ]
    if missing_fields:
        ident = pid if isinstance(pid, str) and pid else loc
        errors.append(f"模式 '{ident}': 缺少或为空的字段：{', '.join(missing_fields)}")

    # id 校验：非空字符串、类前缀、全局唯一
    if isinstance(pid, str) and pid:
        if not pid.startswith(f"{key}-"):
            errors.append(f"模式 '{pid}': id 前缀应为 '{key}-'")
        if pid in seen_ids:
            errors.append(
                f"模式 id 重复：'{pid}'（已出现于类 '{seen_ids[pid]}'）"
            )
        else:
            seen_ids[pid] = key

    # device_state_dimensions 必须是字符串列表（允许空列表，如无设备维度的纯导航缺陷）
    dims = raw.get("device_state_dimensions")
    if dims is not None and (
        not isinstance(dims, list) or not all(isinstance(d, str) for d in dims)
    ):
        ident = pid if isinstance(pid, str) and pid else loc
        errors.append(f"模式 '{ident}': device_state_dimensions 必须是字符串列表")

    # 字段不全则不构造对象
    if missing_fields or not isinstance(pid, str) or not pid:
        return None

    return Pattern(
        id=pid,
        name=str(raw["name"]),
        description=str(raw["description"]),
        kotlin_example_before=str(raw["kotlin_example_before"]),
        kotlin_example_after=str(raw["kotlin_example_after"]),
        trigger_scenario=str(raw["trigger_scenario"]),
        expected_failure=str(raw["expected_failure"]),
        device_state_dimensions=list(dims) if isinstance(dims, list) else [],
        category=key,
    )


def _is_empty(value: object) -> bool:
    """device_state_dimensions 允许为空列表；其余字段空字符串/None 视为缺失。"""
    if isinstance(value, list):
        return False
    return value is None or (isinstance(value, str) and value.strip() == "")
