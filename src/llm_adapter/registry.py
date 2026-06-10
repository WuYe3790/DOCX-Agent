"""Provider Profiles 注册表 + 客户端工厂 + capability fallback

Step 5 落地 PROFILES + build_client + auto-migration 表。
Step 2 落地 pick_capable_adapter 的真实实现。
Step 1 仅留签名 + NotImplementedError 占位,避免上层 import 失败。
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import LLMClient


# Step 5 会填充:openai_compatible / anthropic_compatible / ...
PROFILES: dict[str, dict] = {}


def build_client(config: dict, override_provider: Optional[str] = None) -> "LLMClient":
    """从 config dict 构造 LLMClient。Step 5 落地完整实现(含 PROFILES 继承 + auto-migration)。

    Step 1 占位:抛 NotImplementedError。当前所有 import 路径仍走 LLMClient() 构造函数。
    """
    raise NotImplementedError("build_client 在 Step 5 落地;Step 1-4 仍用 LLMClient() 直接构造")


def pick_capable_adapter(current: "LLMClient", capability: str) -> Optional["LLMClient"]:
    """若 current 不具备 capability,从 config 里挑第一个有该 capability 的 provider,
    返回为它构建的新 LLMClient;都没有则返回 None。

    Review #2 落地的"工厂"接口 — 把 fallback 选择权从 tool 层收回 adapter 层。
    Step 2 落地完整实现(走 PROFILES + has_capability)。
    """
    raise NotImplementedError("pick_capable_adapter 在 Step 2 落地")
