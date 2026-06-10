"""ProviderConfig 数据类 + 配置加载/合并

Step 5 落地实质内容。Step 1 仅放骨架,让其他模块可以 import 类型符号
而不引起循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProviderConfig:
    """解析合并后的 provider 配置(profile 继承已 resolve)。

    Step 5 才会被 build_client 实际构造并注入 LLMClient。
    Step 1 仅作为类型符号存在。
    """
    name: str
    api_key: str
    base_url: str
    model: str
    extra_body_template: Optional[str] = None
    top_level_kwargs: dict = field(default_factory=dict)
    forward_tool_choice: bool = False
    reasoning_field: str = "delta.reasoning_content"
    capabilities: frozenset = field(default_factory=frozenset)
    quirks: tuple = ()
    defaults: dict = field(default_factory=dict)   # thinking / reasoning_effort 等模板上下文
    raw: dict = field(default_factory=dict)        # 原始 block,留给 logging
