import json
import os
from datetime import datetime
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


def create_log_file() -> Path:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"docx_agent_{timestamp}.log"


def append_log(log_path: Path, title: str, data=None) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 80}\n")
        f.write(f"{datetime.now().isoformat(timespec='seconds')} | {title}\n")
        f.write(f"{'=' * 80}\n")
        if data is None:
            return
        if isinstance(data, str):
            f.write(data)
        else:
            f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        f.write("\n")


def tool_status(result: str) -> str:
    try:
        parsed = json.loads(result)
    except json.JSONDecodeError:
        return "完成"
    status = parsed.get("status")
    if status:
        return str(status)
    return "完成"


SYSTEM_PROMPT = f"""
你是一个精细 DOCX 编辑 agent。

目标：
1. 先读取文档结构或查找锚点，不要盲改。
2. 插入文字时优先保留原 run 格式。
3. 编辑后必须调用 diff_docx 验证变化。
4. 只解释和用户请求相关的变化，注意区分 word/document.xml 的业务变化和 Office 保存噪声。
5. 一次工具调用尽量只替换或写入一行内容；如果要写多段正文，优先用 replace_text 写第一段，再用 insert_paragraph_after 逐段追加。
6. 如果用户给出的内容本身包含换行，必须使用支持 newline_mode 的工具，并优先选择 newline_mode="paragraphs"，不要把长正文塞进单个 run。
7. 替换蓝色提示、占位符、高亮说明为正式正文时，使用 format_policy="body"；替换标题占位但希望保留标题样式时，使用 format_policy="preserve"。
8. 需要局部加粗、改颜色、改字号时，优先使用 set_text_format；如果写入时已经知道格式，也可以在写入工具中使用 format_policy="custom"。
9. 表格结构操作必须优先使用表格坐标工具：插入整行用 insert_table_row_after，清空单元格用 clear_table_cell，删除整行用 delete_table_row，替换单元格全部内容用 replace_table_cell_text。
10. 表格工具的 table_index 按 //w:tbl 全文计数，嵌套表格也会计数；调用前必须用 read_docx_structure 返回的行列文本确认目标表格、行、列。
11. 用户说“删除整行”时不要只删除行内文字；用户说“清空单元格”时不要删除行或单元格。

工具说明：
{render_tools_prompt()}
""".strip()


def main():
    client = build_client()
    model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
    thinking_type = os.getenv("DOCX_AGENT_THINKING", "enabled").strip().lower()
    log_path = create_log_file()

    print("=" * 60)
    print("DOCX Agent Demo - lxml + zipfile")
    print("=" * 60)
    print(f"运行日志: {log_path}")
    print("示例需求：")
    print("把 文档格式测试/cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx 中的“依据实验指导书”后插入“测试文本”，另存为 out/demo.docx，并对比原文档。")
    print("=" * 60)

    user_input = input("请输入你的文档编辑需求：\n").strip()
    if not user_input:
        print("需求不能为空")
        return

    append_log(
        log_path,
        "启动配置",
        {
            "model": model,
            "thinking_type": thinking_type,
            "tool_count": len(TOOLS_SCHEMA),
            "user_input": user_input,
        },
    )

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
            append_log(
                log_path,
                f"第 {round_index} 轮模型请求",
                {
                    "model": model,
                    "message_count": len(messages),
                    "tool_count": len(TOOLS_SCHEMA),
                    "thinking_type": thinking_type,
                },
            )
            response = client.chat.completions.create(**request_kwargs)
        except APITimeoutError as exc:
            print("\n模型请求超时。可以先检查网络、base_url、模型名，或设置更长超时：")
            print("$env:OPENAI_TIMEOUT_SECONDS=\"120\"")
            print(f"错误信息: {exc}")
            append_log(log_path, "模型请求超时", {"error_type": type(exc).__name__, "message": str(exc)})
            return
        except APIConnectionError as exc:
            print("\n无法连接到模型服务。请检查网络、代理、OPENAI_BASE_URL/DeepSeek base_url。")
            print(f"错误信息: {exc}")
            append_log(log_path, "模型连接错误", {"error_type": type(exc).__name__, "message": str(exc)})
            return
        except APIError as exc:
            print("\n模型服务返回错误。请检查 API key、模型名、thinking/tool calling 是否兼容。")
            print(f"错误信息: {exc}")
            append_log(log_path, "模型服务错误", {"error_type": type(exc).__name__, "message": str(exc)})
            return
        except Exception as exc:
            print("\n请求模型时发生未知错误。")
            print(f"错误类型: {type(exc).__name__}")
            print(f"错误信息: {exc}")
            append_log(log_path, "模型未知错误", {"error_type": type(exc).__name__, "message": str(exc)})
            return

        msg = response.choices[0].message
        msg_dict = msg.model_dump(exclude_none=True)
        messages.append(msg_dict)
        append_log(log_path, f"第 {round_index} 轮模型响应", msg_dict)

        reasoning_content = getattr(msg, "reasoning_content", None) or msg_dict.get("reasoning_content")
        if reasoning_content:
            print("\n[模型思考摘要]")
            print(reasoning_content[:1200])

        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                name = tool_call.function.name
                args = tool_call.function.arguments
                print(f"\n调用工具: {name}（详情见日志）")
                append_log(log_path, f"调用工具: {name}", {"tool": name, "arguments": args})
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
                append_log(log_path, f"工具结果: {name}", result)
                print(f"工具状态: {tool_status(result)}")
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
        append_log(log_path, "最终回复", msg.content)
        break


if __name__ == "__main__":
    main()
