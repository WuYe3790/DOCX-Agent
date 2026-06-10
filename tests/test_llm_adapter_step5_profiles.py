"""Step 5 回归测试 — PROFILES + build_client + 请求注入三件套数据化 + v2 config

测什么:
1. **extra_body_template / top_level_kwargs / forward_tool_choice 三个新字段**:
   - 默认表(_DEFAULT_*)对 deepseek/sensenova/agnes 的预期值
   - provider block 显式声明覆盖默认
   - 未知 provider → fallback (None / {} / False)

2. **build_client 工厂**(Step 5 新公开 API):
   - 从 dict 构造 + override_provider
   - 空 config 显式失败(缺 api_key)
   - dict 中 active provider 切换

3. **PROFILES documentation**:
   - openai_compatible 在 PROFILES 中

4. **通用接口 4 行 e2e**(plan §G Step 5 关键验收):
   - 仅 4 个字段(profile + api_key + base_url + model) 就能构造 LLMClient
   - 所有未声明字段 fallback 到 OpenAI 兼容默认

5. **v1 / v2 schema 兼容**:
   - v1 config(无 Step 5 字段) 走 _DEFAULT_* fallback
   - v2 config(显式声明全部 Step 5 字段) 字段全部生效

6. **build_request_kwargs 数据驱动**:
   - 通过显式字段控制 extra_body/top_level/tool_choice 注入
   - 与 _build_request_kwargs 一致(实质同一函数)

7. **静态检查**: src/config.json 已升级到 v2; src/config.example.json 存在
"""

import os
import sys
import json
import tempfile
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llm_adapter.provider import LLMClient                              # noqa: E402
from llm_adapter.registry import PROFILES, build_client                 # noqa: E402
from llm_adapter.request_builder import build_request_kwargs            # noqa: E402


# ─── 工具 ────────────────────────────────────────────

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
    path = Path(tempfile.mkdtemp(prefix="docx_agent_step5_")) / "config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _block(extra: dict = None) -> dict:
    base = {"api_key": "sk-test", "base_url": "https://example.com/v1", "model": "test-model"}
    if extra:
        base.update(extra)
    return base


# ─── 1. 注入三件套默认表 ────────────────────────

def test_default_extra_body_template_deepseek():
    cfg = _write_temp_config({"deepseek": _block()}, "deepseek")
    ad = LLMClient(cfg)
    assert ad.extra_body_template == '{"thinking": {"type": "${thinking}"}}'
    print("[OK] default extra_body_template: deepseek")


def test_default_extra_body_template_agnes():
    cfg = _write_temp_config({"agnes": _block()}, "agnes")
    ad = LLMClient(cfg)
    assert "chat_template_kwargs" in ad.extra_body_template
    print("[OK] default extra_body_template: agnes")


def test_default_extra_body_template_sensenova_none():
    cfg = _write_temp_config({"sensenova": _block()}, "sensenova")
    ad = LLMClient(cfg)
    assert ad.extra_body_template is None, "sensenova 不需要 extra_body"
    print("[OK] default extra_body_template: sensenova None")


def test_default_top_level_kwargs_sensenova():
    cfg = _write_temp_config({"sensenova": _block()}, "sensenova")
    ad = LLMClient(cfg)
    assert ad.top_level_kwargs == {"reasoning_effort": "${reasoning_effort}"}
    print("[OK] default top_level_kwargs: sensenova reasoning_effort")


def test_default_top_level_kwargs_deepseek_empty():
    cfg = _write_temp_config({"deepseek": _block()}, "deepseek")
    ad = LLMClient(cfg)
    assert ad.top_level_kwargs == {}
    print("[OK] default top_level_kwargs: deepseek 空")


def test_default_forward_tool_choice():
    """sensenova / agnes 默认 forward_tool_choice = True;deepseek / 通用 = False"""
    cases = [("sensenova", True), ("agnes", True), ("deepseek", False)]
    for provider, expected in cases:
        cfg = _write_temp_config({provider: _block()}, provider)
        ad = LLMClient(cfg)
        assert ad.forward_tool_choice == expected, f"{provider} forward_tool_choice 应为 {expected}"
    print("[OK] default forward_tool_choice (3 providers)")


def test_default_forward_tool_choice_unknown_provider_false():
    cfg = _write_temp_config({"通用模型": _block()}, "通用模型")
    with _clean_env("OPENAI_API_KEY", "LLM_API_KEY"):
        ad = LLMClient(cfg)
    assert ad.forward_tool_choice is False
    print("[OK] default forward_tool_choice: 未知 provider → False")


# ─── 2. 三件套 provider block 覆盖 ──────────────

def test_extra_body_template_block_override():
    cfg = _write_temp_config({
        "deepseek": _block({"extra_body_template": '{"custom": "${thinking}"}'})
    }, "deepseek")
    ad = LLMClient(cfg)
    assert ad.extra_body_template == '{"custom": "${thinking}"}'
    print("[OK] extra_body_template block override")


def test_top_level_kwargs_block_override():
    cfg = _write_temp_config({
        "deepseek": _block({"top_level_kwargs": {"my_kwarg": "fixed"}})
    }, "deepseek")
    ad = LLMClient(cfg)
    assert ad.top_level_kwargs == {"my_kwarg": "fixed"}
    print("[OK] top_level_kwargs block override")


def test_forward_tool_choice_block_override():
    cfg = _write_temp_config({
        "deepseek": _block({"forward_tool_choice": True})    # deepseek 默认 False,显式开
    }, "deepseek")
    ad = LLMClient(cfg)
    assert ad.forward_tool_choice is True
    print("[OK] forward_tool_choice block override")


# ─── 3. build_client 工厂 ────────────────────

def test_build_client_from_dict():
    config = {
        "providers": {
            "sensenova": {
                "api_key": "sk-test",
                "base_url": "https://example.com/v1",
                "model": "test-model",
            }
        }
    }
    client = build_client(config, override_provider="sensenova")
    assert client.get_provider() == "sensenova"
    assert client.get_model_name() == "test-model"
    # 默认表生效
    assert client.has_capability("vision")
    assert client.reasoning_field == "delta.model_extra.reasoning"
    assert client.quirks == ("stream_empty_retry",)
    print("[OK] build_client 从 dict 构造,默认表生效")


def test_build_client_empty_config_raises():
    try:
        build_client({})
        raise AssertionError("空 config 应抛 RuntimeError")
    except RuntimeError as e:
        assert "API Key" in str(e)
    print("[OK] build_client 空 config 显式 fail-loud")


def test_build_client_override_provider():
    """显式 override_provider 覆盖 config['provider'] 字段"""
    config = {
        "provider": "sensenova",
        "providers": {
            "sensenova": _block(),
            "deepseek": _block(),
        }
    }
    client = build_client(config, override_provider="deepseek")
    assert client.get_provider() == "deepseek", "override 应覆盖 config['provider']"
    print("[OK] build_client override_provider 工作")


# ─── 4. PROFILES documentation ──────────────────

def test_profiles_has_openai_compatible():
    assert "openai_compatible" in PROFILES
    profile = PROFILES["openai_compatible"]
    # 文档字段应至少含这些
    for key in ("capabilities", "reasoning_field", "forward_tool_choice",
                "quirks", "extra_body_template", "top_level_kwargs"):
        assert key in profile, f"openai_compatible profile 应有 {key} 字段"
    print("[OK] PROFILES 含 openai_compatible 文档示例")


# ─── 5. ★ 通用接口 4 行 e2e(Step 5 关键验收) ─────

def test_minimal_4_line_provider_block_works():
    """**Plan §G Step 5 关键验收**: 只声明 profile + api_key + base_url + model 4 个字段,
    其他全部 fallback,能成功构造 LLMClient 且默认表生效。"""
    cfg = _write_temp_config({
        "通用接口": {
            "profile": "openai_compatible",       # 第 1 行
            "api_key": "sk-test",                  # 第 2 行
            "base_url": "https://your-endpoint/v1",# 第 3 行
            "model": "your-model"                  # 第 4 行
        }
    }, "通用接口")
    with _clean_env("OPENAI_API_KEY", "LLM_API_KEY"):
        ad = LLMClient(cfg)
    # 构造成功
    assert ad.get_provider() == "通用接口"
    assert ad.get_model_name() == "your-model"
    # 所有 Step 5 三件套 fallback 到 OpenAI 兼容默认
    assert ad.extra_body_template is None, "未声明 → None(不注入)"
    assert ad.top_level_kwargs == {}, "未声明 → 空"
    assert ad.forward_tool_choice is False, "未声明 → False"
    # 其他 step fallback
    assert ad.has_capability("chat") and ad.has_capability("tools")
    assert not ad.has_capability("vision"), "未声明 vision capability"
    assert ad.reasoning_field == "delta.reasoning_content", "默认 OpenAI 标准"
    assert ad.quirks == (), "默认无 quirk"
    # build_request_kwargs 数据驱动验证 — 一个最简请求
    req = build_request_kwargs(ad, [{"role": "user", "content": "hi"}])
    assert req["model"] == "your-model"
    assert req["messages"] == [{"role": "user", "content": "hi"}]
    assert "extra_body" not in req, "未声明 extra_body_template → 不注入"
    assert "reasoning_effort" not in req, "未声明 top_level_kwargs → 不注入"
    print("[OK] 通用接口 4 行 config 完整 e2e: 构造 + property + build_request_kwargs")


# ─── 6. v1 / v2 兼容性 ─────────────────────

def test_v1_config_backward_compat():
    """v1 schema(无 Step 5 字段)应继续工作,走 _DEFAULT_* fallback"""
    cfg = _write_temp_config({
        "deepseek": {  # v1: 无 extra_body_template / top_level_kwargs / forward_tool_choice
            "api_key": "sk-test",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "thinking": "enabled",
        }
    }, "deepseek")
    ad = LLMClient(cfg)
    # 默认表 fallback 生效,行为等价于 v2 显式声明
    assert "thinking" in ad.extra_body_template
    assert ad.top_level_kwargs == {}
    assert ad.forward_tool_choice is False
    # build_request_kwargs 产生与旧 if-else 一致的 request
    req = build_request_kwargs(ad, [{"role": "user", "content": "x"}])
    assert req["extra_body"] == {"thinking": {"type": "enabled"}}, "v1 config 应得到旧 if-else 等价输出"
    print("[OK] v1 config 向后兼容(走 _DEFAULT_* fallback)")


def test_v2_config_explicit_fields_take_effect():
    """v2 schema 显式声明所有字段,字段直接生效(不依赖默认表)"""
    cfg = _write_temp_config({
        "我的新模型": {
            "profile": "openai_compatible",
            "api_key": "sk-test",
            "base_url": "https://my-endpoint/v1",
            "model": "my-model",
            "thinking": "enabled",
            "reasoning_effort": "medium",
            "capabilities": ["chat", "tools", "vision", "reasoning"],
            "reasoning_field": "delta.my_path.r",
            "forward_tool_choice": True,
            "extra_body_template": '{"my_param": "${thinking}"}',
            "top_level_kwargs": {"my_kwarg": "${reasoning_effort}"},
            "quirks": [],
        }
    }, "我的新模型")
    with _clean_env("OPENAI_API_KEY", "LLM_API_KEY"):
        ad = LLMClient(cfg)
    # 所有 Step 5 字段生效
    assert ad.extra_body_template == '{"my_param": "${thinking}"}'
    assert ad.top_level_kwargs == {"my_kwarg": "${reasoning_effort}"}
    assert ad.forward_tool_choice is True
    # build_request_kwargs 渲染正确
    req = build_request_kwargs(ad, [{"role": "user", "content": "x"}])
    assert req["extra_body"] == {"my_param": "enabled"}
    assert req["my_kwarg"] == "medium"
    print("[OK] v2 config 显式字段全部生效 + 渲染正确")


# ─── 7. build_request_kwargs 直接调用 ─────

def test_build_request_kwargs_renders_extra_body_with_thinking():
    cfg = _write_temp_config({"deepseek": _block({"thinking": "enabled"})}, "deepseek")
    ad = LLMClient(cfg)
    req = build_request_kwargs(ad, [{"role": "user", "content": "x"}])
    assert req["extra_body"] == {"thinking": {"type": "enabled"}}
    print("[OK] build_request_kwargs 渲染 deepseek extra_body")


def test_build_request_kwargs_skips_extra_body_when_thinking_disabled():
    """thinking=disabled 时不注入 extra_body(与旧行为一致)"""
    cfg = _write_temp_config({"deepseek": _block({"thinking": "disabled"})}, "deepseek")
    ad = LLMClient(cfg)
    req = build_request_kwargs(ad, [{"role": "user", "content": "x"}])
    assert "extra_body" not in req
    print("[OK] build_request_kwargs thinking=disabled 时跳过 extra_body")


def test_build_request_kwargs_forwards_tool_choice():
    cfg = _write_temp_config({"sensenova": _block()}, "sensenova")
    ad = LLMClient(cfg)
    req = build_request_kwargs(ad, [{"role": "user", "content": "x"}], tool_choice="auto")
    assert req["tool_choice"] == "auto"
    print("[OK] build_request_kwargs 转发 tool_choice (sensenova)")


# ─── 8. 静态检查 config 文件 ─────────────────

def test_src_config_is_v2_schema():
    """src/config.json 应已升级到 v2 显式版"""
    cfg_text = (ROOT / "src" / "config.json").read_text(encoding="utf-8")
    cfg = json.loads(cfg_text)
    sensenova_block = cfg["providers"]["sensenova"]
    assert "profile" in sensenova_block, "v2 应有 profile 字段"
    assert sensenova_block.get("capabilities"), "v2 应显式声明 capabilities"
    assert sensenova_block.get("reasoning_field"), "v2 应显式声明 reasoning_field"
    assert sensenova_block.get("quirks"), "v2 应显式声明 quirks"
    assert "top_level_kwargs" in sensenova_block, "v2 应显式声明 top_level_kwargs"
    print("[OK] src/config.json 已升级到 v2 显式 schema")


def test_config_example_exists_with_4_line_template():
    """src/config.example.json 应存在且含通用接口 4 行模板示例"""
    path = ROOT / "src" / "config.example.json"
    assert path.exists(), "应新增 src/config.example.json"
    text = path.read_text(encoding="utf-8")
    assert "通用接口" in text, "示例应含'通用接口'示范"
    assert '"profile": "openai_compatible"' in text, "示例应使用 openai_compatible profile"
    print("[OK] src/config.example.json 含 4 行通用接口示例")


if __name__ == "__main__":
    test_default_extra_body_template_deepseek()
    test_default_extra_body_template_agnes()
    test_default_extra_body_template_sensenova_none()
    test_default_top_level_kwargs_sensenova()
    test_default_top_level_kwargs_deepseek_empty()
    test_default_forward_tool_choice()
    test_default_forward_tool_choice_unknown_provider_false()
    test_extra_body_template_block_override()
    test_top_level_kwargs_block_override()
    test_forward_tool_choice_block_override()
    test_build_client_from_dict()
    test_build_client_empty_config_raises()
    test_build_client_override_provider()
    test_profiles_has_openai_compatible()
    test_minimal_4_line_provider_block_works()
    test_v1_config_backward_compat()
    test_v2_config_explicit_fields_take_effect()
    test_build_request_kwargs_renders_extra_body_with_thinking()
    test_build_request_kwargs_skips_extra_body_when_thinking_disabled()
    test_build_request_kwargs_forwards_tool_choice()
    test_src_config_is_v2_schema()
    test_config_example_exists_with_4_line_template()

    print()
    print("=" * 60)
    print("✓ Step 5 全部 22 个测试通过 — 数据驱动构造 + v2 schema + 通用接口 4 行")
    print("=" * 60)
