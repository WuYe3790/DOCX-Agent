"""Provider Profiles 注册表 + 客户端工厂 + capability fallback

Step 5 落地 PROFILES(documentation 性质) + build_client 公开工厂。
Step 2 落地 pick_capable_adapter 的完整实现。

关于 PROFILES:
    Plan 原设计 PROFILES 是 "provider block 继承默认值" 的运行时机制。
    实际实现中,provider.py 的 _DEFAULT_CAPABILITIES / _DEFAULT_REASONING_FIELDS /
    _DEFAULT_QUIRKS / _DEFAULT_EXTRA_BODY_TEMPLATES / _DEFAULT_TOP_LEVEL_KWARGS /
    _DEFAULT_FORWARD_TOOL_CHOICE 这 6 个表 + fallback 已经提供了等价能力 —
    未知 provider 自动得到 OpenAI 兼容的合理默认。

    因此 PROFILES 在这里是 **v2 config schema 的引导文档**:声明"openai_compatible"
    profile 是合法值,让用户写 v2 config 时知道可以这样写。
    LLMClient.__init__ 不强制读 profile 字段 — provider block 不显式声明
    的字段会通过 _DEFAULT_* 表 fallback,等价于 "openai_compatible" 默认。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import LLMClient


PROFILES: dict[str, dict] = {
    # v2 config schema 的合法 profile 名(documentation 性质)
    # 字段值反映 provider.py 的 _DEFAULT_* fallback,作为 "OpenAI 兼容" 默认行为文档
    "openai_compatible": {
        "capabilities": ["chat", "tools"],
        "reasoning_field": "delta.reasoning_content",
        "forward_tool_choice": False,
        "quirks": [],
        "extra_body_template": None,
        "top_level_kwargs": {},
    },
}


def build_client(config: dict, override_provider: Optional[str] = None) -> "LLMClient":
    """从 config dict 构造 LLMClient(Step 5 公开工厂)。

    用法:不想先把 config 写到文件就能构造 client,例如未来从远程配置中心拉取 dict
    后立即构造。pick_capable_adapter 在 Step 2 仍走 LLMClient(config_path, ...) 直接路径,
    因为它已经有 config_path。

    实现:写临时 config.json 到 tempdir,然后 LLMClient(tmp_path, provider_override=...)。
    这绕过对 LLMClient.__init__ 的入侵性改动(加 config_data 参数会触发整套测试重跑),
    用稳定 API 包装。

    Args:
        config: 完整的 config dict(含 "provider" 顶层字段和 "providers" 嵌套块)
        override_provider: 显式指定 active provider,覆盖 config["provider"]
    Returns:
        LLMClient 实例
    """
    from .provider import LLMClient
    tmp_path = Path(tempfile.mkdtemp(prefix="docx_agent_buildclient_")) / "config.json"
    tmp_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return LLMClient(str(tmp_path), provider_override=override_provider)


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
