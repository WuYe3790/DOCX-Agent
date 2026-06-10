"""
Agnes-2.0-Flash API probe — 验证 chat_template_kwargs 的实际可用形式

目的:
    接入新 provider 前, 确认 chat_template_kwargs 走 extra_body 还是顶层 kwarg。
    跑完 4 个 case, 至少一个让 thinking 生效, 就能下结论。

使用:
    $env:AGNES_API_KEY = "sk-..."                 # PowerShell
    python scripts/probe_agnes.py
    或
    export AGNES_API_KEY=sk-...                   # bash
    python scripts/probe_agnes.py

输出:
    控制台: 4 case 逐项结果
    文件:   out/probe_agnes_result.json (完整结构化结果)
"""
import os
import sys
import json
import time
from pathlib import Path
from openai import OpenAI, BadRequestError, APIStatusError, APIConnectionError, APITimeoutError


API_KEY = os.getenv("AGNES_API_KEY")
BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
MODEL = "agnes-2.0-flash"

if not API_KEY:
    print("ERROR: 请先设置环境变量 AGNES_API_KEY")
    print("  PowerShell: $env:AGNES_API_KEY = 'sk-...'")
    print("  bash:       export AGNES_API_KEY=sk-...")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=60, max_retries=0)

# 提示: 强制产生思考的 prompt (简单数学让模型进入 thinking)
PROBE_PROMPT = "请逐步推理: 1+1 等于几? 给出完整思考过程, 最后输出最终答案。"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "echo_tool",
        "description": "回显传入的字符串",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
}]


def banner(text: str) -> None:
    line = "=" * 60
    print(f"\n{line}\n{text}\n{line}")


def detect_thinking(full_reasoning: str, last_chunk) -> tuple:
    """判断 thinking 是否生效. 返回 (是否生效, 证据文本)"""
    if full_reasoning:
        return True, f"流式累积 reasoning_content 长度={len(full_reasoning)}, 前 100 字: {full_reasoning[:100]!r}"
    # 兜底: 检查 raw chunk 字段
    if last_chunk is not None:
        try:
            raw = last_chunk.model_dump() if hasattr(last_chunk, "model_dump") else {}
            choices = raw.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                if "reasoning_content" in delta or "reasoning" in delta:
                    extra = delta.get("reasoning_content") or delta.get("reasoning")
                    return True, f"raw delta 含 reasoning 字段, keys={list(delta.keys())}, preview={(extra or '')[:100]!r}"
        except Exception:
            pass
    return False, "未检测到 reasoning_content / reasoning 字段"


def run_case(label: str, **extra) -> dict:
    """跑一个探测 case, 返回结果 dict。"""
    banner(f"{label}")
    print(f"  kwargs: {json.dumps({k: ('<obj>' if k == 'extra_body' else v) for k, v in extra.items()}, ensure_ascii=False, default=str)}")
    result = {"label": label, "kwargs": {k: v for k, v in extra.items() if k != "tools"}, "ok": False, "evidence": "", "error": None}
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": PROBE_PROMPT}],
            stream=True,
            **extra,
        )
        full_content = ""
        full_reasoning = ""
        last_chunk = None
        for chunk in resp:
            last_chunk = chunk
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta:
                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    full_reasoning += rc
                c = getattr(delta, "content", None)
                if c:
                    full_content += c
        elapsed = time.time() - t0
        ok, evidence = detect_thinking(full_reasoning, last_chunk)
        result.update({
            "ok": ok,
            "evidence": evidence,
            "elapsed_sec": round(elapsed, 2),
            "content_len": len(full_content),
            "reasoning_len": len(full_reasoning),
            "content_preview": full_content[:120],
            "reasoning_preview": full_reasoning[:120],
        })
        print(f"  ok={ok}")
        print(f"  证据: {evidence}")
        print(f"  content_len={len(full_content)} reasoning_len={len(full_reasoning)} elapsed={elapsed:.2f}s")
    except (BadRequestError, APIStatusError) as e:
        result["error"] = f"{type(e).__name__}: {getattr(e, 'message', str(e))[:400]}"
        print(f"  ERROR: {result['error']}")
    except (APIConnectionError, APITimeoutError) as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:400]}"
        print(f"  ERROR: {result['error']}")
    except TypeError as e:
        # OpenAI SDK 不识别顶层 kwarg
        result["error"] = f"TypeError (OpenAI SDK 拒绝 kwargs): {str(e)[:300]}"
        print(f"  ERROR: {result['error']}")
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)[:400]}"
        print(f"  ERROR: {result['error']}")
    return result


# ─── 4 个 Case ────────────────────────────────────────────────────

cases = []

# Case A: extra_body 嵌套 chat_template_kwargs (OpenAI SDK 标准透传方式)
cases.append(run_case(
    "Case A: extra_body={'chat_template_kwargs': {'enable_thinking': True}}",
    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
))

# Case B: 顶层 kwarg (若 OpenAI SDK 抛 TypeError, 自动跳过)
try:
    cases.append(run_case(
        "Case B: 顶层 kwarg chat_template_kwargs={...}",
        chat_template_kwargs={"enable_thinking": True},
    ))
except Exception as e:
    print(f"Case B 跳过: {e}")

# Case C: 不传 thinking (看默认是否 thinking)
cases.append(run_case("Case C: 不传 thinking (默认行为)"))

# Case D: A 形式 + tools + tool_choice=auto
cases.append(run_case(
    "Case D: A 形式 + tools + tool_choice='auto'",
    tools=TOOLS,
    tool_choice="auto",
    extra_body={"chat_template_kwargs": {"enable_thinking": True}},
))

# ─── 汇总 ──────────────────────────────────────────────────────────

banner("结论")
any_pass = any(c.get("ok") for c in cases)
print(f"任何 case 让 thinking 生效: {any_pass}")
print()
for c in cases:
    flag = "PASS" if c.get("ok") else ("ERR " if c.get("error") else "FAIL")
    print(f"  [{flag}] {c['label']}")
    if c.get("error"):
        print(f"        {c['error']}")
    elif c.get("ok"):
        print(f"        reasoning_len={c['reasoning_len']} content_len={c['content_len']} elapsed={c['elapsed_sec']}s")
print()

if not any_pass:
    print("✗ 全部 case 都失败, 需要:")
    print("  1. 确认 AGNES_API_KEY 有效")
    print("  2. 确认 model 名正确 (agnes-2.0-flash)")
    print("  3. 查 Agnes API 文档关于 thinking 的正确启用方式")
else:
    print("✓ 至少一个 case 成功, 可以进入代码集成阶段")
    passing = [c for c in cases if c.get("ok")]
    print(f"  第一个成功的 case 是: {passing[0]['label']}")
    if "Case A" in passing[0]["label"] or "Case D" in passing[0]["label"]:
        print("  → 推荐: llm_adapter.py 用 extra_body={'chat_template_kwargs': {'enable_thinking': True}} 注入")

# 写完整结果到 out/probe_agnes_result.json
out_path = Path("out/probe_agnes_result.json")
out_path.parent.mkdir(exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "model": MODEL,
        "base_url": BASE_URL,
        "any_pass": any_pass,
        "cases": cases,
    }, f, ensure_ascii=False, indent=2)
print(f"\n完整结果: {out_path}")
