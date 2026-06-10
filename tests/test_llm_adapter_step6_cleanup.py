"""Step 6 回归测试 — 遗留清理 + DeprecationWarning

测什么:
1. **DeprecationWarning 触发**:
   - base_url 子串启发式(顶层无 provider 字段但 base_url 含 sensenova/agnes/deepseek)
   - flat config(顶层 api_key/base_url 但 providers 嵌套块缺失)
2. **遗留文件已删除**:
   - src/_llm_adapter_legacy.py 不存在
   - 不能再 import _llm_adapter_legacy
3. **server.py 清理**:
   - if provider == "deepseek" / "sensenova" / "agnes" 分支已删除
   - 改为通用读取 thinking_type + reasoning_effort
4. **依赖兼容**(server.py / agent.py / analyze_image_content.py 的 import 仍工作)
"""

import os
import sys
import json
import tempfile
import warnings
import contextlib
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))


@contextlib.contextmanager
def _clean_env(*keys: str):
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def _write_temp_config(data: dict) -> str:
    path = Path(tempfile.mkdtemp(prefix="docx_agent_step6_")) / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ─── DeprecationWarning 触发 ────────────────────────

def test_deprecation_warning_on_base_url_heuristic():
    """顶层未声明 provider + base_url 含 sensenova → DeprecationWarning"""
    # flat config(无 providers 嵌套块,只用顶层 base_url + api_key)
    cfg = {"base_url": "https://token.sensenova.cn/v1", "api_key": "sk-test"}
    cfg_path = _write_temp_config(cfg)
    with _clean_env("LLM_PROVIDER", "OPENAI_API_KEY", "LLM_API_KEY"):
        # 必须重置 __warningregistry__ — 同一进程内多次构造同 module 同 lineno 默认只 warn 一次
        from llm_adapter.provider import LLMClient
        if hasattr(LLMClient.__init__.__code__, '__warningregistry__'):
            LLMClient.__init__.__code__.__warningregistry__.clear()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = LLMClient(cfg_path)
        # 至少有一个 DeprecationWarning
        deprecation_msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecation_msgs, f"应触发 DeprecationWarning,实际 caught={[str(w.message) for w in caught]}"
        assert any("base_url" in m and "deprecated" in m for m in deprecation_msgs), \
            "base_url 启发式的 DeprecationWarning 应明确提到 base_url + deprecated"
        assert client.get_provider() == "sensenova"   # 启发式仍然生效(只是 warn)
    print("[OK] base_url 启发式触发 DeprecationWarning")


def test_deprecation_warning_on_flat_config():
    """deepseek + flat config(顶层 api_key/base_url + 无 providers.deepseek) → DeprecationWarning"""
    cfg = {
        "provider": "deepseek",
        "api_key": "sk-test",
        "base_url": "https://api.deepseek.com",
    }
    cfg_path = _write_temp_config(cfg)
    with _clean_env("LLM_PROVIDER", "DEEPSEEK_API_KEY", "LLM_API_KEY"):
        from llm_adapter.provider import LLMClient
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = LLMClient(cfg_path)
        deprecation_msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecation_msgs, "flat config 应触发 DeprecationWarning"
        assert any("flat config" in m and "deprecated" in m for m in deprecation_msgs), \
            "flat config 的 DeprecationWarning 应明确提到 flat config + deprecated"
        assert client.get_provider() == "deepseek"   # flat config 仍然生效
        assert client.api_key == "sk-test"
    print("[OK] flat config 触发 DeprecationWarning")


def test_no_warning_on_proper_v2_config():
    """v2 config(显式 provider + 嵌套 providers 块) → 不应触发 DeprecationWarning"""
    cfg = {
        "provider": "deepseek",
        "providers": {
            "deepseek": {
                "api_key": "sk-test",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
            }
        }
    }
    cfg_path = _write_temp_config(cfg)
    with _clean_env("LLM_PROVIDER", "DEEPSEEK_API_KEY", "LLM_API_KEY"):
        from llm_adapter.provider import LLMClient
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client = LLMClient(cfg_path)
        deprecation_msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        assert not deprecation_msgs, f"v2 config 不应触发 DeprecationWarning,实际:{deprecation_msgs}"
    print("[OK] v2 config 不触发 DeprecationWarning")


# ─── 遗留文件已删除 ──────────────────────────────

def test_legacy_adapter_file_removed():
    """src/_llm_adapter_legacy.py 已 Step 6 删除"""
    legacy = ROOT / "src" / "_llm_adapter_legacy.py"
    assert not legacy.exists(), f"src/_llm_adapter_legacy.py 应已删除,但仍存在"
    print("[OK] src/_llm_adapter_legacy.py 已删除")


def test_legacy_adapter_unimportable():
    """import _llm_adapter_legacy 应失败"""
    try:
        import _llm_adapter_legacy   # noqa: F401
        raise AssertionError("应该 import 失败")
    except ImportError:
        pass
    print("[OK] import _llm_adapter_legacy 失败(已删除)")


# ─── server.py 清理 ────────────────────────────

def test_server_no_provider_if_else():
    """server.py 的 if-provider 分支(if provider == 'deepseek' / 'sensenova' / 'agnes') 已删除"""
    src = ROOT / "src" / "server.py"
    text = src.read_text(encoding="utf-8")
    assert 'if provider == "deepseek":' not in text, \
        "server.py 应删除 if-provider 分支(start_config 现在用通用读取)"
    assert 'elif provider == "sensenova":' not in text
    assert 'elif provider == "agnes":' not in text
    print("[OK] server.py 已删除 if-provider 分支")


def test_server_uses_generic_adapter_state():
    """server.py 改用通用 thinking_type / reasoning_effort 读取(任何 provider 自动适应)"""
    src = ROOT / "src" / "server.py"
    text = src.read_text(encoding="utf-8")
    assert "adapter.get_thinking_type()" in text
    assert "adapter.get_reasoning_effort()" in text
    print("[OK] server.py 改用通用读取(任何 provider 自适应)")


# ─── 依赖兼容 ────────────────────────────────

def test_callers_still_import_correctly():
    """server.py / agent.py / analyze_image_content.py 的 import 仍工作"""
    from llm_adapter import LLMClientAdapter
    from llm_adapter.response_parser import extract_reasoning
    from llm_adapter.quirks import apply_quirk, QuirkAction
    from llm_adapter.registry import pick_capable_adapter, build_client
    # 烟雾测试:能 callable
    assert callable(LLMClientAdapter)
    assert callable(extract_reasoning)
    assert callable(apply_quirk)
    assert callable(pick_capable_adapter)
    assert callable(build_client)
    print("[OK] 所有调用方 import 路径仍工作")


if __name__ == "__main__":
    test_legacy_adapter_file_removed()
    test_legacy_adapter_unimportable()
    test_server_no_provider_if_else()
    test_server_uses_generic_adapter_state()
    test_callers_still_import_correctly()
    test_deprecation_warning_on_base_url_heuristic()
    test_deprecation_warning_on_flat_config()
    test_no_warning_on_proper_v2_config()

    print()
    print("=" * 60)
    print("✓ Step 6 全部 8 个测试通过 — 遗留清理 + DeprecationWarning 落地")
    print("=" * 60)
