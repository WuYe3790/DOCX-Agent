"""
探测脚本:验证商汤 SenseNova API 是否接受 assistant message 里的 reasoning_content / reasoning 字段。

目的:
    决定 fix-sensenova-reasoning-only 分支走 B 路径(摘要注入)还是 C 路径(保留原生 reasoning_content 字段)。

判断准则:
    Case 2 (reasoning_content) 或 Case 3 (reasoning) 不报 400 且响应合理 → 走 C 路径
    Case 2/3 都报 400 或响应明显异常 → 走 B 路径

使用:
    cd <worktree 根目录>
    python scripts/probe_sensenova_reasoning.py
"""

import sys
import json
import traceback
from pathlib import Path

# Windows 终端 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 复用业务侧 LLMClientAdapter,指向 master 工作区的 config.json(worktree gitignored)
WORKTREE_ROOT = Path(__file__).resolve().parent.parent
MASTER_CONFIG = Path("J:/学习/项目/文档agent/src/config.json")
sys.path.insert(0, str(WORKTREE_ROOT / "src"))

from llm_adapter import LLMClientAdapter  # noqa: E402


def banner(text: str) -> None:
    line = "=" * 70
    print(f"\n{line}\n{text}\n{line}")


def run_case(adapter, name: str, messages: list, expectation: str) -> dict:
    """跑一个探测 case,返回 {ok, error, content, raw}。"""
    banner(f"{name}\n期望: {expectation}")
    print("发送 messages:")
    print(json.dumps(messages, ensure_ascii=False, indent=2))

    result = {"name": name, "ok": False, "error": None, "content": None, "raw": None}
    try:
        # 非流式请求,简化 case 比较
        resp = adapter.client.chat.completions.create(
            model=adapter.model,
            messages=messages,
            stream=False,
        )
        # 这里也不传 reasoning_effort, 想看"裸"行为
        result["raw"] = resp.model_dump() if hasattr(resp, "model_dump") else str(resp)
        choice = resp.choices[0]
        result["content"] = choice.message.content
        result["ok"] = True
        print(f"\n✓ 成功 — 响应 content:")
        print(f"  {result['content']!r}")
        finish = getattr(choice, "finish_reason", None)
        print(f"  finish_reason: {finish}")
        # 商汤的 reasoning 字段在响应里
        reasoning = getattr(choice.message, "reasoning_content", None)
        if reasoning is None:
            extra = getattr(choice.message, "model_extra", None) or {}
            reasoning = extra.get("reasoning") if isinstance(extra, dict) else None
        if reasoning:
            print(f"  reasoning_content(响应里): {reasoning[:200]!r}...")
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        print(f"\n✗ 失败 — {result['error']}")
        # 提取 HTTP body 的更多细节
        for attr in ("status_code", "response", "body"):
            v = getattr(e, attr, None)
            if v:
                print(f"  {attr}: {v}")
        traceback.print_exc(limit=2)

    return result


def main() -> int:
    print(f"读取 config: {MASTER_CONFIG}")
    if not MASTER_CONFIG.exists():
        print(f"✗ config.json 不存在,请检查路径")
        return 1

    adapter = LLMClientAdapter(config_path=MASTER_CONFIG)
    print(f"provider={adapter.provider} model={adapter.model} base_url={adapter.base_url}")
    print(f"reasoning_effort(默认)={adapter.reasoning_effort}")

    cases = []

    # ─── Case 1: 基线 — 普通对话,确认 API 通 ───
    cases.append(run_case(
        adapter,
        "Case 1: 基线(无 reasoning 字段)",
        messages=[
            {"role": "user", "content": "请用一句话(20 字内)总结量子计算。"},
        ],
        expectation="正常返回 content,无报错。",
    ))

    # ─── Case 2: assistant 带 reasoning_content (DeepSeek 风格) ───
    cases.append(run_case(
        adapter,
        "Case 2: assistant 消息带 reasoning_content 字段(DeepSeek 风格)",
        messages=[
            {"role": "user", "content": "请用一句话(20 字内)总结量子计算。"},
            {
                "role": "assistant",
                "content": "我先想想",
                "reasoning_content": "用户希望简洁的总结,我需要涵盖关键点:量子比特的叠加和纠缠特性。一句话内表达。",
            },
            {"role": "user", "content": "请继续完成总结。"},
        ],
        expectation="不报 400 且响应合理(承接上一轮思考)。",
    ))

    # ─── Case 3: assistant 带 reasoning (商汤响应里用的字段名) ───
    cases.append(run_case(
        adapter,
        "Case 3: assistant 消息带 reasoning 字段(商汤专有字段名)",
        messages=[
            {"role": "user", "content": "请用一句话(20 字内)总结量子计算。"},
            {
                "role": "assistant",
                "content": "我先想想",
                "reasoning": "用户希望简洁的总结,我需要涵盖关键点:量子比特的叠加和纠缠特性。一句话内表达。",
            },
            {"role": "user", "content": "请继续完成总结。"},
        ],
        expectation="不报 400 且响应合理。",
    ))

    # ─── Case 4(关键): 还原 bug 场景 — content="" + reasoning_content 有内容 ───
    cases.append(run_case(
        adapter,
        "Case 4 [关键]: 还原 bug — assistant.content='' + reasoning_content 有内容",
        messages=[
            {
                "role": "user",
                "content": "请按顺序生成 3 个 markdown 文件: a.md, b.md, c.md。每个文件内容是一段对应字母的简短介绍。直接输出文件内容。",
            },
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "用户要求生成 3 个 markdown 文件。我先生成 a.md,内容是字母 A 的介绍...让我开始第一个文件的内容。",
            },
        ],
        expectation="期望:模型能从 reasoning_content 续写,直接输出 a.md 内容,而非重新思考。",
    ))

    # ─── 汇总 ───
    banner("汇总")
    for c in cases:
        status = "✓" if c["ok"] else "✗"
        err = c["error"] or ""
        content_preview = (c["content"] or "")[:60] if c["content"] else "(无)"
        print(f"  {status} {c['name']}")
        if err:
            print(f"      错误: {err}")
        if c["ok"]:
            print(f"      content 预览: {content_preview!r}")

    # ─── 判断准则 ───
    banner("判断准则")
    case2_ok = cases[1]["ok"]
    case3_ok = cases[2]["ok"]
    case4_ok = cases[3]["ok"]
    if case2_ok or case3_ok:
        print("✓ Case 2 或 Case 3 通过 — 可考虑走 C 路径(保留 reasoning_content 字段)")
        if case2_ok:
            print("  → 字段名用 reasoning_content")
        if case3_ok:
            print("  → 字段名用 reasoning")
        if case4_ok:
            print("✓ Case 4 也通过 — 强烈支持 C 路径(还原 bug 场景能续写)")
        else:
            print("⚠ Case 4 失败 — C 路径在真实 bug 场景下不一定有效, 建议降级到 B 路径(摘要注入)")
    else:
        print("✗ Case 2 和 Case 3 都失败 — 走 B 路径(reasoning 摘要作为 user/system 消息注入)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
