"""LLM Adapter 子包

公开 API:
    LLMClientAdapter — 原 class 的别名,完全兼容旧 `from llm_adapter import LLMClientAdapter`
    LLMClient        — 新名,供 Step 2+ 的内部代码使用

子模块说明:
    provider          : LLMClient 类(适配器入口)
    config            : ProviderConfig 数据类(Step 5 起承载解析后的 provider 配置)
    registry          : PROFILES + build_client + pick_capable_adapter(Step 2/5 落地)
    quirks            : QuirkAction/QuirkDirective + register_quirk + apply_quirk(Step 4 注册)
    request_builder   : _render 模板渲染 + build_request_kwargs(Step 5 启用)
    response_parser   : extract_reasoning(Step 3 启用)
    constants         : Step 6 起承载模型枚举(SENSENOVA_U1_VALID_SIZES 等)
"""

from .provider import LLMClient

# 向后兼容别名 — server.py / agent.py / analyze_image_content.py 全部继续工作
LLMClientAdapter = LLMClient

# 显式导出常量,供 generate_image 工具 schema 和 early validation 使用
from .constants import SENSENOVA_U1_VALID_SIZES, DEFAULT_IMAGE_MODEL  # noqa: E402

__all__ = [
    "LLMClient",
    "LLMClientAdapter",
    "SENSENOVA_U1_VALID_SIZES",
    "DEFAULT_IMAGE_MODEL",
]
