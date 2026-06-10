"""Step 2 回归测试 — capability 系统 + pick_capable_adapter 工厂 + analyze_image_content 改造

测什么:
1. **has_capability 真实实现**:
   - 默认表(_DEFAULT_CAPABILITIES): deepseek/sensenova/agnes 三家硬编码
   - provider block 显式声明 capabilities 字段 → 覆盖默认表
   - 未知 provider → _FALLBACK_CAPABILITIES = {"chat","tools"}

2. **pick_capable_adapter 工厂**(Review #2 落地的核心):
   - current 已具备 → 直接返回 current (is 关系)
   - current 不具备 + config 有 fallback → 返回新 LLMClient
   - current 不具备 + 无 fallback → 返回 None
   - **关键反模式消除**: 不污染 os.environ['LLM_PROVIDER']

3. **analyze_image_content.py 改造** (静态代码检查):
   - 已 import 并调用 pick_capable_adapter
   - 不再含 os.environ mutation
   - 不再含 {"sensenova","openai","gemini"} 硬编码白名单

策略:用临时 config.json (写到 tempdir) 隔离测试与项目实际 config,
避免修改 src/config.json 影响测试 / 反之。
"""

import os
import sys
import json
import tempfile
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llm_adapter.provider import LLMClient                # noqa: E402
from llm_adapter.registry import pick_capable_adapter     # noqa: E402


# ─── 工具: 隔离 env vars(避免测试受跑测试机器的 shell 影响) ────

@contextlib.contextmanager
def _clean_env(*keys: str):
    """临时清掉指定 env vars,with 块退出后恢复原值。

    用途:LLMClient 对未知 provider 走 `else` 分支时,会从 OPENAI_API_KEY/
    LLM_API_KEY 等 env vars 抢 api_key — 这让"坏配置应构造失败"的测试
    依赖跑测试机器的 shell 状态。clean 掉后测试可重复。
    """
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ─── 工具: 写临时 config.json ──────────────────────────────────

def _write_temp_config(providers_block: dict, active_provider: str) -> str:
    """写一个临时 config.json,返回路径(str)。"""
    cfg = {"provider": active_provider, "providers": providers_block}
    tmp_dir = Path(tempfile.mkdtemp(prefix="docx_agent_step2_"))
    path = tmp_dir / "config.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return str(path)


# 通用最小 provider block(api_key + base_url + model 三件套,api_key 不能为空否则 __init__ 抛 RuntimeError)
def _block(extra: dict = None) -> dict:
    base = {"api_key": "sk-test", "base_url": "https://example.com/v1", "model": "test-model"}
    if extra:
        base.update(extra)
    return base


# ─── has_capability:默认表 ───────────────────────────────────

def test_has_capability_default_table_sensenova_has_vision():
    cfg_path = _write_temp_config({"sensenova": _block()}, "sensenova")
    ad = LLMClient(cfg_path)
    assert ad.has_capability("chat")
    assert ad.has_capability("tools")
    assert ad.has_capability("reasoning")
    assert ad.has_capability("vision"), "sensenova 默认应有 vision"
    print("[OK] has_capability default: sensenova 含 vision")


def test_has_capability_default_table_deepseek_no_vision():
    cfg_path = _write_temp_config({"deepseek": _block()}, "deepseek")
    ad = LLMClient(cfg_path)
    assert ad.has_capability("chat")
    assert ad.has_capability("tools")
    assert ad.has_capability("reasoning")
    assert not ad.has_capability("vision"), "deepseek 默认不应有 vision"
    print("[OK] has_capability default: deepseek 无 vision")


def test_has_capability_default_table_agnes_no_vision():
    cfg_path = _write_temp_config({"agnes": _block()}, "agnes")
    ad = LLMClient(cfg_path)
    assert ad.has_capability("chat")
    assert ad.has_capability("tools")
    assert ad.has_capability("reasoning")
    assert not ad.has_capability("vision"), "agnes 默认不应有 vision"
    print("[OK] has_capability default: agnes 无 vision")


# ─── has_capability:provider block 覆盖 ────────────────────────

def test_has_capability_block_override():
    """显式 capabilities 列表完全替换默认表 — 不存在的能力会被去掉"""
    cfg_path = _write_temp_config({
        "deepseek": _block({"capabilities": ["chat", "vision"]})  # 加 vision,但移除 tools/reasoning
    }, "deepseek")
    ad = LLMClient(cfg_path)
    assert ad.has_capability("chat")
    assert ad.has_capability("vision"), "显式声明应覆盖默认表加上 vision"
    assert not ad.has_capability("tools"), "显式列表不含 tools → 应失去"
    assert not ad.has_capability("reasoning"), "显式列表不含 reasoning → 应失去"
    print("[OK] has_capability block override 完全替换")


def test_has_capability_block_can_add_new_capability():
    """通用接口 provider 可以在 config 里声明任意 capabilities"""
    cfg_path = _write_temp_config({
        "通用接口": _block({"capabilities": ["chat", "tools", "vision", "speech"]})
    }, "通用接口")
    ad = LLMClient(cfg_path)
    assert ad.has_capability("speech"), "未来扩展能力应能从 config 直接声明"
    print("[OK] has_capability 支持任意未来 capability")


# ─── has_capability:未知 provider fallback ─────────────────────

def test_has_capability_unknown_provider_minimal_fallback():
    cfg_path = _write_temp_config({"我自己的模型": _block()}, "我自己的模型")
    ad = LLMClient(cfg_path)
    # _FALLBACK_CAPABILITIES = {"chat","tools"}
    assert ad.has_capability("chat")
    assert ad.has_capability("tools")
    assert not ad.has_capability("vision")
    assert not ad.has_capability("reasoning")
    print("[OK] has_capability unknown provider → 最低 {chat, tools}")


# ─── pick_capable_adapter:三种路径 ────────────────────────────

def test_pick_capable_current_already_has():
    """current 已具备 → 返回 same instance(is 关系,零开销)"""
    cfg_path = _write_temp_config({
        "sensenova": _block(),
        "deepseek": _block(),
    }, "sensenova")
    ad = LLMClient(cfg_path)
    result = pick_capable_adapter(ad, "vision")
    assert result is ad, "current 已具备 vision,应直接返回 same instance(节省重新构造开销)"
    print("[OK] pick_capable current 已具备 → is 返回")


def test_pick_capable_fallback_to_other_provider():
    """current 不具备 + 有 fallback → 返回新 LLMClient(provider 名为 fallback)"""
    cfg_path = _write_temp_config({
        "deepseek": _block(),    # 无 vision
        "sensenova": _block(),   # 有 vision
    }, "deepseek")
    ad = LLMClient(cfg_path)
    assert ad.get_provider() == "deepseek"
    result = pick_capable_adapter(ad, "vision")
    assert result is not None, "应该能 fallback 到 sensenova"
    assert result is not ad, "fallback 应是新 client 实例"
    assert result.get_provider() == "sensenova", f"应路由到 sensenova,实际 {result.get_provider()}"
    assert result.has_capability("vision")
    print("[OK] pick_capable fallback: deepseek → sensenova")


def test_pick_capable_no_match_returns_none():
    """current 不具备 + 无 fallback → None(不抛错)"""
    cfg_path = _write_temp_config({
        "deepseek": _block(),
        "agnes": _block(),
    }, "deepseek")
    ad = LLMClient(cfg_path)
    result = pick_capable_adapter(ad, "vision")
    assert result is None, "deepseek+agnes 都无 vision → 应返回 None"
    print("[OK] pick_capable no match → None")


def test_pick_capable_does_not_pollute_os_environ():
    """关键反模式消除:不触碰 os.environ['LLM_PROVIDER'](替代旧 analyze_image_content.py:51-59)"""
    cfg_path = _write_temp_config({
        "deepseek": _block(),
        "sensenova": _block(),
    }, "deepseek")
    before = os.environ.get("LLM_PROVIDER", "<unset>")
    ad = LLMClient(cfg_path)
    _ = pick_capable_adapter(ad, "vision")
    after = os.environ.get("LLM_PROVIDER", "<unset>")
    assert before == after, f"os.environ['LLM_PROVIDER'] 被污染: {before!r} → {after!r}"
    print("[OK] pick_capable 不污染 os.environ['LLM_PROVIDER']")


def test_pick_capable_skips_unconfigurable_candidate():
    """候选 provider 缺 api_key → 静默跳过,试下一个能构造的。

    用 _clean_env 隔离 OPENAI_API_KEY/LLM_API_KEY 等全局 env vars,
    确保"坏配置"真正构造失败(否则可能从机器 env 抢到 key 误成功)。
    """
    with _clean_env("OPENAI_API_KEY", "LLM_API_KEY",
                    "DEEPSEEK_API_KEY", "SENSENOVA_API_KEY", "AGNES_API_KEY"):
        cfg_path = _write_temp_config({
            "deepseek": _block(),                                              # 无 vision
            "坏配置": {"base_url": "http://x", "model": "m",                    # 有 vision 显式但无 api_key
                      "capabilities": ["chat", "tools", "vision"]},
            "sensenova": _block(),                                             # 有 vision 且能构造
        }, "deepseek")
        ad = LLMClient(cfg_path)
        result = pick_capable_adapter(ad, "vision")
        assert result is not None
        assert result.get_provider() == "sensenova", f"应跳过坏配置,落到 sensenova,实际 {result.get_provider()}"
    print("[OK] pick_capable 静默跳过缺 api_key 的候选")


def test_pick_capable_provider_override_works():
    """LLMClient(config_path, provider_override=name) 路径正确选 provider"""
    cfg_path = _write_temp_config({
        "deepseek": _block(),
        "sensenova": _block(),
    }, "deepseek")
    # 显式 override 不应受 active provider 影响
    ad = LLMClient(cfg_path, provider_override="sensenova")
    assert ad.get_provider() == "sensenova"
    print("[OK] LLMClient(provider_override=...) 工作")


# ─── analyze_image_content.py 静态改造检查 ───────────────────

def test_analyze_image_content_uses_pick_capable_adapter():
    """static check: analyze_image_content.py 已迁移到 pick_capable_adapter"""
    src = ROOT / "src" / "basic_tools" / "analyze_image_content.py"
    text = src.read_text(encoding="utf-8")
    assert "pick_capable_adapter" in text, "应该 import 并使用 pick_capable_adapter"
    assert 'os.environ["LLM_PROVIDER"]' not in text, "不应再 mutate os.environ['LLM_PROVIDER']"
    assert 'os.environ.pop("LLM_PROVIDER"' not in text
    assert '{"sensenova", "openai", "gemini"}' not in text, "硬编码白名单应已删除"
    print("[OK] analyze_image_content.py 完成 Step 2 改造(静态检查)")


# ─── 向后兼容:Step 1 测试仍应全绿(occluded 的兼容性) ──────────

def test_backward_compat_provider_override_default():
    """不传 provider_override 时,行为应与 Step 1 完全一致"""
    cfg_path = _write_temp_config({"sensenova": _block()}, "sensenova")
    ad = LLMClient(cfg_path)
    assert ad.get_provider() == "sensenova"
    assert ad.has_capability("vision")
    assert isinstance(ad.config_path, Path)
    print("[OK] 默认参数下行为与 Step 1 一致")


if __name__ == "__main__":
    test_has_capability_default_table_sensenova_has_vision()
    test_has_capability_default_table_deepseek_no_vision()
    test_has_capability_default_table_agnes_no_vision()
    test_has_capability_block_override()
    test_has_capability_block_can_add_new_capability()
    test_has_capability_unknown_provider_minimal_fallback()
    test_pick_capable_current_already_has()
    test_pick_capable_fallback_to_other_provider()
    test_pick_capable_no_match_returns_none()
    test_pick_capable_does_not_pollute_os_environ()
    test_pick_capable_skips_unconfigurable_candidate()
    test_pick_capable_provider_override_works()
    test_analyze_image_content_uses_pick_capable_adapter()
    test_backward_compat_provider_override_default()

    print()
    print("=" * 60)
    print("✓ Step 2 全部 14 个测试通过 — capability 配置化 + pick_capable_adapter 落地")
    print("=" * 60)
