"""verdict schema 加载与校验工具。

verdict_schema.json 是 Phase 3 按模式归因分析的数据契约，本阶段冻结。
所有 oracle 层（L1/L2/L3）产出的 verdict dict 须经 validate_verdict() 自验后才允许返回。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).parent / "verdict_schema.json"

# 模块级单例：避免重复 IO
_SCHEMA: dict[str, Any] | None = None
_VALIDATOR: Draft202012Validator | None = None


def _load_schema() -> dict[str, Any]:
    """加载并缓存 verdict schema。"""
    global _SCHEMA, _VALIDATOR
    if _SCHEMA is None:
        with _SCHEMA_PATH.open(encoding="utf-8") as fh:
            _SCHEMA = json.load(fh)
        _VALIDATOR = Draft202012Validator(_SCHEMA)
    return _SCHEMA


def get_schema() -> dict[str, Any]:
    """返回冻结的 verdict schema dict（供外部只读引用）。"""
    return _load_schema()


class VerdictValidationError(Exception):
    """verdict dict 不符合冻结 schema 时抛出。"""


def validate_verdict(verdict: dict[str, Any]) -> None:
    """校验 verdict dict 是否符合冻结 schema。

    不符合时抛出 VerdictValidationError，包含 jsonschema 原始错误信息。
    所有 oracle 层（L1/L2/L3）在返回判定前必须调用本函数自验。
    """
    _load_schema()
    assert _VALIDATOR is not None
    errors = list(_VALIDATOR.iter_errors(verdict))
    if errors:
        messages = "; ".join(e.message for e in errors)
        raise VerdictValidationError(
            f"verdict 不符合冻结 schema：{messages}"
        )


def self_validate_schema() -> None:
    """用 Draft 2020-12 元校验器自验 verdict_schema.json 本身。

    在测试/CI 中调用，确认 schema 文件格式合规。
    """
    schema = _load_schema()
    meta_validator = Draft202012Validator(
        Draft202012Validator.META_SCHEMA  # type: ignore[attr-defined]
    )
    errors = list(meta_validator.iter_errors(schema))
    if errors:
        messages = "; ".join(e.message for e in errors)
        raise VerdictValidationError(
            f"verdict_schema.json 未通过 Draft 2020-12 元校验：{messages}"
        )
