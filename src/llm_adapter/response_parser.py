"""响应解析 — 把流式 chunk 翻译成 provider 无关的字段

Step 3 启用 extract_reasoning,替换 agent.py:461-464 的硬编码 if-else。
Step 1 提供完整函数,但 agent.py 还没切过来。
"""

from __future__ import annotations

from typing import Optional


_DEFAULT_PATH = "delta.reasoning_content"
_SENSENOVA_PATH = "delta.model_extra.reasoning"


def extract_reasoning(delta, reasoning_field: str) -> Optional[str]:
    """按 reasoning_field 指定的 JSONPath 从 delta 提取 reasoning 文本。

    支持的路径:
        - delta.reasoning_content       (DeepSeek / Agnes — 默认)
        - delta.model_extra.reasoning   (SenseNova)
        - 通用 dotted-path 兜底(例如未来新 provider 自定义路径)

    返回 None 当字段不存在或值不是字符串。
    """
    # 快路径:两个已知值直接用 getattr,免去字符串拆分开销
    if reasoning_field == _DEFAULT_PATH:
        return getattr(delta, "reasoning_content", None)

    if reasoning_field == _SENSENOVA_PATH:
        extra = getattr(delta, "model_extra", None)
        if isinstance(extra, dict):
            v = extra.get("reasoning")
            return v if isinstance(v, str) else None
        return None

    # 通用 dotted-path
    cur = delta
    for part in reasoning_field.split("."):
        if part == "delta":
            continue
        nxt = getattr(cur, part, None)
        if nxt is None and isinstance(cur, dict):
            nxt = cur.get(part)
        if nxt is None:
            return None
        cur = nxt
    return cur if isinstance(cur, str) else None
