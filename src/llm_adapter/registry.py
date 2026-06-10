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
    """若 current 已具备 capability → 直接返回 current(零开销);否则从 config.providers
    里找第一个有该 capability 的 provider,用 LLMClient(config_path, provider_override=name)
    构造新 client 返回;都没有则返回 None。

    Review #2 落地的"工厂"接口 — 把 fallback 选择权从 tool 层收回 adapter 层:
    - tool 层(basic_tools/*) 只调这个函数,不再直接读 raw_config
    - 不再 mutate os.environ["LLM_PROVIDER"](旧 analyze_image_content.py:51-59 的反模式)
    - 候选 provider 缺 api_key 等导致构造失败时,静默跳过试下一个

    Step 2 实现:基于 LLMClient 自带的 capability 解析(provider block 显式 > _DEFAULT_CAPABILITIES)
    去测试每个候选 provider。Step 5 升级为完整 PROFILES + auto-migration 后,
    此函数语义不变。
    """
    # 延迟 import — 避免 registry.py 顶层 import provider.py 触发循环依赖
    from .provider import LLMClient

    # 1. 自己已经具备 → 直接返回
    if current.has_capability(capability):
        return current

    # 2. 遍历 config 里其他 provider,找第一个有该 capability 的
    cfg = current.raw_config
    config_path = current.config_path
    current_name = current.get_provider()
    for name, _block in (cfg.get("providers") or {}).items():
        if name == current_name:
            continue   # 已在第 1 步排除
        try:
            candidate = LLMClient(config_path, provider_override=name)
        except RuntimeError:
            # 候选 provider 缺 api_key / 配置不完整 → 静默跳过,试下一个
            continue
        if candidate.has_capability(capability):
            return candidate

    return None
