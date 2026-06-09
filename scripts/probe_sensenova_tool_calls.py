"""
探测脚本 2: 验证商汤 SenseNova 流式响应里 tool_calls 字段的真实位置。

新假设(用户提出):
    商汤模型在 reasoning 后本应跟 tool_calls,但 agent.py:474 的
        tcs = getattr(delta, "tool_calls", None)
    只读标准字段,如果商汤的 tool_calls 在 delta.model_extra 里(就像 reasoning 一样),
    我们会**完全错过** tool_calls,导致模型行为看起来像"思而不答"。

验证方法:
    给模型一个**强制 tool_call** 的 prompt(让它必须调工具才能回答),
    用 stream=True,**打印每个 chunk 的完整结构**(包括 model_extra),
    人肉对比 tool_calls 出现在 delta 的哪个字段。

判断:
    - 如果 tool_calls 在 delta.tool_calls(标准位置)→ agent.py 是对的,新假设不成立,回到原方案
    - 如果 tool_calls 在 delta.model_extra['tool_calls'] 或其他位置 → 新假设成立,需要修 agent.py:474
"""

import sys
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WORKTREE_ROOT = Path(__file__).resolve().parent.parent
MASTER_CONFIG = Path("J:/学习/项目/文档agent/src/config.json")
sys.path.insert(0, str(WORKTREE_ROOT / "src"))

from llm_adapter import LLMClientAdapter  # noqa: E402


def banner(text: str) -> None:
    line = "=" * 70
    print(f"\n{line}\n{text}\n{line}")


# 极简 tool 定义:让模型必须调用才能完成任务
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_markdown_draft",
            "description": "将草稿写入磁盘。生成 markdown 文件时**必须**调用此工具,不要只输出文字。",
            "parameters": {
                "type": "object",
                "properties": {
                    "output_path": {"type": "string", "description": "输出文件路径,如 a.md"},
                    "content": {"type": "string", "description": "markdown 文件内容"},
                },
                "required": ["output_path", "content"],
            },
        },
    },
]


def dump_chunk(idx: int, chunk) -> dict:
    """完整 dump 一个 chunk 的所有可见字段,返回结构摘要。"""
    try:
        full = chunk.model_dump() if hasattr(chunk, "model_dump") else {}
    except Exception as e:
        full = {"__dump_error__": str(e)}

    summary = {
        "idx": idx,
        "finish_reason": None,
        "delta_keys": [],
        "delta_tool_calls": None,
        "delta_model_extra": None,
        "delta_content": None,
        "delta_reasoning_content": None,
    }

    if chunk.choices:
        choice = chunk.choices[0]
        summary["finish_reason"] = getattr(choice, "finish_reason", None)
        delta = getattr(choice, "delta", None)
        if delta is not None:
            try:
                d_dump = delta.model_dump() if hasattr(delta, "model_dump") else {}
                summary["delta_keys"] = sorted(d_dump.keys())
                summary["delta_tool_calls"] = d_dump.get("tool_calls")
                summary["delta_content"] = d_dump.get("content")
                summary["delta_reasoning_content"] = d_dump.get("reasoning_content")
            except Exception as e:
                summary["__delta_dump_error__"] = str(e)
            # 关键: 看 model_extra 里有没有 tool_calls
            try:
                extra = getattr(delta, "model_extra", None) or {}
                summary["delta_model_extra"] = dict(extra) if isinstance(extra, dict) else str(extra)
            except Exception as e:
                summary["__model_extra_error__"] = str(e)

    return summary


def run_stream_probe(adapter, name: str, messages: list, tools=None, tool_choice=None) -> None:
    banner(name)
    print("messages:", json.dumps(messages, ensure_ascii=False, indent=2))
    if tools:
        print(f"tools: {len(tools)} 个 (强制让模型调用)")
    if tool_choice:
        print(f"tool_choice: {tool_choice}")

    try:
        kwargs = {"messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        # 直接用底层 client,不经过 adapter.create_chat_completion(避免被适配层加工)
        stream = adapter.client.chat.completions.create(
            model=adapter.model,
            **kwargs,
        )

        chunks_with_tool_calls_standard = []
        chunks_with_tool_calls_extra = []
        all_chunk_summaries = []

        for i, chunk in enumerate(stream):
            summary = dump_chunk(i, chunk)
            all_chunk_summaries.append(summary)

            # 标准位置有 tool_calls?
            if summary["delta_tool_calls"]:
                chunks_with_tool_calls_standard.append(i)

            # model_extra 里有 tool_calls?
            extra = summary["delta_model_extra"] or {}
            if isinstance(extra, dict):
                # 任何含 tool 关键字的字段都打出来
                tool_keys = [k for k in extra.keys() if "tool" in k.lower()]
                if tool_keys:
                    chunks_with_tool_calls_extra.append((i, tool_keys, {k: extra[k] for k in tool_keys}))

        # 打印关键 chunk(只打前 5 + 后 3,完整的丢日志文件)
        print("\n--- chunk 结构摘要 ---")
        n = len(all_chunk_summaries)
        to_show = list(range(min(5, n))) + ([n-3, n-2, n-1] if n > 8 else [])
        for i in to_show:
            s = all_chunk_summaries[i]
            keys_label = ",".join(s["delta_keys"])
            extra_keys_label = ""
            if s["delta_model_extra"]:
                if isinstance(s["delta_model_extra"], dict):
                    extra_keys_label = f" model_extra_keys=[{','.join(s['delta_model_extra'].keys())}]"
            print(f"  chunk #{i}: finish={s['finish_reason']} delta_keys=[{keys_label}]{extra_keys_label}")
            if s["delta_tool_calls"]:
                print(f"     ⚡ tool_calls(标准位置): {json.dumps(s['delta_tool_calls'], ensure_ascii=False)[:200]}")

        # 关键判断
        print("\n--- tool_calls 字段定位 ---")
        if chunks_with_tool_calls_standard:
            print(f"  ✓ 在标准 delta.tool_calls 位置出现 (chunks: {chunks_with_tool_calls_standard[:10]})")
        else:
            print(f"  ✗ 标准 delta.tool_calls 位置**没有**出现 tool_calls")

        if chunks_with_tool_calls_extra:
            print(f"  ⚡ 在 delta.model_extra 里发现 tool 相关字段! (chunks: {[c[0] for c in chunks_with_tool_calls_extra[:5]]})")
            for i, keys, data in chunks_with_tool_calls_extra[:3]:
                print(f"     chunk #{i}: keys={keys}")
                print(f"     data: {json.dumps(data, ensure_ascii=False, default=str)[:300]}")
        else:
            print(f"  - delta.model_extra 里**无** tool 相关字段")

        # 写完整 chunk 数据到文件供事后分析
        dump_file = WORKTREE_ROOT / f"tmp_probe_chunks_{name.replace(' ', '_').replace(':', '_').replace('[', '').replace(']', '')}.json"
        dump_file.parent.mkdir(exist_ok=True)
        with open(dump_file, "w", encoding="utf-8") as f:
            json.dump(all_chunk_summaries, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  完整 chunk dump 写入: {dump_file}")

    except Exception as e:
        print(f"\n✗ 探测失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc(limit=3)


def main() -> int:
    adapter = LLMClientAdapter(config_path=MASTER_CONFIG)
    print(f"provider={adapter.provider} model={adapter.model}")

    # ─── 探测 A: 强制让模型调用 write_markdown_draft ───
    run_stream_probe(
        adapter,
        "Probe A: 用 tools + tool_choice='required' 强制商汤调工具",
        messages=[
            {"role": "user", "content": "请生成一个 a.md 文件,内容是字母 A 的简介(50 字)。"},
        ],
        tools=TOOLS,
        tool_choice="required",
    )

    # ─── 探测 B: 不强制,但 prompt 暗示要调工具 ───
    run_stream_probe(
        adapter,
        "Probe B: 用 tools 但 tool_choice='auto', 让模型自由选择",
        messages=[
            {"role": "user", "content": "请用 write_markdown_draft 工具把一段关于字母 A 的简短介绍(50 字)写入 a.md。"},
        ],
        tools=TOOLS,
        tool_choice="auto",
    )

    # ─── 探测 C: 无 tools,看普通响应 chunk 结构(基线对照) ───
    run_stream_probe(
        adapter,
        "Probe C: 无 tools, 普通响应 (基线对照)",
        messages=[
            {"role": "user", "content": "请用一句话(20 字内)总结量子计算。"},
        ],
    )

    banner("结论")
    print("查看上面每个 Probe 的 'tool_calls 字段定位' 部分:")
    print("  - 如果 Probe A/B 显示 '✓ 在标准 delta.tool_calls 位置出现' → 用户假设**不成立**, agent.py 没漏读")
    print("  - 如果 Probe A/B 显示 '⚡ 在 delta.model_extra 里发现 tool 相关字段' → 用户假设**成立**, 需要修 agent.py:474")
    print("  - 如果 Probe A 商汤直接报错说不支持 tool_choice='required' → 另一种 bug, 但不影响 chunk 结构分析")

    return 0


if __name__ == "__main__":
    sys.exit(main())
