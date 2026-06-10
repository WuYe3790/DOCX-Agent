"""请求 kwargs 构建器 — 把 ProviderConfig 翻译成 chat.completions.create 参数

Step 5 落地 build_request_kwargs(cfg, messages, tools, **kwargs)。
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
