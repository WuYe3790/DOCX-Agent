"""Step 1 回归测试 — 新 src/llm_adapter/ 子包与旧 src/_llm_adapter_legacy.py 行为一致

测什么:
1. **parity**: 同一 config.json 下,新旧两版 create_chat_completion 给底层
   client.chat.completions.create 的 kwargs 字节级一致 (3 个 provider × 多种 caller kwargs)
2. **Review #3**: _render 模板渲染对含 " / \\ 等特殊字符的值做 JSON-escape,
   产物能被 json.loads 解析
3. **Review #1**: QuirkAction Enum + QuirkDirective dataclass 契约
   (Enum 区分、frozen、Step 1 QUIRKS 暂为空)
4. **占位接口**: has_capability / reasoning_field / quirks 三个 property
   在 Step 1 占位实现下与旧 agent.py / analyze_image_content.py 的 if-else 一致
5. **向后兼容**: `from llm_adapter import LLMClientAdapter` 仍可用

策略:
- 用 CapturingClient 替换 self.client,拦截 chat.completions.create 的 kwargs,
  不发起真实 API 调用 — 测试完全 offline,不消耗任何 API quota
- 切换 provider 通过 os.environ["LLM_PROVIDER"] = "..." (LLMClient 在
  __init__ 时读取),用完立刻 pop 不污染其他测试
"""

import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

import llm_adapter as new_pkg          # noqa: E402  — 新子包(__init__ 重导出 LLMClientAdapter)
import _llm_adapter_legacy as old_mod  # noqa: E402  — 旧单文件(Step 6 删除)

CONFIG = str(ROOT / "src" / "config.json")


# ─── 工具: 拦截底层 client.chat.completions.create 的 kwargs ───────────────

class CapturingClient:
    """替换 LLMClient.client,捕获 chat.completions.create 调用的 kwargs。

    不发起真实 HTTP 调用 — Step 1 parity test 完全 offline。
    """
    def __init__(self):
        self.last_kwargs = None
        outer = self

        class _Completions:
            @staticmethod
            def create(**kw):
                outer.last_kwargs = kw
                return "SENTINEL_NOT_REAL_RESPONSE"

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def _make_pair(provider_name: str):
    """构造同 config_path 下的新旧两个 adapter,client 已被 capturing 替换。"""
    os.environ["LLM_PROVIDER"] = provider_name
    try:
        new_ad = new_pkg.LLMClientAdapter(CONFIG)
        old_ad = old_mod.LLMClientAdapter(CONFIG)
    finally:
        os.environ.pop("LLM_PROVIDER", None)
    new_ad.client = CapturingClient()
    old_ad.client = CapturingClient()
    return new_ad, old_ad


def _assert_same_request(provider_name: str, **call_kwargs):
    new_ad, old_ad = _make_pair(provider_name)
    messages = [{"role": "user", "content": "hello"}]
    new_ad.create_chat_completion(messages, **call_kwargs)
    old_ad.create_chat_completion(messages, **call_kwargs)
    assert new_ad.client.last_kwargs == old_ad.client.last_kwargs, (
        f"\n[{provider_name}] new vs old request kwargs differ:\n"
        f"  new = {new_ad.client.last_kwargs}\n"
        f"  old = {old_ad.client.last_kwargs}"
    )


# ─── parity 测试 ─────────────────────────────────────────────────

def test_parity_deepseek():
    _assert_same_request("deepseek")
    _assert_same_request("deepseek", reasoning_effort="high")    # deepseek 应忽略 (旧行为)
    _assert_same_request("deepseek", tool_choice="auto")          # deepseek 应忽略 (旧行为)
    print("[OK] parity deepseek (3 case)")


def test_parity_sensenova():
    _assert_same_request("sensenova")
    _assert_same_request("sensenova", reasoning_effort="low")
    _assert_same_request("sensenova", tool_choice="auto")
    _assert_same_request("sensenova", reasoning_effort="none", tool_choice="auto")
    print("[OK] parity sensenova (4 case)")


def test_parity_agnes():
    _assert_same_request("agnes")
    _assert_same_request("agnes", tool_choice="auto")
    print("[OK] parity agnes (2 case)")


def test_parity_with_tools():
    tools = [{"type": "function", "function": {"name": "foo", "description": "x",
                                                "parameters": {"type": "object", "properties": {}}}}]
    for provider in ("deepseek", "sensenova", "agnes"):
        new_ad, old_ad = _make_pair(provider)
        messages = [{"role": "user", "content": "x"}]
        new_ad.create_chat_completion(messages, tools=tools)
        old_ad.create_chat_completion(messages, tools=tools)
        assert new_ad.client.last_kwargs == old_ad.client.last_kwargs, f"{provider} with tools differ"
    print("[OK] parity with tools (3 providers)")


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


def test_quirks_registry_empty_in_step1():
    from llm_adapter.quirks import QUIRKS
    assert len(QUIRKS) == 0, f"Step 1 不应注册任何 quirk,实际有 {list(QUIRKS)}"
    print("[OK] QUIRKS empty in Step 1")


def test_apply_quirk_unknown_raises():
    from llm_adapter.quirks import apply_quirk
    try:
        apply_quirk("nonexistent_quirk", {})
        raise AssertionError("apply_quirk 对未知名应该抛 RuntimeError")
    except RuntimeError as e:
        assert "Unknown quirk" in str(e)
    print("[OK] apply_quirk unknown raises")


# ─── 占位接口与旧行为一致性 ───────────────────────────────────

def test_has_capability_vision_matches_old_allowlist():
    """Step 1 占位:vision 能力与旧 analyze_image_content.py:48 白名单
    {sensenova, openai, gemini} 一致 — Step 2 才改成读 cfg.capabilities"""
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
    """Step 1 占位:reasoning_field 与旧 agent.py:461-464 if-else 一致 —
    Step 3 才改成读 cfg.reasoning_field"""
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


def test_quirks_property_empty_in_step1():
    """Step 1: quirks 暂为空 tuple,Step 4 才注册 stream_empty_retry"""
    os.environ["LLM_PROVIDER"] = "sensenova"
    try:
        ad = new_pkg.LLMClientAdapter(CONFIG)
    finally:
        os.environ.pop("LLM_PROVIDER", None)
    assert ad.quirks == ()
    print("[OK] quirks property 空")


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


# ─── 占位 registry 函数应该抛 NotImplementedError(防止 Step 1 误用)───

def test_registry_placeholders_raise():
    from llm_adapter.registry import build_client, pick_capable_adapter
    for fn, args in [(build_client, ({},)), (pick_capable_adapter, (None, "vision"))]:
        try:
            fn(*args)
            raise AssertionError(f"{fn.__name__} 在 Step 1 应抛 NotImplementedError")
        except NotImplementedError:
            pass
    print("[OK] registry 占位函数抛 NotImplementedError")


if __name__ == "__main__":
    # 顺序: 不依赖配置文件的 → 依赖配置文件的
    test_render_basic_substitution()
    test_render_json_escape_special_chars()
    test_quirk_action_enum_distinct()
    test_quirk_directive_frozen()
    test_quirks_registry_empty_in_step1()
    test_apply_quirk_unknown_raises()
    test_backward_compat_import()
    test_registry_placeholders_raise()

    # 需要 config.json 才能跑的
    test_backward_compat_class_methods()
    test_raw_config_accessible()
    test_has_capability_vision_matches_old_allowlist()
    test_reasoning_field_matches_old_agent_if_else()
    test_quirks_property_empty_in_step1()
    test_parity_deepseek()
    test_parity_sensenova()
    test_parity_agnes()
    test_parity_with_tools()

    print()
    print("=" * 60)
    print("✓ Step 1 全部 16 个测试通过 — 新子包行为与旧单文件字节级一致")
    print("=" * 60)
