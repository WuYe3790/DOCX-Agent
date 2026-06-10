"""Quirk 注册表 — provider 的"不守规矩"行为(代码做,配置触发)

Review #1 落地点:返回值用 Enum + dataclass,避免 agent.py 解析无类型 dict。

Step 4 才把 @register_quirk("stream_empty_retry") 装上 + 接入 agent.py 流式循环。
Step 1 提供完整的注册框架 + Enum/dataclass,但 QUIRKS 字典暂为空。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


class QuirkAction(Enum):
    """Quirk 指令的可选动作。agent.py 用 == 比较,不要用 .value。"""
    CONTINUE = auto()        # 当前 chunk/round 不触发任何特殊处理,按正常流程走
    RETRY_REQUEST = auto()   # 重新发起整轮 LLM 请求(consume retry budget)


@dataclass(frozen=True)
class QuirkDirective:
    """Quirk 评估后给上层的指令。frozen 保证 agent.py 不能误改。"""
    action: QuirkAction
    reason: str = ""


# 注册表 — quirk 名 → 评估函数(ctx → QuirkDirective)
QUIRKS: dict[str, Callable[[dict], QuirkDirective]] = {}


def register_quirk(name: str):
    """装饰器:把一个 quirk 实现注册到名字下。

    Step 4 会用 @register_quirk("stream_empty_retry") 装饰 stream_empty_retry 函数。
    """
    def decorator(fn: Callable[[dict], QuirkDirective]):
        if name in QUIRKS:
            raise RuntimeError(f"Quirk '{name}' 已注册;重复注册可能是 import 路径混乱")
        QUIRKS[name] = fn
        return fn
    return decorator


def apply_quirk(name: str, ctx: dict) -> QuirkDirective:
    """按名调用 quirk。未知名 → 显式抛错,避免静默忽略配置错误。"""
    if name not in QUIRKS:
        raise RuntimeError(
            f"Unknown quirk '{name}'. Registered: {sorted(QUIRKS) or '(none yet)'}"
        )
    return QUIRKS[name](ctx)
