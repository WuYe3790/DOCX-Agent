"""LLMClient — 模型适配器主类

Step 1 行为说明:
    本文件是旧 src/llm_adapter.py 的"纯搬家"复刻 — __init__ 和
    create_chat_completion 的 if-else 分支原样保留,不改任何行为。
    新增的 has_capability / reasoning_field / quirks / raw_config 是
    Step 2-4 要替换 if-else 用的占位接口,Step 1 给出默认实现以保证
    系统在过渡期能跑。
"""

from __future__ import annotations

import os
import json
import warnings
from pathlib import Path
from openai import OpenAI


# Step 2: provider 名 → 默认 capability 集合(Step 5 升级为完整 PROFILES + auto-migration)
# 注意:这只是 v1 config 的兼容兜底,config.json 的 providers.<name>.capabilities
# 字段会覆盖此表 — 新接入的 provider 在 config 里写 capabilities 即可,不需要改这里。
_DEFAULT_CAPABILITIES: dict[str, frozenset] = {
    "deepseek":  frozenset({"chat", "tools", "reasoning"}),
    "sensenova": frozenset({"chat", "tools", "vision", "reasoning"}),
    "agnes":     frozenset({"chat", "tools", "reasoning"}),
}
_FALLBACK_CAPABILITIES = frozenset({"chat", "tools"})   # 未知 provider 的最低限度


# Step 3: provider 名 → 流式响应 reasoning 字段的 JSONPath
# 同样可被 config.json providers.<name>.reasoning_field 字段覆盖。
# 历史:旧 agent.py:458-464 用 if-else 在每个 chunk 上判断,Step 3 集中到这里。
_DEFAULT_REASONING_FIELDS: dict[str, str] = {
    "deepseek":  "delta.reasoning_content",        # OpenAI 标准字段
    "sensenova": "delta.model_extra.reasoning",    # 商汤专有扩展(走 model_extra)
    "agnes":     "delta.reasoning_content",        # 用 OpenAI 标准
}
_FALLBACK_REASONING_FIELD = "delta.reasoning_content"   # OpenAI 通用兼容


# Step 4: provider 名 → 默认启用的 quirks tuple
# 同样可被 config.json providers.<name>.quirks 字段覆盖(空列表也算覆盖,显式禁用所有 quirk)。
# 历史:旧 agent.py:540-561 直接 inline 检查 sensenova 行为,Step 4 抽成命名 quirk。
_DEFAULT_QUIRKS: dict[str, tuple] = {
    "sensenova": ("stream_empty_retry",),   # 复现 session-20260609-205746
}
_FALLBACK_QUIRKS: tuple = ()


# Step 5: provider 名 → 请求注入字段的默认表(消灭 create_chat_completion 的 if-else)
# 三个字段共同决定一个 provider 的请求"形状":
#   - extra_body_template: JSON 模板,${var} 占位由 _render 渲染;为 None 时不注入 extra_body
#   - top_level_kwargs:    要塞到 chat.completions.create 顶层的 kwarg map(值可为 ${var} 模板)
#   - forward_tool_choice: 是否透传 caller 的 tool_choice kwarg
# 这三个字段都可在 config.json providers.<name>.{extra_body_template,top_level_kwargs,
# forward_tool_choice} 显式覆盖默认表。
# extra_body 仅在 thinking != "disabled" 时注入(与旧行为一致)。
_DEFAULT_EXTRA_BODY_TEMPLATES: dict[str, str] = {
    "deepseek": '{"thinking": {"type": "${thinking}"}}',
    "agnes":    '{"chat_template_kwargs": {"enable_thinking": true}}',
    # sensenova 不需要 extra_body(reasoning_effort 走顶层)
}
_DEFAULT_TOP_LEVEL_KWARGS: dict[str, dict] = {
    "sensenova": {"reasoning_effort": "${reasoning_effort}"},
}
_DEFAULT_FORWARD_TOOL_CHOICE: dict[str, bool] = {
    "sensenova": True,
    "agnes":     True,
    # deepseek 不在表里 → 默认 False(与旧 if-else 一致:deepseek 分支不处理 tool_choice)
    # (但 caller 的 tool_choice 仍会走最后的 kwarg 透传,行为不变)
}


class LLMClient:
    """模型适配层:统一管理不同大模型服务商(如 DeepSeek, SenseNova, Agnes)的连接与调用细节。"""

    def __init__(self, config_path=None, *, provider_override: str | None = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config.json"
        else:
            config_path = Path(config_path)
        self._config_path = config_path           # Step 2: 供 pick_capable_adapter 重新构造用

        # 1. 加载 config.json
        self.config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"警告: 加载配置文件 {config_path} 失败: {e}")

        # 2. 判定 provider
        # 优先级: provider_override(显式参数) -> 环境变量 LLM_PROVIDER -> config.json 的 provider 字段
        #        -> 根据旧版 root-level 配置自动判定 -> 默认 deepseek
        self.provider = (
            provider_override
            or os.getenv("LLM_PROVIDER")
            or self.config.get("provider")
        )

        top_api_key = self.config.get("api_key")
        top_base_url = self.config.get("base_url")

        if not self.provider:
            # Step 6: base_url 子串启发式已 deprecated — 显式声明 "provider" 字段
            if top_base_url and ("sensenova" in top_base_url
                                  or "agnes" in top_base_url
                                  or "deepseek" in top_base_url):
                warnings.warn(
                    "通过 base_url 子串(sensenova/agnes/deepseek)推断 provider 已 deprecated。"
                    "请在 config.json 顶层显式声明 \"provider\" 字段(参考 src/config.example.json)。",
                    DeprecationWarning,
                    stacklevel=2,
                )
            if top_base_url and "sensenova" in top_base_url:
                self.provider = "sensenova"
            elif top_base_url and "agnes" in top_base_url:
                self.provider = "agnes"
            elif top_base_url and "deepseek" in top_base_url:
                self.provider = "deepseek"
            else:
                self.provider = "deepseek"  # 默认降级为 deepseek

        # 3. 提取所选提供商的具体配置
        provider_config = {}
        if "providers" in self.config and self.provider in self.config["providers"]:
            provider_config = self.config["providers"][self.provider]

        # 初始化配置参数
        self.api_key = None
        self.base_url = None
        self.model = None
        self.thinking_type = None
        self.reasoning_effort = None

        if self.provider == "deepseek":
            self.api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("LLM_BASE_URL")
            self.model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
            self.thinking_type = os.getenv("DOCX_AGENT_THINKING")

            self.api_key = self.api_key or provider_config.get("api_key")
            self.base_url = self.base_url or provider_config.get("base_url")
            self.model = self.model or provider_config.get("model")
            if self.thinking_type is None:
                self.thinking_type = provider_config.get("thinking")

            if not provider_config:
                self.api_key = self.api_key or top_api_key
                self.base_url = self.base_url or top_base_url
                # Step 6: flat config(顶层 api_key/base_url 无 providers 嵌套块)已 deprecated。
                # deepseek 是默认 provider,大多数旧 flat config 都走这里,warning 在此处触发足够。
                if top_api_key or top_base_url:
                    warnings.warn(
                        "顶层 api_key/base_url 的 flat config 已 deprecated;"
                        "请改用 providers.<name>.{api_key,base_url,model} 嵌套结构"
                        "(参考 src/config.example.json)。",
                        DeprecationWarning,
                        stacklevel=2,
                    )
            self.base_url = self.base_url or "https://api.deepseek.com"
            self.model = self.model or "deepseek-v4-flash"
            if self.thinking_type is None:
                self.thinking_type = "enabled"

        elif self.provider == "sensenova":
            self.api_key = os.getenv("SENSENOVA_API_KEY") or os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("SENSENOVA_BASE_URL") or os.getenv("LLM_BASE_URL")
            self.model = os.getenv("LLM_MODEL")
            self.reasoning_effort = os.getenv("SENSENOVA_REASONING_EFFORT") or os.getenv("LLM_REASONING_EFFORT")

            self.api_key = self.api_key or provider_config.get("api_key")
            self.base_url = self.base_url or provider_config.get("base_url")
            self.model = self.model or provider_config.get("model")
            self.reasoning_effort = self.reasoning_effort or provider_config.get("reasoning_effort")

            if not provider_config and top_base_url and "sensenova" in top_base_url:
                self.api_key = self.api_key or top_api_key
                self.base_url = self.base_url or top_base_url

            self.base_url = self.base_url or "https://token.sensenova.cn/v1"
            self.model = self.model or "sensenova-6.7-flash-lite"
            self.thinking_type = "disabled"  # 商汤不需要 DeepSeek-style thinking extra_body

        elif self.provider == "agnes":
            # Agnes-2.0-Flash (Sapiens AI, OpenAI 兼容, 现价免费)
            # thinking 注入方式: extra_body={"chat_template_kwargs": {"enable_thinking": True}}
            self.api_key = os.getenv("AGNES_API_KEY") or os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("AGNES_BASE_URL") or os.getenv("LLM_BASE_URL")
            self.model = os.getenv("AGNES_MODEL") or os.getenv("LLM_MODEL")
            self.thinking_type = os.getenv("AGNES_THINKING") or os.getenv("DOCX_AGENT_THINKING")

            self.api_key = self.api_key or provider_config.get("api_key")
            self.base_url = self.base_url or provider_config.get("base_url")
            self.model = self.model or provider_config.get("model")
            if self.thinking_type is None:
                self.thinking_type = provider_config.get("thinking", "enabled")

            if not provider_config and top_base_url and "agnes" in top_base_url:
                self.api_key = self.api_key or top_api_key
                self.base_url = self.base_url or top_base_url

            self.base_url = self.base_url or "https://apihub.agnes-ai.com/v1"
            self.model = self.model or "agnes-2.0-flash"
            if self.thinking_type is None:
                self.thinking_type = "enabled"  # 默认开启 thinking (probe 验证有效)

        else:
            # 通用 OpenAI 兼容配置
            self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY") or top_api_key
            self.base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or top_base_url
            self.model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")

            self.api_key = self.api_key or provider_config.get("api_key")
            self.base_url = self.base_url or provider_config.get("base_url")
            self.model = self.model or provider_config.get("model")

            self.base_url = self.base_url or "https://api.openai.com/v1"
            self.model = self.model or "gpt-4o"
            # Step 5: 从 provider block 读 thinking / reasoning_effort,让 v2 config 对新接入
            # OpenAI 兼容 provider 也能用 extra_body_template / top_level_kwargs 模板渲染。
            # 旧行为:未知 provider 硬编码 thinking="disabled",reasoning_effort=None — 这是限制,
            # 不是契约。修复后已知 3 个 provider 的行为不变(它们走 if/elif 分支),只放宽未知 provider。
            self.thinking_type = provider_config.get("thinking", "disabled")
            self.reasoning_effort = self.reasoning_effort or provider_config.get("reasoning_effort")

        # 检查 api_key 是否存在
        if not self.api_key:
            raise RuntimeError(
                f"未设置 LLM API Key。请设置相应的环境变量(如 {self.provider.upper()}_API_KEY)"
                f"或在 config.json 中配置该提供商的 api_key。"
            )

        # 4. 创建 OpenAI 客户端
        timeout = float(self.config.get("timeout_seconds", 300))
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=0,
        )

        # 5. Step 2: 解析 capabilities
        # 优先级:provider block 显式声明 > _DEFAULT_CAPABILITIES 默认表 > _FALLBACK_CAPABILITIES
        # 新接入 provider 在 config.json 写 "capabilities": [...] 即可,不必改代码。
        provider_block = (self.config.get("providers") or {}).get(self.provider) or {}
        if "capabilities" in provider_block:
            self._capabilities = frozenset(provider_block["capabilities"])
        else:
            self._capabilities = _DEFAULT_CAPABILITIES.get(self.provider, _FALLBACK_CAPABILITIES)

        # 6. Step 3: 解析 reasoning_field
        # 优先级:provider block 显式 "reasoning_field" > _DEFAULT_REASONING_FIELDS > _FALLBACK
        # __init__ 阶段算一次缓存,property 直接 return — agent.py 流式循环每 chunk 查一次,需热路径性能。
        self._reasoning_field = (
            provider_block.get("reasoning_field")
            or _DEFAULT_REASONING_FIELDS.get(self.provider, _FALLBACK_REASONING_FIELD)
        )

        # 7. Step 4: 解析 quirks
        # 优先级:provider block 显式 "quirks"(即使空列表 = 显式禁用) > _DEFAULT_QUIRKS > 空 tuple
        # 显式空列表的语义:用户明确告诉系统"这个 provider 不要启用任何 quirk"
        # (例如关掉 sensenova 的 stream_empty_retry 自查问题来源)。
        if "quirks" in provider_block:
            self._quirks = tuple(provider_block["quirks"])
        else:
            self._quirks = _DEFAULT_QUIRKS.get(self.provider, _FALLBACK_QUIRKS)

        # 8. Step 5: 解析请求注入三件套(extra_body_template / top_level_kwargs / forward_tool_choice)
        # 同 capabilities/quirks 模式:provider block 显式 > _DEFAULT_* 表 > 空/False
        self._extra_body_template = (
            provider_block.get("extra_body_template")
            or _DEFAULT_EXTRA_BODY_TEMPLATES.get(self.provider)
        )
        if "top_level_kwargs" in provider_block:
            self._top_level_kwargs = dict(provider_block["top_level_kwargs"])
        else:
            self._top_level_kwargs = dict(_DEFAULT_TOP_LEVEL_KWARGS.get(self.provider, {}))
        if "forward_tool_choice" in provider_block:
            self._forward_tool_choice = bool(provider_block["forward_tool_choice"])
        else:
            self._forward_tool_choice = _DEFAULT_FORWARD_TOOL_CHOICE.get(self.provider, False)

    # ────────────────────────── 公开 getter(旧接口,保留) ──────────────────────────

    def get_model_name(self) -> str:
        """获取当前激活的模型名称"""
        return self.model

    def get_thinking_type(self):
        """获取当前的 thinking 类型配置(仅用于 DeepSeek/Agnes 兼容性)"""
        return self.thinking_type

    def get_provider(self) -> str:
        """获取当前所使用的提供商"""
        return self.provider

    def get_reasoning_effort(self):
        """获取当前商汤模型的推理强度"""
        return self.reasoning_effort

    # ────────────────────────── 新增占位接口(Step 2-4 替换 if-else 用) ──────────────────────────

    def has_capability(self, capability: str) -> bool:
        """是否具备某能力(chat/tools/vision/reasoning)。

        Step 2 实现:读 self._capabilities,它在 __init__ 阶段一次性解析:
          1. config.json providers.<name>.capabilities 显式声明优先
          2. 否则用 _DEFAULT_CAPABILITIES 表(deepseek/sensenova/agnes 三家)
          3. 都没有则用 _FALLBACK_CAPABILITIES = {"chat","tools"}

        Step 5 把默认表升级为完整 PROFILES + auto-migration,语义不变。
        """
        return capability in self._capabilities

    @property
    def reasoning_field(self) -> str:
        """响应流 reasoning 字段的 JSONPath。Step 3 实现:

          1. config.json providers.<name>.reasoning_field 显式声明优先
          2. 否则用 _DEFAULT_REASONING_FIELDS 表(deepseek/agnes→delta.reasoning_content,
             sensenova→delta.model_extra.reasoning)
          3. 都没有则用 _FALLBACK_REASONING_FIELD = "delta.reasoning_content"(OpenAI 标准)

        实例属性 self._reasoning_field 在 __init__ 算一次缓存 — agent.py 流式循环
        每 chunk 都查一次,property 不能含 dict 查找/getattr 链。
        """
        return self._reasoning_field

    @property
    def quirks(self) -> tuple:
        """启用的 quirk 名 tuple。Step 4 实现:

          1. config.json providers.<name>.quirks 显式声明优先(空列表 = 显式禁用所有)
          2. 否则用 _DEFAULT_QUIRKS 表(sensenova → stream_empty_retry,其他无)
          3. 都没有则空 tuple

        实例属性 self._quirks 在 __init__ 缓存。agent.py 流式循环每轮检查一次,
        property 直接 return 避免重复 dict 查找。
        """
        return self._quirks

    @property
    def extra_body_template(self):
        """Step 5: extra_body 的 JSON 模板(${var} 占位由 _render 渲染)。

        优先级:provider block "extra_body_template" > _DEFAULT_EXTRA_BODY_TEMPLATES > None
        None 时表示该 provider 不需要注入 extra_body。
        约定:只在 thinking != "disabled" 时实际注入(与旧行为一致)。
        """
        return self._extra_body_template

    @property
    def top_level_kwargs(self) -> dict:
        """Step 5: 注入到 chat.completions.create 顶层的 kwarg map。值可为 ${var} 模板。

        优先级:provider block "top_level_kwargs" > _DEFAULT_TOP_LEVEL_KWARGS > {}
        典型用法:sensenova {"reasoning_effort": "${reasoning_effort}"}
        """
        return self._top_level_kwargs

    @property
    def forward_tool_choice(self) -> bool:
        """Step 5: 是否透传 caller 的 tool_choice kwarg。

        优先级:provider block "forward_tool_choice" > _DEFAULT_FORWARD_TOOL_CHOICE > False
        注意:即使返回 False,caller 的 tool_choice 仍会走 build_request_kwargs 最后的
        kwarg 透传循环(与旧 if-else 行为一致 — deepseek 没专门处理但 caller 传入仍透传)。
        """
        return self._forward_tool_choice

    @property
    def raw_config(self) -> dict:
        """返回原始 config.json 字典。给 registry.pick_capable_adapter 用,
        不应该被工具层(basic_tools/*)直接读取。"""
        return self.config

    @property
    def config_path(self) -> Path:
        """返回 config.json 的路径(Path 对象)。给 registry.pick_capable_adapter
        重新构造同 config 下不同 provider 的 LLMClient 用。"""
        return self._config_path

    # ────────────────────────── 请求构建(Step 5: 数据驱动,消灭 if-else) ──────────────────────────

    def create_chat_completion(self, messages, tools=None, **kwargs):
        """创建对话补全。

        Step 5: 通过 build_request_kwargs 数据驱动构造 — 注入逻辑由 3 个 property
        (extra_body_template / top_level_kwargs / forward_tool_choice) 决定,
        provider-specific if-else 已彻底消灭。新接入 OpenAI 兼容模型只需在
        config.json 写 4 行(api_key / base_url / model / 可选 capabilities),
        其余字段从 _DEFAULT_* 表或 profile 默认值得来。
        """
        from .request_builder import build_request_kwargs  # 延迟 import 避免循环依赖
        req = build_request_kwargs(self, messages, tools, **kwargs)
        return self.client.chat.completions.create(**req)

    # ────────────────────────── 内部辅助(Step 1 parity 测试用) ──────────────────────────

    def _build_request_kwargs(self, messages, tools=None, **kwargs) -> dict:
        """暴露请求 kwargs 构建过程供回归测试比对。不发起真实 API 调用。

        Step 5 后:这是 build_request_kwargs 的薄包装,parity 测试因此能验证
        "数据驱动版与旧 _llm_adapter_legacy 的 if-else 版字节级一致"。
        """
        from .request_builder import build_request_kwargs
        return build_request_kwargs(self, messages, tools, **kwargs)
