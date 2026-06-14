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


# ============ 503 重试链路 (Step 11 补全) ============

def test_render_diagram_503_retry_then_success(monkeypatch, session_id):
    """503 两次后 200: 共调 3 次, 最终成功 (KROKI_MAX_RETRIES = 2)"""
    monkeypatch.setattr(rd.time, "sleep", lambda s: None)  # 加速测试
    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return _make_resp(503, text="upstream timeout")
        return _make_resp(200, content=_fake_png_bytes())

    monkeypatch.setattr(rd.requests, "get", fake_get)
    result = json.loads(render_diagram(session_id, "digraph G { A -> B }"))
    assert result["status"] == "ok"
    assert call_count["n"] == 3, "应在第 3 次成功 (1 初始 + 2 重试)"


def test_render_diagram_503_exhausted(monkeypatch, session_id):
    """503 连续 (1 初始 + KROKI_MAX_RETRIES 重试) → renderer_unavailable"""
    monkeypatch.setattr(rd.time, "sleep", lambda s: None)
    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        return _make_resp(503, text="upstream overload")

    monkeypatch.setattr(rd.requests, "get", fake_get)
    result = json.loads(render_diagram(session_id, "digraph G { A -> B }"))
    assert result["status"] == "error"
    assert result["error_type"] == "renderer_unavailable"
    assert result["http_status"] == 503
    assert call_count["n"] == 3, "应重试 KROKI_MAX_RETRIES(2) 次, 共 3 次 HTTP 调用"


# ============ Timeout / 网络异常 ============

def test_render_diagram_timeout(monkeypatch, session_id):
    """requests.Timeout 持续 → renderer_unavailable, 经过重试耗尽"""
    import requests as _real_requests
    monkeypatch.setattr(rd.time, "sleep", lambda s: None)
    call_count = {"n": 0}

    def fake_get(url, **kwargs):
        call_count["n"] += 1
        raise _real_requests.Timeout("connection timeout")

    monkeypatch.setattr(rd.requests, "get", fake_get)
    result = json.loads(render_diagram(session_id, "digraph G { A -> B }"))
    assert result["status"] == "error"
    assert result["error_type"] == "renderer_unavailable"
    # 主入口 catch requests.RequestException 后给出"网络异常"消息
    assert "网络异常" in result["message"]
    assert call_count["n"] == 3, "Timeout 也应重试 KROKI_MAX_RETRIES 次"


def test_render_diagram_connection_error(monkeypatch, session_id):
    """requests.ConnectionError → renderer_unavailable"""
    import requests as _real_requests
    monkeypatch.setattr(rd.time, "sleep", lambda s: None)

    def fake_get(url, **kwargs):
        raise _real_requests.ConnectionError("DNS resolve failed")

    monkeypatch.setattr(rd.requests, "get", fake_get)
    result = json.loads(render_diagram(session_id, "digraph G { A -> B }"))
    assert result["status"] == "error"
    assert result["error_type"] == "renderer_unavailable"


# ============ POST 阈值切换 ============

def test_render_diagram_post_for_large_source(monkeypatch, session_id):
    """编码后 >= POST_THRESHOLD 时切 POST 路径, GET 一定不被调用"""
    # 构造一个能突破 POST_THRESHOLD 的源码 (随机化文本对抗 zlib 压缩率)
    big_source = "digraph G { " + " ".join(
        f"n{i}_lbl_{hex(i*7919)} [color=\"#{i:06x}\", shape=box];"
        for i in range(500)
    ) + " }"
    encoded_len = len(rd._kroki_encode_source(big_source))
    assert encoded_len >= rd.POST_THRESHOLD, (
        f"测试源码不够长触发 POST, encoded_len={encoded_len} < {rd.POST_THRESHOLD}, "
        f"测试本身需要更多节点 (调高 range)"
    )

    post_calls = []

    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs.get("headers", {}).get("Content-Type")))
        return _make_resp(200, content=_fake_png_bytes())

    monkeypatch.setattr(rd.requests, "post", fake_post)
    # 反向 assert: 如果代码错误地走了 GET 路径, AssertionError 立刻冒出来
    monkeypatch.setattr(
        rd.requests, "get",
        Mock(side_effect=AssertionError("POST 阈值场景不应走 GET")),
    )

    result = json.loads(render_diagram(session_id, big_source))
    assert result["status"] == "ok"
    assert result["transport"] == "POST"
    assert len(post_calls) == 1
    # POST 路径必须用 text/plain Content-Type
    assert post_calls[0][1] == "text/plain"


# ============ 日志路径 ============

def test_render_diagram_writes_success_log(monkeypatch, session_id, tmp_root):
    """成功调用应写 out/sessions/<id>/logs/render_diagram.log, 含 tool_start/tool_done"""
    monkeypatch.setattr(
        rd.requests, "get",
        lambda url, **kw: _make_resp(200, content=_fake_png_bytes()),
    )
    render_diagram(session_id, "digraph G { A -> B }")

    log_path = tmp_root / session_id / "logs" / "render_diagram.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "tool_start" in content
    assert "tool_done" in content
    assert "language=graphviz" in content


def test_render_diagram_writes_error_log(monkeypatch, session_id, tmp_root):
    """语法错误时也应记录 kroki_error 事件到日志, 便于排查"""
    monkeypatch.setattr(
        rd.requests, "get",
        lambda url, **kw: _make_resp(400, content=b"Error: bad", text="Error: bad"),
    )
    render_diagram(session_id, "digraph G { bad }")

    log_path = tmp_root / session_id / "logs" / "render_diagram.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "kroki_error" in content
    assert "http_status=400" in content
