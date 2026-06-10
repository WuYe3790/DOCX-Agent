"""Step 2 端到端测试: WS startup 协议 (start / resume) + session_created / history 响应

测什么:
- WS start 命令 → 第一个 frame 是 session_created
- start 后 out/sessions/<id>/ 含 3 JSON (fire-and-forget 后台写盘)
- WS resume 已有 session → 第一个 frame 是 history (含 messages)
- WS resume 不存在 → error frame
- 未知 startup 类型 → error frame
- start 但 prompt 空 → error frame

不测什么:
- agent.step() 后续事件流 (Step 1 已测过 save/load, 端到端由 LLM 行为决定)
- HTTP 控制面 (Step 3 范围)
"""
import sys
import json
import time
import shutil
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))  # tests/ 是子目录, src/ 在仓库根

from fastapi.testclient import TestClient
import server  # 触发 app 初始化 (含 SESSIONS_ROOT = Path("out") / "sessions")


# === 隔离: 把 SESSIONS_ROOT 重定向到 tmpdir, 避免污染真实 out/sessions ===
TMP_ROOT = Path(tempfile.mkdtemp(prefix="docx_agent_test_step2_"))
TMP_ROOT.mkdir(parents=True, exist_ok=True)
server.SESSIONS_ROOT = TMP_ROOT

client = TestClient(server.app)


# === Fixture: 隔离本 file 的 test 跑时改 SESSIONS_ROOT, 跑完恢复 saved ===
# 根因: server.SESSIONS_ROOT 是 module-level 全局, test_step3 / test_step5 等
# 也在 import 时改它。pytest import 顺序不保证, 跑在 test_step3 之后时
# SESSIONS_ROOT 已被它改成自己的 tmpdir — 但本 file test 2 用 TMP_ROOT
# 算路径找 session, 找不到就 fail。
# 修法: fixture 在 test 2 跑前临时设 SESSIONS_ROOT = TMP_ROOT, 跑完恢复
# saved。**不**用 autouse, 避免污染 test_step3 / test_step5。
@pytest.fixture
def isolate_sessions_root():
    saved = server.SESSIONS_ROOT
    server.SESSIONS_ROOT = TMP_ROOT
    yield
    server.SESSIONS_ROOT = saved


def test_start_sends_session_created():
    """Test 1: WS start 命令 → 第一个 frame 是 session_created (含 session_id)"""
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "start", "prompt": "你好, 请分析这个文档", "docx_path": ""})
        frame = ws.receive_json()
        assert frame["type"] == "session_created", f"expected session_created, got {frame}"
        assert frame["session_id"].startswith("session-"), f"session_id 应以 session- 开头: {frame['session_id']}"
        assert frame["docx_path"] == ""
        assert frame["approvalPhase"] is None
        assert frame["isWaitingApproval"] is False
    print("[OK] Test 1: start → session_created (含 session_id + docx_path)")


def test_start_creates_session_dir_with_3_json(isolate_sessions_root):
    """Test 2: start 后 out/sessions/<id>/ 应含 3 JSON (fire-and-forget Checkpoint 验证)

    注: server.SESSIONS_ROOT 是 module-level 全局, test_step3 / test_step5 等会改它.
    跑在它们之后时, server 写 session 到它们的 tmpdir, 本 test 用 TMP_ROOT 算路径
    会找不到. 修法: 用 isolate_sessions_root fixture 临时设回 TMP_ROOT, 跑完恢复.
    """
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "start", "prompt": "请分析", "docx_path": "/path/to/template.docx"})
        frame = ws.receive_json()
        session_id = frame["session_id"]

    # 后台 _background_save 异步跑, 等它完成
    time.sleep(0.8)

    session_dir = TMP_ROOT / session_id
    assert session_dir.exists(), f"session 目录未创建: {session_dir}"
    assert (session_dir / "metadata.json").exists(), "metadata.json 未落盘"
    assert (session_dir / "messages.json").exists(), "messages.json 未落盘"
    assert (session_dir / "workflow.json").exists(), "workflow.json 未落盘"

    # 验证 metadata 内容
    meta = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["session_id"] == session_id
    assert meta["docx_path"] == "/path/to/template.docx"
    assert meta["workflow_state"] == "style_review"  # Agent 初始状态

    # 验证 messages 含 user prompt
    msgs = json.loads((session_dir / "messages.json").read_text(encoding="utf-8"))
    assert any(m.get("role") == "user" and m.get("content") == "请分析" for m in msgs["entries"])

    # 验证 workflow
    wf = json.loads((session_dir / "workflow.json").read_text(encoding="utf-8"))
    assert wf["round_index"] >= 0  # round_start Checkpoint 触发后 ≥ 0
    print("[OK] Test 2: start 后 session_dir + 3 JSON 自动落盘 (Checkpoint 验证)")


def test_resume_existing_sends_history():
    """Test 3: WS resume 已有 session → 第一个 frame 是 history (含 messages + approvalPhase)"""
    # 先 start 创建 session
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "start", "prompt": "历史消息测试", "docx_path": "/t.docx"})
        start_frame = ws.receive_json()
        session_id = start_frame["session_id"]
    time.sleep(0.8)  # 等后台写盘

    # 再 resume
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "resume", "session_id": session_id})
        history_frame = ws.receive_json()
        assert history_frame["type"] == "history", f"expected history, got {history_frame}"
        assert history_frame["session_id"] == session_id
        assert history_frame["docxPath"] == "/t.docx"
        assert history_frame["approvalPhase"] == "style_review"
        assert history_frame["isWaitingApproval"] is False
        # messages 应含 user prompt (恢复后前端直接渲染)
        messages = history_frame["messages"]
        assert any(m.get("role") == "user" and m.get("content") == "历史消息测试" for m in messages)
    print("[OK] Test 3: resume 成功 → history frame (含 messages + approvalPhase + isWaitingApproval)")


def test_resume_nonexistent_sends_error():
    """Test 4: WS resume 不存在 session → error frame, 不创建任何 session 目录"""
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "resume", "session_id": "session-20260101-000000"})
        err_frame = ws.receive_json()
        assert err_frame["type"] == "error", f"expected error, got {err_frame}"
        assert "not found" in err_frame["message"], f"错误消息应含 'not found': {err_frame['message']}"
    # 验证: 没创建 session 目录
    assert not (TMP_ROOT / "session-20260101-000000").exists(), "失败的 resume 不应创建目录"
    print("[OK] Test 4: resume 不存在 → error frame, 无副作用")


def test_unknown_startup_type_sends_error():
    """Test 5: 未知 startup 类型 (e.g. list_sessions) → error frame (避坑 3 验证: list 应走 HTTP)"""
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "list_sessions"})  # v1 协议有, v2 应拒绝 (HTTP 才是)
        err_frame = ws.receive_json()
        assert err_frame["type"] == "error"
        assert "'start' 或 'resume'" in err_frame["message"]
    print("[OK] Test 5: 未知 startup 类型 → error frame (协议干净分离)")


def test_start_empty_prompt_sends_error():
    """Test 6: start 但 prompt 为空字符串 → error frame, 不创建 session 目录"""
    sessions_before = set(TMP_ROOT.iterdir()) if TMP_ROOT.exists() else set()
    with client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "start", "prompt": "", "docx_path": ""})
        err_frame = ws.receive_json()
        assert err_frame["type"] == "error"
        assert "prompt 不能为空" in err_frame["message"]
    sessions_after = set(TMP_ROOT.iterdir()) if TMP_ROOT.exists() else set()
    assert sessions_before == sessions_after, "空 prompt 不应创建 session 目录"
    print("[OK] Test 6: start 但 prompt 空 → error frame, 无副作用")


if __name__ == "__main__":
    test_start_sends_session_created()
    test_start_creates_session_dir_with_3_json()
    test_resume_existing_sends_history()
    test_resume_nonexistent_sends_error()
    test_unknown_startup_type_sends_error()
    test_start_empty_prompt_sends_error()
    print()
    print("=" * 50)
    print("✓ All 6 Step 2 tests passed")
    print("=" * 50)
