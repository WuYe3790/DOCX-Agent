import json
import os
from pathlib import Path

from openai import OpenAI
from openai import APIConnectionError, APIError, APITimeoutError

from docx_tools import TOOLS_SCHEMA, call_tool, render_tools_prompt


def load_config():
    config_path = Path(__file__).with_name("config.json")
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_client():
    config = load_config()
    api_key = os.getenv("DEEPSEEK_API_KEY") or config.get("api_key", "")
    base_url = config.get("base_url", "https://api.deepseek.com")
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", config.get("timeout_seconds", 60)))
    if not api_key:
        raise RuntimeError("请设置 OPENAI_API_KEY/DEEPSEEK_API_KEY，或在 src/config.json 中配置 api_key")
    return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0,)


SYSTEM_PROMPT = f"""
你是一个精细 DOCX 编辑 agent。

目标：
1. 先读取文档结构或查找锚点，不要盲改。
2. 插入文字时优先保留原 run 格式。
3. 编辑后必须调用 diff_docx 验证变化。
4. 只解释和用户请求相关的变化，注意区分 word/document.xml 的业务变化和 Office 保存噪声。

工具说明：
{render_tools_prompt()}
""".strip()


def main():
    client = build_client()
    model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
    thinking_type = os.getenv("DOCX_AGENT_THINKING", "enabled").strip().lower()

    print("=" * 60)
    print("DOCX Agent Demo - lxml + zipfile")
    print("=" * 60)
    print("示例需求：")
    print("把 文档格式测试/cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx 中的“依据实验指导书”后插入“测试文本”，另存为 out/demo.docx，并对比原文档。")
    print("=" * 60)

    user_input = input("请输入你的文档编辑需求：\n").strip()
    if not user_input:
        print("需求不能为空")
        return

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    round_index = 0
    while True:
        round_index += 1
        print(f"\n第 {round_index} 轮：正在请求模型 {model} ...", flush=True)
        try:
            request_kwargs = {
                "model": model,
                "messages": messages,
                "tools": TOOLS_SCHEMA,
            }
            if thinking_type and thinking_type != "disabled":
                request_kwargs["extra_body"] = {"thinking": {"type": thinking_type}}
            response = client.chat.completions.create(**request_kwargs)
        except APITimeoutError as exc:
            print("\n模型请求超时。可以先检查网络、base_url、模型名，或设置更长超时：")
            print("$env:OPENAI_TIMEOUT_SECONDS=\"120\"")
            print(f"错误信息: {exc}")
            return
        except APIConnectionError as exc:
            print("\n无法连接到模型服务。请检查网络、代理、OPENAI_BASE_URL/DeepSeek base_url。")
            print(f"错误信息: {exc}")
            return
        except APIError as exc:
            print("\n模型服务返回错误。请检查 API key、模型名、thinking/tool calling 是否兼容。")
            print(f"错误信息: {exc}")
            return
        except Exception as exc:
            print("\n请求模型时发生未知错误。")
            print(f"错误类型: {type(exc).__name__}")
            print(f"错误信息: {exc}")
            return

        msg = response.choices[0].message
        msg_dict = msg.model_dump(exclude_none=True)
        messages.append(msg_dict)

        reasoning_content = getattr(msg, "reasoning_content", None) or msg_dict.get("reasoning_content")
        if reasoning_content:
            print("\n[模型思考摘要]")
            print(reasoning_content[:1200])

        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = tool_call.function.arguments
                print(f"\n调用工具: {name}")
                print(f"参数: {args}")
                try:
                    result = call_tool(name, args)
                except Exception as exc:
                    result = json.dumps(
                        {
                            "status": "error",
                            "tool": name,
                            "error_type": type(exc).__name__,
                            "message": str(exc),
                        },
                        ensure_ascii=False,
                    )
                print(f"结果: {result[:1200]}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )
            continue

        print("\n" + "=" * 60)
        print("最终回复")
        print("=" * 60)
        print(msg.content)
        break


if __name__ == "__main__":
    main()
