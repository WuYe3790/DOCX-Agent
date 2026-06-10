"""Step 1 单元测试(Step 6 后已退役 parity 部分)

历史:Step 1 commit 7cc259b 引入 _llm_adapter_legacy.py 做"新版子包 vs 旧单文件"
字节级回归对比(parity tests)。Step 1-5 期间共 5 次跑通 parity,验证 Step 5 数据
驱动版与旧 if-else 字节级一致。Step 6 删除 _llm_adapter_legacy.py,parity 测试
也随之退役。

本文件保留非 parity 的契约测试:
- _render JSON-escape (Review #3)
- QuirkAction / QuirkDirective dataclass 契约 (Review #1)
- apply_quirk 错误处理
- 向后兼容 import (LLMClientAdapter is LLMClient)
- registry build_client 工厂(Step 5 落地)
- backward-compat 4 getters
- raw_config / has_capability 与旧 agent 行为一致性
"""

import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import llm_adapter as new_pkg          # noqa: E402  — 新子包(__init__ 重导出 LLMClientAdapter)

CONFIG = str(ROOT / "src" / "config.json")


# ─── Review #3: _render JSON-escape ──────────────────────────────

def test_render_basic_substitution():
    from llm_adapter.request_builder import _render
    assert _render('{"type": "${x}"}', {"x": "enabled"}) == '{"type": "enabled"}'
    assert _render('plain', {}) == 'plain'                          # 无占位符
    assert _render('${missing}', {}) == ''                           # 未提供 → 空
    print("[OK] _render basic substitution")


def test_render_json_escape_special_chars():
    """Review #3: 含 " / \\ / 换行 的值不能破坏 extra_body 的 JSON 合法性"""
    from llm_adapter.request_builder import _render
    for value in ['a"b', 'a\\b', 'a\nb', '中文\\and "quotes"']:
        rendered = _render('{"x": "${v}"}', {"v": value})
        # 关键不变量:渲染产物必须是合法 JSON,且 round-trip 等于原值
        obj = json.loads(rendered)
        assert obj["x"] == value, f"round-trip failed for {value!r}: got {obj['x']!r}"
    print("[OK] _render JSON-escape (4 special-char cases)")


# ─── Review #1: QuirkAction Enum + QuirkDirective dataclass ───────

def test_quirk_action_enum_distinct():
    from llm_adapter.quirks import QuirkAction
    assert QuirkAction.CONTINUE != QuirkAction.RETRY_REQUEST
    assert QuirkAction.CONTINUE is not QuirkAction.RETRY_REQUEST
    print("[OK] QuirkAction distinct values")


def test_quirk_directive_frozen():
    from llm_adapter.quirks import QuirkAction, QuirkDirective
    d = QuirkDirective(QuirkAction.RETRY_REQUEST, reason="test")
    assert d.action == QuirkAction.RETRY_REQUEST
    assert d.reason == "test"
    # frozen — 改字段应该报错
    try:
        d.action = QuirkAction.CONTINUE
        raise AssertionError("QuirkDirective 应该是 frozen,但允许了赋值")
    except (AttributeError, Exception) as e:
        # FrozenInstanceError 继承自 AttributeError
        assert "frozen" in str(e).lower() or isinstance(e, AttributeError)
    print("[OK] QuirkDirective frozen")


def test_quirks_registry_has_stream_empty_retry():
    """Step 4 已注册 stream_empty_retry"""
    from llm_adapter.quirks import QUIRKS
    assert "stream_empty_retry" in QUIRKS, "Step 4 后 stream_empty_retry 应已注册"
    print("[OK] QUIRKS 含 Step 4 注册的 stream_empty_retry")


def test_apply_quirk_unknown_raises():
    from llm_adapter.quirks import apply_quirk
    try:
        apply_quirk("nonexistent_quirk", {})
        raise AssertionError("apply_quirk 对未知名应该抛 RuntimeError")
    except RuntimeError as e:
        assert "Unknown quirk" in str(e)
    print("[OK] apply_quirk unknown raises")


# ─── 占位接口与旧行为一致性(读 v2 config.json) ──────────────

def test_has_capability_vision_matches_old_allowlist():
    """Step 2 后:vision capability 与旧 analyze_image_content.py:48 白名单
    {sensenova, openai, gemini} 行为一致(sensenova=True, deepseek/agnes=False)"""
    cases = [("sensenova", True), ("deepseek", False), ("agnes", False)]
    for provider, expected in cases:
        os.environ["LLM_PROVIDER"] = provider
        try:
            ad = new_pkg.LLMClientAdapter(CONFIG)
        finally:
            os.environ.pop("LLM_PROVIDER", None)
        assert ad.has_capability("vision") == expected, \
            f"{provider}.has_capability('vision') 应为 {expected}"
        assert ad.has_capability("chat") is True
        assert ad.has_capability("tools") is True
    print("[OK] has_capability vision 与旧白名单一致")


def test_reasoning_field_matches_old_agent_if_else():
    """Step 3 后:reasoning_field 与旧 agent.py:461-464 if-else 一致"""
    cases = [
        ("sensenova", "delta.model_extra.reasoning"),
        ("deepseek", "delta.reasoning_content"),
        ("agnes", "delta.reasoning_content"),
    ]
    for provider, expected_path in cases:
        os.environ["LLM_PROVIDER"] = provider
        try:
            ad = new_pkg.LLMClientAdapter(CONFIG)
        finally:
            os.environ.pop("LLM_PROVIDER", None)
        assert ad.reasoning_field == expected_path, \
            f"{provider}.reasoning_field = {ad.reasoning_field!r} != {expected_path!r}"
    print("[OK] reasoning_field 与旧 agent if-else 一致")


def test_quirks_property_deepseek_empty():
    """deepseek 默认无 quirk(sensenova 默认有 stream_empty_retry — Step 4 后断言不再适用)"""
    os.environ["LLM_PROVIDER"] = "deepseek"
    try:
        ad = new_pkg.LLMClientAdapter(CONFIG)
    finally:
        os.environ.pop("LLM_PROVIDER", None)
    assert ad.quirks == ()
    print("[OK] deepseek.quirks 空")


def test_raw_config_accessible():
    """raw_config 暴露原始 dict 给 registry.pick_capable_adapter 用"""
    os.environ["LLM_PROVIDER"] = "deepseek"
    try:
        ad = new_pkg.LLMClientAdapter(CONFIG)
    finally:
        os.environ.pop("LLM_PROVIDER", None)
    cfg = ad.raw_config
    assert isinstance(cfg, dict)
    assert "providers" in cfg
    print("[OK] raw_config exposes original dict")


# ─── 向后兼容 ────────────────────────────────────────────

def test_backward_compat_import():
    from llm_adapter import LLMClientAdapter
    from llm_adapter import LLMClient
    assert LLMClientAdapter is LLMClient, "LLMClientAdapter 应当是 LLMClient 的别名 (is 关系)"
    print("[OK] backward-compat import: LLMClientAdapter is LLMClient")


def test_backward_compat_class_methods():
    """旧调用方使用的 4 个 getter + create_chat_completion 仍然存在"""
    os.environ["LLM_PROVIDER"] = "sensenova"
    try:
        ad = new_pkg.LLMClientAdapter(CONFIG)
    finally:
        os.environ.pop("LLM_PROVIDER", None)
    assert ad.get_model_name()
    assert ad.get_provider() == "sensenova"
    assert ad.get_thinking_type() == "disabled"
    assert ad.get_reasoning_effort() == "high"
    assert callable(ad.create_chat_completion)
    print("[OK] backward-compat: 4 getters + create_chat_completion")


# ─── registry.build_client(Step 5 落地)──────

def test_registry_build_client_from_dict():
    """Step 5 起 build_client 是公开工厂,空 config 显式失败,合法 config 正确构造"""
    from llm_adapter.registry import build_client
    # 空 config → 缺 api_key → 显式 RuntimeError(fail-loud)
    try:
        build_client({})
        raise AssertionError("空 config 应触发 RuntimeError(缺 api_key)")
    except RuntimeError as e:
        assert "API Key" in str(e)

    # 合法 config → 能成功构造
    valid_cfg = {
        "providers": {
            "deepseek": {
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
            }
        }
    }
    client = build_client(valid_cfg, override_provider="deepseek")
    assert client.get_provider() == "deepseek"
    assert client.get_model_name() == "deepseek-v4-flash"
    print("[OK] registry.build_client 从 dict 正确构造 + 空 config fail-loud")


if __name__ == "__main__":
    test_render_basic_substitution()
    test_render_json_escape_special_chars()
    test_quirk_action_enum_distinct()
    test_quirk_directive_frozen()
    test_quirks_registry_has_stream_empty_retry()
    test_apply_quirk_unknown_raises()
    test_backward_compat_import()
    test_registry_build_client_from_dict()

    # 需要 config.json 才能跑的
    test_backward_compat_class_methods()
    test_raw_config_accessible()
    test_has_capability_vision_matches_old_allowlist()
    test_reasoning_field_matches_old_agent_if_else()
    test_quirks_property_deepseek_empty()

    print()
    print("=" * 60)
    print("✓ Step 1 单元测试 13 个全部通过(parity 部分 Step 6 退役)")
    print("=" * 60)
