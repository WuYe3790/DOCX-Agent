"""tests for render_diagram tool — 最小集合 (Step 10)

覆盖:
- 编码协议正确性 (zlib 头尾 / Unicode / URL-safe / 无 padding)
- 主成功路径 (GET → 200 → PNG 文件落地)
- 主错误路径 (400 → syntax_error + stderr 透传)
- 参数防御 (非法 language / 越权 filename / 空 source)

不在本文件覆盖的 (留给 Step 11 的补全套件):
- 503 重试链路
- Timeout 异常处理
- POST 阈值切换
- 日志路径写入
"""
import base64
import json
import sys
import zlib
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from basic_tools import render_diagram as rd  # noqa: E402
from basic_tools.render_diagram import (  # noqa: E402
    _kroki_encode_source,
    PNG_MAGIC,
    render_diagram,
)


# ============ Fixtures ============

@pytest.fixture
def tmp_root(monkeypatch, tmp_path):
    """与项目其他测试一致 (e.g. test_unzip_docx_sandbox.py:17-23):
    把 WORKSPACE_ROOT 重定向到 tmp_path/sessions, 测试落地到 tmp。
    """
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    import workspace.guard as guard
    monkeypatch.setattr(guard, "WORKSPACE_ROOT", sessions)
    return sessions


@pytest.fixture
def session_id(tmp_root):
    """建好 sessions/<id>/workspace 的 session_id"""
    sid = "sess-render-test"
    from workspace.guard import workspace_dir
    workspace_dir(sid)  # 触发 mkdir
    return sid


def _fake_png_bytes() -> bytes:
    """构造最小合法 PNG (8 字节 magic + 占位字节, 足够通过 magic 校验)"""
    return PNG_MAGIC + b"\x00" * 32


def _make_resp(status_code: int, content: bytes = b"", text: str = ""):
    """构造 mock 的 requests Response"""
    resp = Mock()
    resp.status_code = status_code
    resp.content = content
    resp.text = text or content.decode("utf-8", errors="replace")
    return resp


# ============ 编码协议测试 (防回归核心) ============

def test_kroki_encode_simple_ascii():
    """简单 ASCII 源码: 编码后能反解回原文"""
    src = "digraph G { A -> B }"
    encoded = _kroki_encode_source(src)
    # 反解: 加回 padding -> b64decode -> zlib.decompress
    pad = "=" * (-len(encoded) % 4)
    compressed = base64.urlsafe_b64decode(encoded + pad)
    decoded = zlib.decompress(compressed).decode("utf-8")
    assert decoded == src


def test_kroki_encode_unicode():
    """含中文/emoji 的源码: UTF-8 字节序正确"""
    src = "digraph G { 节点A -> 节点B [label=\"启动 🚀\"] }"
    encoded = _kroki_encode_source(src)
    pad = "=" * (-len(encoded) % 4)
    compressed = base64.urlsafe_b64decode(encoded + pad)
    decoded = zlib.decompress(compressed).decode("utf-8")
    assert decoded == src


def test_kroki_encode_keeps_zlib_header_and_checksum():
    """⚠️ 核心防回归: 编码必须保留完整 zlib 包装 (78 头 + adler32 尾)

    一旦未来有人误改成 zlib.compress(...)[2:-4] (PlantUML 风格切片),
    这条测试立刻挂掉。Kroki 用 Java Inflater 反序列化, 要完整 zlib。

    zlib 首字节固定 0x78 (CMF byte = 8 (deflate) + 7<<4 (32KB window)),
    次字节因压缩级别而变 (level 6 → 9C, level 9 → DA),
    所以只校验首字节而不锁次字节。
    """
    src = "digraph G { A -> B }"
    encoded = _kroki_encode_source(src)
    pad = "=" * (-len(encoded) % 4)
    compressed = base64.urlsafe_b64decode(encoded + pad)

    # 1) zlib CMF byte (固定 0x78, deflate + 32KB window)
    assert compressed[0] == 0x78, (
        f"首字节应为 0x78 (zlib CMF), 实际 {compressed[:1].hex()}。"
        f" 如果这条挂了, 极有可能是有人把 _kroki_encode_source 改成了"
        f" zlib.compress(...)[2:-4] —— 那是 plantuml.com 自己 server 的旧协议,"
        f" Kroki 不接受。"
    )
    # 2) zlib.decompress 完整还原 = adler32 校验通过 = 尾部 4 字节也在
    #    (raw deflate 没有 adler32 尾, decompress 会失败)
    assert zlib.decompress(compressed).decode("utf-8") == src


def test_kroki_encode_no_padding():
    """编码末尾不能有 '=' padding (Kroki URL path 段不接受)"""
    src = "digraph G { A -> B }"
    encoded = _kroki_encode_source(src)
    assert not encoded.endswith("=")


def test_kroki_encode_url_safe():
    """编码必须用 URL-safe base64 字母表 (- 和 _ 而非 + 和 /)"""
    # 构造一个能产生足够多字节的源码, 触发常见 base64 输出
    src = "digraph G { " + " ".join(f"n{i} -> n{i+1};" for i in range(50)) + " }"
    encoded = _kroki_encode_source(src)
    assert "+" not in encoded and "/" not in encoded


# ============ 主成功路径 ============

def test_render_diagram_success_get(monkeypatch, session_id, tmp_root):
    """简单 DOT → 200 + PNG → 文件落地 workspace/media/diagram.png"""
    fake_png = _fake_png_bytes()
    calls = []

    def fake_get(url, **kwargs):
        calls.append(("GET", url))
        return _make_resp(200, content=fake_png)

    monkeypatch.setattr(rd.requests, "get", fake_get)

    result = json.loads(render_diagram(session_id, "digraph G { A -> B }"))

    assert result["status"] == "ok"
    assert result["language"] == "graphviz"
    assert result["path"] == "media/diagram.png"
    assert result["transport"] == "GET"
    assert result["size_bytes"] == len(fake_png)

    # 文件确实写入了
    target = tmp_root / session_id / "workspace" / "media" / "diagram.png"
    assert target.exists()
    assert target.read_bytes() == fake_png

    # URL 形如 https://kroki.io/graphviz/png/<encoded>
    assert len(calls) == 1
    assert calls[0][1].startswith("https://kroki.io/graphviz/png/")


def test_render_diagram_mermaid_language(monkeypatch, session_id):
    """language=mermaid 时 URL path 是 .../mermaid/png/..."""
    urls = []
    def fake_get(url, **kw):
        urls.append(url)
        return _make_resp(200, content=_fake_png_bytes())
    monkeypatch.setattr(rd.requests, "get", fake_get)

    result = json.loads(render_diagram(
        session_id, "graph TD; A-->B;", language="mermaid"
    ))
    assert result["status"] == "ok"
    assert result["language"] == "mermaid"
    assert urls[0].startswith("https://kroki.io/mermaid/png/")


# ============ 主错误路径: HTTP 400 语法错误 ============

def test_render_diagram_syntax_error_400(monkeypatch, session_id):
    """HTTP 400 + plain text stderr → error_type=syntax_error, stderr 透传给 LLM"""
    stderr_msg = "Error: syntax error near line 3, missing semicolon"
    monkeypatch.setattr(
        rd.requests, "get",
        lambda url, **kw: _make_resp(400, content=stderr_msg.encode(), text=stderr_msg),
    )

    bad_dot = "digraph G { A -> B A -> C }"  # 故意少分号
    result = json.loads(render_diagram(session_id, bad_dot))

    assert result["status"] == "error"
    assert result["error_type"] == "syntax_error"
    assert result["language"] == "graphviz"
    assert stderr_msg in result["renderer_stderr"]
    assert result["source_snippet"].startswith("digraph G {")
    assert "DOT 必须以" in result["hint"]


def test_render_diagram_syntax_error_mermaid_hint(monkeypatch, session_id):
    """mermaid 语法错误时 hint 是 mermaid 特定的"""
    monkeypatch.setattr(
        rd.requests, "get",
        lambda url, **kw: _make_resp(400, content=b"Parse error", text="Parse error"),
    )
    result = json.loads(render_diagram(
        session_id, "graph TD; A-->;", language="mermaid"
    ))
    assert result["error_type"] == "syntax_error"
    assert "Mermaid" in result["hint"]


# ============ 参数防御 (不进 HTTP) ============

def test_render_diagram_bad_language(session_id):
    """非法 language → bad_argument, 不进 HTTP"""
    result = json.loads(render_diagram(session_id, "x", language="plantuml"))
    assert result["status"] == "error"
    assert result["error_type"] == "bad_argument"
    assert "plantuml" in result["message"]


def test_render_diagram_bad_filename(session_id):
    """output_filename 含路径分隔符或 .. → bad_argument"""
    for bad in ["../escape.png", "media/sub.png", "..\\evil.png"]:
        result = json.loads(render_diagram(
            session_id, "digraph G { A -> B }", output_filename=bad
        ))
        assert result["status"] == "error", f"应拒绝 {bad!r}"
        assert result["error_type"] == "bad_argument"


def test_render_diagram_empty_source(session_id):
    """空 source → bad_argument"""
    for empty in ["", "   ", "\n\n"]:
        result = json.loads(render_diagram(session_id, empty))
        assert result["status"] == "error"
        assert result["error_type"] == "bad_argument"
