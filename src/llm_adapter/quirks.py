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


# ────────────────────────── 已注册 quirks ──────────────────────────

@register_quirk("stream_empty_retry")
def _stream_empty_retry(ctx: dict) -> QuirkDirective:
    """SenseNova 偶发流静默关闭:finish_reason=None + 空 tool_calls。

    复现:session-20260609-205746 第 13/14 轮(reasoning-only 死循环)。
    历史:旧 agent.py:540-561 用 inline if-else 处理,Step 4 抽到这里。

    职责边界:
    - 本函数只判断"这一轮响应是否应该 retry",返回 QuirkDirective
    - retry budget 计数 + 日志 + continue 重发请求 → 仍归 agent 管(全局预算)

    ctx 字段(由 agent.py 传入):
      - finish_reason: server 给的 finish_reason 值(可能 None)
      - tool_calls_map: 本轮累积的 tool_calls 字典
      - accumulated_content: 本轮累积的 content 字符串
      - accumulated_reasoning: 本轮累积的 reasoning 字符串

    返回:
      - RETRY_REQUEST + reason="stream_incomplete":检测到静默关闭,建议 retry
      - CONTINUE:正常路径,不做特殊处理
    """
    if ctx["finish_reason"] is None and not ctx["tool_calls_map"]:
        return QuirkDirective(QuirkAction.RETRY_REQUEST, reason="stream_incomplete")
    return QuirkDirective(QuirkAction.CONTINUE)
