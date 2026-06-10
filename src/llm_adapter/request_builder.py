"""请求 kwargs 构建器 — 把 LLMClient 的声明性字段翻译成 chat.completions.create 参数

Step 5 落地 build_request_kwargs:从 LLMClient 的 3 个 property
(extra_body_template / top_level_kwargs / forward_tool_choice) 数据驱动地组装
请求 kwargs,消灭 create_chat_completion 里最后的 provider if-else。

Step 1 落地 _render 模板渲染(Review #3:JSON-escape 防止特殊字符破坏 extra_body)。
"""

from __future__ import annotations

import json
import re


_PLACEHOLDER_RE = re.compile(r"\$\{(\w+)\}")


def _render(template: str, ctx: dict) -> str:
    """把模板里 ${name} 替换成 ctx[name],并做 JSON-escape(Review #3)。

    安全性:用 json.dumps 把替换值序列化为 JSON 字符串字面量(带外层引号),
    然后剥掉外层引号 — 剩下的部分就是合法的 JSON 字符串内容,可以安全
    嵌入到 "..." 字符串字面量上下文。

    用法约定:占位符必须出现在模板的字符串字面量上下文(即外层有引号),
    例如 `"type": "${thinking}"`。不要在数字/布尔/对象位置使用占位符。

    示例:
        >>> _render('{"type": "${x}"}', {"x": "enabled"})
        '{"type": "enabled"}'
        >>> _render('{"type": "${x}"}', {"x": 'a"b'})           # 特殊字符自动转义
        '{"type": "a\\"b"}'
        >>> json.loads(_render('{"type": "${x}"}', {"x": 'a"b'}))
        {'type': 'a"b'}
    """
    def _escape(value) -> str:
        # json.dumps("foo") -> '"foo"';取 [1:-1] 剥掉外层引号
        # 这样 \"、\\、\n、\u 等转义全部由 json 库正确处理
        return json.dumps(str(value))[1:-1]

    return _PLACEHOLDER_RE.sub(
        lambda m: _escape(ctx.get(m.group(1), "")),
        template,
    )


def build_request_kwargs(client, messages, tools=None, **kwargs) -> dict:
    """根据 client 的声明性配置构造 chat.completions.create 的 kwargs。

    输出 = (model + messages + tools)  +  注入(top_level + tool_choice + extra_body)
         + caller kwargs 兜底透传(setdefault 语义,不覆盖已有键)

    与旧 create_chat_completion 的 if-else 行为字节级一致 — 由
    tests/test_llm_adapter_step1_parity.py 验证(新版 _build_request_kwargs
    走本函数,与 _llm_adapter_legacy 对比)。

    上下文变量(供 ${var} 模板渲染):
      - thinking         : client.get_thinking_type() 或 "disabled"
      - reasoning_effort : caller kwarg 优先,然后 client.get_reasoning_effort(),默认 ""
      - model            : client.get_model_name()
    """
    req = {"model": client.get_model_name(), "messages": messages}
    if tools:
        req["tools"] = tools

    # 上下文 — caller kwarg 优先(允许调用时临时覆盖)
    thinking = client.get_thinking_type() or "disabled"
    reasoning_effort = kwargs.get("reasoning_effort") or client.get_reasoning_effort() or ""
    ctx = {
        "thinking": thinking,
        "reasoning_effort": reasoning_effort,
        "model": client.get_model_name(),
    }

    # 1. top_level_kwargs(渲染后用 setdefault,不覆盖 req 已有键)
    for k, v in client.top_level_kwargs.items():
        rendered = _render(v, ctx) if isinstance(v, str) else v
        if rendered != "":      # 空字符串 = ${var} 未提供,跳过(与旧 `if reasoning_effort:` 一致)
            req.setdefault(k, rendered)

    # 2. tool_choice 显式透传(provider 声明 forward_tool_choice 时)
    if client.forward_tool_choice and "tool_choice" in kwargs:
        req["tool_choice"] = kwargs["tool_choice"]

    # 3. extra_body — 仅在有模板且 thinking != "disabled" 时注入(与旧 if-else 一致)
    # 渲染后用 json.loads 校验合法性 — 配置错误立刻显式失败
    if client.extra_body_template and thinking != "disabled":
        rendered_json = _render(client.extra_body_template, ctx)
        req["extra_body"] = json.loads(rendered_json)

    # 4. 兜底透传 caller kwargs(不覆盖已有键)— 保留旧 llm_adapter.py:208-210 行为
    for k, v in kwargs.items():
        if k not in req:
            req[k] = v

    return req
