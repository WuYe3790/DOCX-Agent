"""Step 4 回归测试 — quirks 注册表 + stream_empty_retry + agent.py 改造

测什么:
1. QUIRKS 注册表:stream_empty_retry 已注册
2. stream_empty_retry quirk 函数行为:
   - finish_reason=None + 空 tool_calls → RETRY_REQUEST
   - finish_reason 有值 → CONTINUE
   - 有 tool_calls → CONTINUE
3. provider.quirks property:
   - sensenova → ("stream_empty_retry",)(默认表)
   - deepseek/agnes → () (默认表无)
   - provider block 显式 "quirks" 覆盖默认表(空列表 = 显式禁用)
4. static check: agent.py 已迁移到 apply_quirk + QuirkAction.RETRY_REQUEST
"""

import os
import sys
import json
import tempfile
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llm_adapter.provider import LLMClient                       # noqa: E402
from llm_adapter.quirks import (                                  # noqa: E402
    QUIRKS, QuirkAction, QuirkDirective, apply_quirk,
)


# ─── 工具 ───────────────────────────────────────────────

@contextlib.contextmanager
def _clean_env(*keys: str):
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def _write_temp_config(providers_block: dict, active_provider: str) -> str:
    cfg = {"provider": active_provider, "providers": providers_block}
    path = Path(tempfile.mkdtemp(prefix="docx_agent_step4_")) / "config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _block(extra: dict = None) -> dict:
    base = {"api_key": "sk-test", "base_url": "https://example.com/v1", "model": "test-model"}
    if extra:
        base.update(extra)
    return base


# ─── 注册表 ────────────────────────────────

def test_stream_empty_retry_registered():
    assert "stream_empty_retry" in QUIRKS, "Step 4 应注册 stream_empty_retry"
    print("[OK] stream_empty_retry 已注册到 QUIRKS")


# ─── stream_empty_retry quirk 函数行为 ─────

def test_quirk_triggers_on_silent_close():
    """finish_reason=None + 空 tool_calls → RETRY_REQUEST"""
    directive = apply_quirk("stream_empty_retry", {
        "finish_reason": None,
        "tool_calls_map": {},
        "accumulated_content": "",
        "accumulated_reasoning": "在想但没产出",
    })
    assert directive.action == QuirkAction.RETRY_REQUEST
    assert directive.reason == "stream_incomplete"
    print("[OK] quirk 在 finish_reason=None + tool_calls 空时 → RETRY_REQUEST")


def test_quirk_passes_when_finish_reason_present():
    """finish_reason 有值(正常结束)→ CONTINUE"""
    directive = apply_quirk("stream_empty_retry", {
        "finish_reason": "stop",
        "tool_calls_map": {},
        "accumulated_content": "正常响应",
        "accumulated_reasoning": "",
    })
    assert directive.action == QuirkAction.CONTINUE
    print("[OK] quirk 在 finish_reason=stop 时 → CONTINUE")


def test_quirk_passes_when_tool_calls_present():
    """finish_reason=None 但有 tool_calls(server 还在发 tool chunks)→ CONTINUE"""
    directive = apply_quirk("stream_empty_retry", {
        "finish_reason": None,
        "tool_calls_map": {0: {"name": "foo", "arguments": "{}"}},
        "accumulated_content": "",
        "accumulated_reasoning": "",
    })
    assert directive.action == QuirkAction.CONTINUE
    print("[OK] quirk 在有 tool_calls 时 → CONTINUE")


# ─── provider.quirks property ─────────────────

def test_provider_quirks_sensenova_default():
    cfg = _write_temp_config({"sensenova": _block()}, "sensenova")
    ad = LLMClient(cfg)
    assert ad.quirks == ("stream_empty_retry",), f"sensenova 默认应启用 stream_empty_retry,实际 {ad.quirks}"
    print("[OK] sensenova 默认启用 stream_empty_retry")


def test_provider_quirks_deepseek_default_empty():
    cfg = _write_temp_config({"deepseek": _block()}, "deepseek")
    ad = LLMClient(cfg)
    assert ad.quirks == (), f"deepseek 默认无 quirk,实际 {ad.quirks}"
    print("[OK] deepseek 默认无 quirk")


def test_provider_quirks_agnes_default_empty():
    cfg = _write_temp_config({"agnes": _block()}, "agnes")
    ad = LLMClient(cfg)
    assert ad.quirks == (), f"agnes 默认无 quirk,实际 {ad.quirks}"
    print("[OK] agnes 默认无 quirk")


def test_provider_quirks_block_override():
    """provider block 显式 'quirks' 列表覆盖默认表"""
    cfg = _write_temp_config({
        "deepseek": _block({"quirks": ["stream_empty_retry"]})  # deepseek 强制启用
    }, "deepseek")
    ad = LLMClient(cfg)
    assert ad.quirks == ("stream_empty_retry",), "block 显式 quirks 应覆盖默认"
    print("[OK] block 显式 quirks 覆盖默认")


def test_provider_quirks_block_explicit_empty_disables_default():
    """显式空列表 = 用户明确禁用 sensenova 默认的 stream_empty_retry(用于 debug)"""
    cfg = _write_temp_config({
        "sensenova": _block({"quirks": []})
    }, "sensenova")
    ad = LLMClient(cfg)
    assert ad.quirks == (), "显式 quirks=[] 应清空所有 quirk(包括默认表)"
    print("[OK] 显式空列表禁用默认 quirk")


def test_provider_quirks_unknown_provider_empty():
    cfg = _write_temp_config({"我自己的模型": _block()}, "我自己的模型")
    with _clean_env("OPENAI_API_KEY", "LLM_API_KEY"):
        ad = LLMClient(cfg)
    assert ad.quirks == ()
    print("[OK] 未知 provider 默认无 quirk")


# ─── apply_quirk 错误处理 ─────────────

def test_apply_unknown_quirk_raises_with_hint():
    """未知 quirk 名 → RuntimeError + 列出已注册名(配置错误时 fail-loud)"""
    try:
        apply_quirk("nonexistent_quirk_xyz", {})
        raise AssertionError("apply_quirk 应抛 RuntimeError")
    except RuntimeError as e:
        msg = str(e)
        assert "Unknown quirk" in msg
        assert "stream_empty_retry" in msg, "错误信息应列出当前已注册的 quirks"
    print("[OK] apply_quirk 未知名抛 RuntimeError 并列出已注册")


# ─── agent.py 静态改造检查 ───

def test_agent_uses_apply_quirk():
    src = ROOT / "src" / "agent.py"
    text = src.read_text(encoding="utf-8")
    assert "from llm_adapter.quirks import apply_quirk, QuirkAction" in text, \
        "agent.py 应 import apply_quirk + QuirkAction"
    assert "for quirk_name in self.llm.quirks" in text, \
        "agent.py 应遍历 self.llm.quirks"
    assert "QuirkAction.RETRY_REQUEST" in text, \
        "agent.py 应用 QuirkAction Enum 判断 action"
    # 旧 inline if-else 触发条件应已删除
    assert "if finish_reason is None and not tool_calls_map:" not in text, \
        "旧 inline 触发条件应已抽到 quirk 函数内"
    print("[OK] agent.py 已完成 Step 4 改造(静态检查)")


if __name__ == "__main__":
    test_stream_empty_retry_registered()
    test_quirk_triggers_on_silent_close()
    test_quirk_passes_when_finish_reason_present()
    test_quirk_passes_when_tool_calls_present()
    test_provider_quirks_sensenova_default()
    test_provider_quirks_deepseek_default_empty()
    test_provider_quirks_agnes_default_empty()
    test_provider_quirks_block_override()
    test_provider_quirks_block_explicit_empty_disables_default()
    test_provider_quirks_unknown_provider_empty()
    test_apply_unknown_quirk_raises_with_hint()
    test_agent_uses_apply_quirk()

    print()
    print("=" * 60)
    print("✓ Step 4 全部 12 个测试通过 — quirks 配置化 + agent.py 解耦完毕")
    print("=" * 60)
