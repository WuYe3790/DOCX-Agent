import json
import os
from pathlib import Path

from openai import OpenAI

from docx_tools import TOOLS_SCHEMA, call_tool, render_tools_prompt


def load_config():
    config_path = Path(__file__).with_name("config.json")
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_client():
    config = load_config()
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or config.get("api_key", "")
    base_url = os.getenv("OPENAI_BASE_URL") or config.get("base_url", "https://api.deepseek.com")
    if not api_key:
        raise RuntimeError("请设置 OPENAI_API_KEY/DEEPSEEK_API_KEY，或在 src/config.json 中配置 api_key")
    return OpenAI(api_key=api_key, base_url=base_url)


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

    print("=" * 60)
    print("DOCX Agent Demo - lxml + zipfile")
    print("=" * 60)
    print("示例需求：")
    print("把 cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx 中的“依据实验指导书”后插入“测试文本”，另存为 out/demo.docx，并对比原文档。")
    print("=" * 60)

    user_input = input("请输入你的文档编辑需求：\n").strip()
    if not user_input:
        print("需求不能为空")
        return

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    while True:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS_SCHEMA,
        )
        msg = response.choices[0].message
        messages.append(msg)

        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = tool_call.function.arguments
                print(f"\n调用工具: {name}")
                print(f"参数: {args}")
                result = call_tool(name, args)
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

