"""v3 测试: /api/word/preview HTTP 端点

覆盖:
  - 有效 session_id + 真实 .docx → 200 + 正确 content-type
  - 越界 session_id → 400
  - 文件不存在 → 404
  - Cache-Control: no-store header
  - 路径是目录 → 400
  - 空 session_id → 400

设计:
  - 用 fastapi.testclient.TestClient (不真起服务, 0 端口开销)
  - monkeypatch WORKSPACE_ROOT 到 tmp_path, 隔离文件系统
  - 用 _build_minimal_docx 工厂造测试 docx
"""
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# 复用 test_docx_preview_diff.py 的 _build_minimal_docx
from tests.test_docx_preview_diff import _build_minimal_docx  # noqa: E402


# === fixtures ===

@pytest.fixture
def tmp_workspace_root(monkeypatch, tmp_path: Path) -> Path:
    """monkeypatch WORKSPACE_ROOT 到 tmp_path, 返回 sessions 根目录."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    import workspace.guard as guard
    monkeypatch.setattr(guard, "WORKSPACE_ROOT", sessions)
    return sessions


@pytest.fixture
def session_with_docx(tmp_workspace_root: Path) -> tuple[str, Path]:
    """建一个 session 目录 + workspace + 一个合法 docx, 返回 (session_id, docx_path)."""
    session_id = "sess-preview-test"
    from workspace.guard import workspace_dir
    ws = workspace_dir(session_id)  # 自动 mkdir
    docx_path = ws / "test_input.docx"
    _build_minimal_docx(docx_path, ["第一段", "第二段", "第三段"])
    return session_id, docx_path


@pytest.fixture
def client(tmp_workspace_root: Path) -> TestClient:
    """FastAPI TestClient, WORKSPACE_ROOT 已重定向到 tmp_path."""
    # 必须 monkeypatch 完再 import server (因为 server.py 在模块级 import)
    from src.server import app
    return TestClient(app)


# === 测试 ===

class TestWordPreviewEndpoint:
    """/api/word/preview: 5 个 case."""

    def test_valid_session_and_docx_returns_200(
        self, client: TestClient, session_with_docx: tuple[str, Path]
    ):
        """有效 session_id + 真实 .docx → 200, content-type 正确, body 是 docx 二进制."""
        session_id, docx_path = session_with_docx
        # docx_path 在 workspace 下的相对路径
        rel_path = docx_path.name  # "test_input.docx"

        response = client.get(
            f"/api/word/preview?session_id={session_id}&path={rel_path}"
        )

        assert response.status_code == 200
        # content-type 应是 docx mime
        ct = response.headers.get("content-type", "")
        assert "officedocument.wordprocessingml" in ct, (
            f"content-type 应是 docx mime, 实际: {ct}"
        )
        # body 应是 zip 格式 (docx 是 zip)
        body = response.content
        assert body[:2] == b"PK", f"body 应以 PK 开头 (zip 格式), 实际: {body[:4]!r}"
        # 能被 zipfile 读
        import io
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            assert "word/document.xml" in zf.namelist()

    def test_cache_control_header_no_store(
        self, client: TestClient, session_with_docx: tuple[str, Path]
    ):
        """响应头含 Cache-Control: no-store (前端用 ?v=<mtime> 自己控缓存)."""
        session_id, docx_path = session_with_docx

        response = client.get(
            f"/api/word/preview?session_id={session_id}&path={docx_path.name}"
        )

        assert response.status_code == 200
        cc = response.headers.get("cache-control", "")
        assert "no-store" in cc, f"Cache-Control 应含 no-store, 实际: {cc}"

    def test_session_id_with_traversal_returns_400(self, client: TestClient):
        """session_id 含 '..' → 400 (workspace.guard 的 5 层防御)."""
        response = client.get(
            "/api/word/preview?session_id=..%2F..&path=test.docx"
        )
        assert response.status_code == 400, (
            f"越界 session_id 应 400, 实际: {response.status_code} {response.text}"
        )

    def test_empty_session_id_returns_400(self, client: TestClient):
        """空 session_id → 400."""
        response = client.get(
            "/api/word/preview?session_id=&path=test.docx"
        )
        # validate_session_id 拒绝空 → WorkspacePathError → 400
        assert response.status_code == 400

    def test_file_not_found_returns_404(
        self, client: TestClient, session_with_docx: tuple[str, Path]
    ):
        """session_id 有效, 但 path 文件不存在 → 404."""
        session_id, _ = session_with_docx

        response = client.get(
            f"/api/word/preview?session_id={session_id}&path=nonexistent.docx"
        )
        assert response.status_code == 404, (
            f"文件不存在应 404, 实际: {response.status_code} {response.text}"
        )

    def test_path_is_directory_returns_400(
        self, client: TestClient, session_with_docx: tuple[str, Path]
    ):
        """path 是目录而非文件 → 400 (must_be_file=True)."""
        session_id, _ = session_with_docx
        # 在 workspace 下建一个子目录
        from workspace.guard import workspace_dir
        ws = workspace_dir(session_id)
        subdir = ws / "subdir"
        subdir.mkdir()

        response = client.get(
            f"/api/word/preview?session_id={session_id}&path=subdir"
        )
        assert response.status_code == 400, (
            f"path 是目录应 400, 实际: {response.status_code} {response.text}"
        )

    def test_path_outside_workspace_returns_400(self, client: TestClient):
        """path 试图访问 workspace 外的文件 → 400 (越界检测)."""
        response = client.get(
            "/api/word/preview?session_id=sess-preview-test&path=..%2F..%2Fwindows%2Fsystem32%2Fdrivers%2Fetc%2Fhosts"
        )
        # workspace 校验会拒绝 (含 ..)
        assert response.status_code == 400
