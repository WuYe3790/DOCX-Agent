import os
import json
from pathlib import Path
from openai import OpenAI

class LLMClientAdapter:
    """
    模型适配层：统一管理不同大模型服务商（如 DeepSeek, SenseNova）的连接与调用细节。
    """
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.json"
        else:
            config_path = Path(config_path)

        # 1. 加载 config.json
        self.config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except Exception as e:
                print(f"警告: 加载配置文件 {config_path} 失败: {e}")

        # 2. 判定 provider (提供商)
        # 优先级: 环境变量 LLM_PROVIDER -> config.json 的 provider 字段 -> 根据旧版 root-level 配置自动判定 -> 默认 deepseek
        self.provider = os.getenv("LLM_PROVIDER") or self.config.get("provider")

        top_api_key = self.config.get("api_key")
        top_base_url = self.config.get("base_url")

        if not self.provider:
            if top_base_url and "sensenova" in top_base_url:
                self.provider = "sensenova"
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
            # 环境变量
            self.api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("LLM_BASE_URL")
            self.model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
            self.thinking_type = os.getenv("DOCX_AGENT_THINKING")

            # 厂商特定配置
            self.api_key = self.api_key or provider_config.get("api_key")
            self.base_url = self.base_url or provider_config.get("base_url")
            self.model = self.model or provider_config.get("model")
            if self.thinking_type is None:
                self.thinking_type = provider_config.get("thinking")

            # 兼容旧版本单层级 config
            if not provider_config:
                self.api_key = self.api_key or top_api_key
                self.base_url = self.base_url or top_base_url

            # 默认兜底值
            self.base_url = self.base_url or "https://api.deepseek.com"
            self.model = self.model or "deepseek-v4-flash"
            if self.thinking_type is None:
                self.thinking_type = "enabled"

        elif self.provider == "sensenova":
            # 环境变量
            self.api_key = os.getenv("SENSENOVA_API_KEY") or os.getenv("LLM_API_KEY")
            self.base_url = os.getenv("SENSENOVA_BASE_URL") or os.getenv("LLM_BASE_URL")
            self.model = os.getenv("LLM_MODEL")
            self.reasoning_effort = os.getenv("SENSENOVA_REASONING_EFFORT") or os.getenv("LLM_REASONING_EFFORT")

            # 厂商特定配置
            self.api_key = self.api_key or provider_config.get("api_key")
            self.base_url = self.base_url or provider_config.get("base_url")
            self.model = self.model or provider_config.get("model")
            self.reasoning_effort = self.reasoning_effort or provider_config.get("reasoning_effort")

            # 兼容旧版本单层级 config (如果 root-level 的 base_url 是商汤的话)
            if not provider_config and top_base_url and "sensenova" in top_base_url:
                self.api_key = self.api_key or top_api_key
                self.base_url = self.base_url or top_base_url

            # 默认兜底值
            self.base_url = self.base_url or "https://token.sensenova.cn/v1"
            self.model = self.model or "sensenova-6.7-flash-lite"
            self.thinking_type = "disabled"  # 商汤不需要 DeepSeek-style thinking extra_body

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
                f"未设置 LLM API Key。请设置相应的环境变量（如 {self.provider.upper()}_API_KEY）或在 config.json 中配置该提供商的 api_key。"
            )

        # 4. 创建 OpenAI 客户端
        timeout = float(self.config.get("timeout_seconds", 300))
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            max_retries=0
        )

    def get_model_name(self) -> str:
        """获取当前激活的模型名称"""
        return self.model

    def get_thinking_type(self) -> str:
        """获取当前的 thinking 类型配置（仅用于 DeepSeek 兼容性）"""
        return self.thinking_type

    def get_provider(self) -> str:
        """获取当前所使用的提供商"""
        return self.provider

    def get_reasoning_effort(self) -> str:
        """获取当前商汤模型的推理强度"""
        return self.reasoning_effort

    def create_chat_completion(self, messages, tools=None, **kwargs):
        """
        创建对话补全：自动处理不同厂商特有的参数（例如 DeepSeek 的 thinking 块）
        """
        request_kwargs = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            request_kwargs["tools"] = tools

        # 不同厂商的参数适配处理
        if self.provider == "deepseek":
            if self.thinking_type and self.thinking_type != "disabled":
                request_kwargs["extra_body"] = {"thinking": {"type": self.thinking_type}}
        elif self.provider == "sensenova":
            # 自动应用 reasoning_effort 参数
            reasoning_effort = kwargs.get("reasoning_effort") or self.reasoning_effort
            if reasoning_effort:
                request_kwargs["reasoning_effort"] = reasoning_effort
            # 商汤支持 tool_choice
            if "tool_choice" in kwargs:
                request_kwargs["tool_choice"] = kwargs["tool_choice"]

        # 补充并覆盖其它自定义参数
        for k, v in kwargs.items():
            if k not in request_kwargs:
                request_kwargs[k] = v

        return self.client.chat.completions.create(**request_kwargs)
