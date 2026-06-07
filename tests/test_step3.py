"""Step 3 端到端测试: HTTP 控制面 (4 endpoint) + uploads 改路径 + 旧 draft API 删除

测什么:
- GET /api/sessions 空 → []
- GET /api/sessions 有 2 个 → 2 条 (按 updatedAt 倒序)
- GET /api/sessions/{id} 存在 → metadata + messages
- GET /api/sessions/{id} 不存在 → 404
- DELETE /api/sessions/{id} 存在 → 200 + 目录真没了
- DELETE /api/sessions/{id} 不存在 → 200 (幂等)
- POST /api/upload 带 session_id + 真 session → 文件写到 session_dir/uploads/
- POST /api/upload 不带 session_id → 422 (Pydantic 校验)
- POST /api/upload 带不存在 session_id → 404
- 旧 /api/drafts/* 4 个 endpoint → 404 (验证 v1 全局草稿 API 已删)
"""
import sys
import json
import shutil
import tempfile
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fastapi.testclient import TestClient
import server

# 隔离: 把 SESSIONS_ROOT 重定向到 tmpdir
TMP_ROOT = Path(tempfile.mkdtemp(prefix="docx_agent_test_step3_"))
server.SESSIONS_ROOT = TMP_ROOT
TMP_ROOT.mkdir(parents=True, exist_ok=True)

client = TestClient(server.app)


def _make_fake_session(session_id: str, docx_path: str = "/t.docx", title: str = "测试会话") -> Path:
    """手工写一个 session 目录 (含 3 JSON) — 跳过 LLM"""
    session_dir = TMP_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "session_id": session_id,
        "title": title,
        "created_at": "2026-06-07T10:00:00",
        "updated_at": "2026-06-07T10:00:00",
        "docx_path": docx_path,
        "workflow_state": "style_review",
        "session_complete": False,
        "pending_approval": False,
    }
    (session_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    messages = {
        "session_id": session_id,
        "system_prompt": "test",
        "entries": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "好的"},
        ],
        "total_input_tokens": 10,
        "last_prompt_tokens": 5,
    }
    (session_dir / "messages.json").write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")
    workflow = {
        "session_id": session_id,
        "workflow_state": "style_review",
        "stage_called_tools": {},
        "draft_files_written": [],
        "round_index": 0,
    }
    (session_dir / "workflow.json").write_text(json.dumps(workflow, ensure_ascii=False), encoding="utf-8")
    return session_dir


def test_list_sessions_empty():
    """Test 1: GET /api/sessions → 空目录返回 []"""
    # 先清空 TMP_ROOT (test 之间可能残留)
    for d in TMP_ROOT.iterdir():
        if d.is_dir():
            shutil.rmtree(d)
    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    assert resp.json() == []
    print("[OK] Test 1: GET /api/sessions 空 → []")


def test_list_sessions_returns_multiple_sorted_by_updated():
    """Test 2: GET /api/sessions → 2 个 session, 按 updatedAt 倒序"""
    _make_fake_session("session-aaa", title="会话 A")
    # 改 updated_at 让 B 更新
    session_b_dir = _make_fake_session("session-bbb", title="会话 B")
    meta_b = json.loads((session_b_dir / "metadata.json").read_text(encoding="utf-8"))
    meta_b["updated_at"] = "2026-06-07T12:00:00"  # 比 A 新
    (session_b_dir / "metadata.json").write_text(json.dumps(meta_b, ensure_ascii=False), encoding="utf-8")

    resp = client.get("/api/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # B 应在前面 (updatedAt 倒序)
    assert data[0]["id"] == "session-bbb"
    assert data[1]["id"] == "session-aaa"
    assert data[0]["title"] == "会话 B"
    assert data[0]["messageCount"] == 2
    assert data[0]["workflowState"] == "style_review"
    print("[OK] Test 2: GET /api/sessions → 2 条, 按 updatedAt 倒序")


def test_get_session_existing_returns_messages():
    """Test 3: GET /api/sessions/{id} → metadata + messages + approvalPhase"""
    _make_fake_session("session-get-test", docx_path="/abc.docx", title="Get Test")
    resp = client.get("/api/sessions/session-get-test")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "session-get-test"
    assert data["docxPath"] == "/abc.docx"
    assert data["title"] == "Get Test"
    assert data["approvalPhase"] == "style_review"
    assert data["isWaitingApproval"] is False
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    print("[OK] Test 3: GET /api/sessions/{id} → metadata + messages")


def test_get_session_nonexistent_returns_404():
    """Test 4: GET /api/sessions/{id} 不存在 → 404"""
    resp = client.get("/api/sessions/session-does-not-exist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]
    print("[OK] Test 4: GET /api/sessions/{id} 不存在 → 404")


def test_delete_session_existing_removes_directory():
    """Test 5: DELETE /api/sessions/{id} 存在 → 200 + 目录真没了 (含子目录)"""
    session_dir = _make_fake_session("session-to-delete")
    (session_dir / "drafts").mkdir()
    (session_dir / "drafts" / "test.md").write_text("# test", encoding="utf-8")
    (session_dir / "uploads").mkdir()
    (session_dir / "uploads" / "test.docx").write_bytes(b"fake")
    assert session_dir.exists()

    resp = client.delete("/api/sessions/session-to-delete")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert not session_dir.exists(), "目录应该被级联删除"
    # 草稿和上传也应该没了
    assert not (session_dir / "drafts").exists()
    print("[OK] Test 5: DELETE /api/sessions/{id} → 目录级联删除 (含 drafts/ / uploads/)")


def test_delete_session_nonexistent_idempotent():
    """Test 6: DELETE /api/sessions/{id} 不存在 → 200 幂等"""
    resp = client.delete("/api/sessions/session-never-existed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    print("[OK] Test 6: DELETE /api/sessions/{id} 不存在 → 200 幂等")


def test_upload_to_existing_session_writes_to_session_dir():
    """Test 7: POST /api/upload 带 session_id + 真 session → 文件写到 session_dir/uploads/"""
    _make_fake_session("session-upload-test")
    file_content = b"PK\x03\x04 fake docx content"

    resp = client.post(
        "/api/upload",
        data={"session_id": "session-upload-test"},
        files={"file": ("实验报告.docx", io.BytesIO(file_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200, f"上传失败: {resp.text}"
    data = resp.json()
    assert data["status"] == "ok"
    assert data["session_id"] == "session-upload-test"
    # 文件应真写到 session_dir/uploads/
    upload_path = Path(data["absolute_path"])
    assert upload_path.exists()
    assert upload_path.parent.parent == TMP_ROOT / "session-upload-test", f"文件应在 session_dir/uploads/ 下, 实际 {upload_path}"
    assert upload_path.read_bytes() == file_content
    print("[OK] Test 7: POST /api/upload → 文件写到 session_dir/uploads/")


def test_upload_without_session_id_returns_422():
    """Test 8: POST /api/upload 不带 session_id → 422 (Pydantic Form 校验)"""
    file_content = b"PK\x03\x04 fake"
    resp = client.post(
        "/api/upload",
        # 故意不传 session_id
        files={"file": ("test.docx", io.BytesIO(file_content), "application/octet-stream")},
    )
    assert resp.status_code == 422, f"应 422, 实际 {resp.status_code}: {resp.text}"
    print("[OK] Test 8: POST /api/upload 不带 session_id → 422 (Form 校验)")


def test_upload_to_nonexistent_session_returns_404():
    """Test 9: POST /api/upload 带不存在 session_id → 404"""
    file_content = b"PK\x03\x04 fake"
    resp = client.post(
        "/api/upload",
        data={"session_id": "session-not-yet"},
        files={"file": ("test.docx", io.BytesIO(file_content), "application/octet-stream")},
    )
    assert resp.status_code == 404, f"应 404, 实际 {resp.status_code}"
    assert "不存在" in resp.json()["detail"]
    # 副作用: 不应创建任何 session 目录
    assert not (TMP_ROOT / "session-not-yet").exists()
    print("[OK] Test 9: POST /api/upload 带不存在 session_id → 404, 无副作用")


def test_legacy_drafts_api_endpoints_removed():
    """Test 10: 旧 /api/drafts/* + /api/draft/parse 4 个 endpoint 全部 404 (v1 全局草稿 API 已删)"""
    for path, method in [
        ("/api/drafts/list", "GET"),
        ("/api/drafts/read", "GET"),
        ("/api/drafts/save", "POST"),
        ("/api/draft/parse", "POST"),
    ]:
        resp = client.request(method, path)
        assert resp.status_code == 404, f"{method} {path} 应 404, 实际 {resp.status_code}"
    print("[OK] Test 10: 旧 /api/drafts/* + /api/draft/parse 4 个 endpoint 全部 404 (v1 全删)")


if __name__ == "__main__":
    test_list_sessions_empty()
    test_list_sessions_returns_multiple_sorted_by_updated()
    test_get_session_existing_returns_messages()
    test_get_session_nonexistent_returns_404()
    test_delete_session_existing_removes_directory()
    test_delete_session_nonexistent_idempotent()
    test_upload_to_existing_session_writes_to_session_dir()
    test_upload_without_session_id_returns_422()
    test_upload_to_nonexistent_session_returns_404()
    test_legacy_drafts_api_endpoints_removed()
    print()
    print("=" * 50)
    print("✓ All 10 Step 3 tests passed")
    print("=" * 50)
