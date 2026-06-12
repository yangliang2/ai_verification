"""LLM 输出解析公共工具。"""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json_block(text: str) -> str:
    """从 LLM 响应中提取 JSON 文本，容忍 markdown 代码块包裹。

    处理情形：纯 JSON、```json ... ``` 包裹、``` ... ``` 无语言标记包裹。
    """
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()
