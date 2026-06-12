"""bench/taxonomy — 行为层缺陷分类法（缺陷注入系统的知识核心）。"""

from __future__ import annotations

from .loader import (
    MIN_PATTERNS_PER_CATEGORY,
    REQUIRED_CATEGORIES,
    REQUIRED_PATTERN_FIELDS,
    Category,
    Pattern,
    Taxonomy,
    TaxonomyError,
    load_taxonomy,
)

__all__ = [
    "Category",
    "Pattern",
    "Taxonomy",
    "TaxonomyError",
    "load_taxonomy",
    "MIN_PATTERNS_PER_CATEGORY",
    "REQUIRED_CATEGORIES",
    "REQUIRED_PATTERN_FIELDS",
]
