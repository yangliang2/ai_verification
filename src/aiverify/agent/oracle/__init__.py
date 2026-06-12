"""Oracle 判定层：L1（廉价信号）/ L2（状态断言）/ L3（LLM 语义判定）。

分层判定原则：L1 廉价信号先行，L2 状态断言次之，
L3 LLM 语义判定仅在前两层均返回 inconclusive 时介入。

所有层产出的 verdict dict 均符合 verdict_schema.json（冻结版）。
"""

from aiverify.agent.oracle.schema import (
    VerdictValidationError,
    get_schema,
    self_validate_schema,
    validate_verdict,
)
from aiverify.agent.oracle.l1 import L1Oracle
from aiverify.agent.oracle.l2 import L2Oracle, Assertion
from aiverify.agent.oracle.l3 import L3Oracle

__all__ = [
    "Assertion",
    "L1Oracle",
    "L2Oracle",
    "L3Oracle",
    "VerdictValidationError",
    "get_schema",
    "self_validate_schema",
    "validate_verdict",
]
