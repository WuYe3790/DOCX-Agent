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
            self.thinking_type = "disabled"

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
        """响应流 reasoning 字段的 JSONPath。Step 3 会改成读 cfg.reasoning_field。

        Step 1 占位实现:按 provider 返回旧 agent.py:461-464 的硬编码路径。
        """
        if self.provider == "sensenova":
            return "delta.model_extra.reasoning"
        return "delta.reasoning_content"

    @property
    def quirks(self) -> tuple:
        """启用的 quirk 名列表。Step 4 会改成读 cfg.quirks。

        Step 1 占位实现:返回空 tuple,行为完全由 agent.py 现有的 if-else 决定。
        """
        return ()

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

    # ────────────────────────── 请求构建(旧 if-else,Step 5 替换) ──────────────────────────

    def create_chat_completion(self, messages, tools=None, **kwargs):
        """创建对话补全:自动处理不同厂商特有的参数(例如 DeepSeek 的 thinking 块)"""
        request_kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            request_kwargs["tools"] = tools

        # 不同厂商的参数适配处理(Step 5 会替换为 build_request_kwargs)
        if self.provider == "deepseek":
            if self.thinking_type and self.thinking_type != "disabled":
                request_kwargs["extra_body"] = {"thinking": {"type": self.thinking_type}}
        elif self.provider == "sensenova":
            reasoning_effort = kwargs.get("reasoning_effort") or self.reasoning_effort
            if reasoning_effort:
                request_kwargs["reasoning_effort"] = reasoning_effort
            if "tool_choice" in kwargs:
                request_kwargs["tool_choice"] = kwargs["tool_choice"]
        elif self.provider == "agnes":
            if self.thinking_type and self.thinking_type != "disabled":
                request_kwargs["extra_body"] = {
                    "chat_template_kwargs": {"enable_thinking": True}
                }
            if "tool_choice" in kwargs:
                request_kwargs["tool_choice"] = kwargs["tool_choice"]

        # 补充并覆盖其它自定义参数
        for k, v in kwargs.items():
            if k not in request_kwargs:
                request_kwargs[k] = v

        return self.client.chat.completions.create(**request_kwargs)

    # ────────────────────────── 内部辅助(Step 1 测试用) ──────────────────────────

    def _build_request_kwargs(self, messages, tools=None, **kwargs) -> dict:
        """暴露请求 kwargs 构建过程供回归测试比对。不发起真实 API 调用。

        实现策略:复制 create_chat_completion 的构建逻辑,只是不调 self.client。
        Step 5 改造为 build_request_kwargs(cfg, ...) 后,这个方法会变成它的薄包装。
        """
        request_kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            request_kwargs["tools"] = tools

        if self.provider == "deepseek":
            if self.thinking_type and self.thinking_type != "disabled":
                request_kwargs["extra_body"] = {"thinking": {"type": self.thinking_type}}
        elif self.provider == "sensenova":
            reasoning_effort = kwargs.get("reasoning_effort") or self.reasoning_effort
            if reasoning_effort:
                request_kwargs["reasoning_effort"] = reasoning_effort
            if "tool_choice" in kwargs:
                request_kwargs["tool_choice"] = kwargs["tool_choice"]
        elif self.provider == "agnes":
            if self.thinking_type and self.thinking_type != "disabled":
                request_kwargs["extra_body"] = {
                    "chat_template_kwargs": {"enable_thinking": True}
                }
            if "tool_choice" in kwargs:
                request_kwargs["tool_choice"] = kwargs["tool_choice"]

        for k, v in kwargs.items():
            if k not in request_kwargs:
                request_kwargs[k] = v

        return request_kwargs
