"""Step 5 静态契约验证: 前端 v2 架构 (HTTP fetch + WS resume, 删 IndexedDB)

为什么用静态扫描而不是 UI e2e 测:
- 前端是 UI 代码 (1118 行 page.tsx), 端到端测需要 browser (Playwright)
- v2 架构的核心契约是 "源码形状": 删了哪些 import, 加了哪些 fetch, 哪些 WS case
- 静态扫描能在 1 秒内验证, 比启动 dev server + Playwright 跑 5 分钟更可重复

测什么:
- frontend/lib/sessions.ts 已删 (IndexedDB 持久化层)
- frontend/lib/session-types.ts 新建 (纯 type, 共享给 page.tsx + session-sidebar.tsx)
- page.tsx 删了 lib/sessions import
- page.tsx 删了 persistCurrentSession / createSession / updateSession / deleteSession / getSession 调用
- page.tsx 加了 fetch("/api/sessions") + fetch(...DELETE) 调用
- page.tsx 加了 session_created / history WS case 处理
- page.tsx startAgentSession 接受 resumeSessionId 第三参数
- 整个 frontend/ 无 indexedDB 引用 (除 .next cache)
"""
import sys
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent  # 仓库根
FRONTEND = REPO_ROOT / "frontend"
APP_PAGE = FRONTEND / "app" / "page.tsx"
SESSION_SIDEBAR = FRONTEND / "components" / "session-sidebar.tsx"
OLD_SESSIONS_LIB = FRONTEND / "lib" / "sessions.ts"
NEW_SESSIONS_TYPES = FRONTEND / "lib" / "session-types.ts"


def read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_old_sessions_lib_deleted():
    """Test 1: frontend/lib/sessions.ts (IndexedDB 持久化层) 已删"""
    assert not OLD_SESSIONS_LIB.exists(), (
        f"旧 lib/sessions.ts 应已删除, 但仍存在: {OLD_SESSIONS_LIB}. "
        f"v2 不再用 IndexedDB, 改用后端 HTTP + WS resume."
    )
    print("[OK] Test 1: frontend/lib/sessions.ts 已删除 (IndexedDB 持久化层移除)")


def test_new_session_types_lib_exists():
    """Test 2: frontend/lib/session-types.ts 新建, 含 SessionMeta export"""
    assert NEW_SESSIONS_TYPES.exists(), f"应新建 lib/session-types.ts, 但不存在: {NEW_SESSIONS_TYPES}"
    content = read(NEW_SESSIONS_TYPES)
    assert "export interface SessionMeta" in content, "session-types.ts 应 export interface SessionMeta"
    assert "id:" in content and "title:" in content and "messageCount:" in content, "SessionMeta 字段应齐全"
    print("[OK] Test 2: frontend/lib/session-types.ts 新建, 含 SessionMeta interface")


def test_page_tsx_no_sessions_lib_import():
    """Test 3: page.tsx 不再 import from '../lib/sessions'"""
    content = read(APP_PAGE)
    # 允许注释里提到 "lib/sessions" (历史记录), 但不能有 import 语句
    assert 'from "../lib/sessions"' not in content, "page.tsx 不应再 import '../lib/sessions' (v2 已删 IndexedDB)"
    # 验证改用 session-types
    assert 'from "../lib/session-types"' in content, "page.tsx 应 import SessionMeta from '../lib/session-types'"
    print("[OK] Test 3: page.tsx 删 import '../lib/sessions', 改用 '../lib/session-types'")


def test_page_tsx_no_indexeddb_crud_calls():
    """Test 4: page.tsx 不再调 createSession/updateSession/deleteSession/getSession/listSessions/persistCurrentSession"""
    content = read(APP_PAGE)
    # 这些是 lib/sessions.ts 导出的 IndexedDB 函数 — v2 不应再调
    for fn in ["createSession(", "updateSession(", "deleteSession(", "getSession(", "listSessions(", "persistCurrentSession"]:
        assert fn not in content, f"page.tsx 不应再调 {fn} (v2 改用后端 HTTP/WS)"
    print("[OK] Test 4: page.tsx 不再调 6 个 IndexedDB CRUD 函数 (v2 删 IndexedDB)")


def test_page_tsx_uses_http_sessions_api():
    """Test 5: page.tsx 调 fetch('/api/sessions') + DELETE 端点"""
    content = read(APP_PAGE)
    assert 'fetch("/api/sessions")' in content, "page.tsx 应调 fetch('/api/sessions') 拉列表"
    assert 'fetch(`/api/sessions/${id}`' in content and "method: \"DELETE\"" in content, (
        "page.tsx 应调 fetch('/api/sessions/${id}', { method: 'DELETE' }) 删 session"
    )
    print("[OK] Test 5: page.tsx 调 fetch /api/sessions (GET 列表 + DELETE 单个)")


def test_page_tsx_handles_session_created_and_history():
    """Test 6: page.tsx onmessage 处理 'session_created' 和 'history' (v2 WS 协议)"""
    content = read(APP_PAGE)
    assert 'case "session_created"' in content, "page.tsx 应处理 'session_created' WS 响应 (start 成功)"
    assert 'case "history"' in content, "page.tsx 应处理 'history' WS 响应 (resume 成功)"
    # session_created 应包含 setCurrentSessionId(data.session_id)
    # 用更简单的子串匹配, 避免 { } 嵌套
    assert "setCurrentSessionId(data.session_id)" in content, "page.tsx 应 setCurrentSessionId(data.session_id)"
    # history 应包含 setMessages(data.messages)
    assert "setMessages(data.messages || [])" in content or "setMessages(data.messages)" in content, (
        "page.tsx history case 应 setMessages(data.messages) 恢复消息历史"
    )
    # approvalPhase 恢复 (v2 history 响应推 approvalPhase)
    assert "setApprovalPhase(data.approvalPhase" in content, "page.tsx history case 应 setApprovalPhase(data.approvalPhase)"
    # isWaitingApproval 恢复
    assert "setIsWaitingApproval(data.isWaitingApproval" in content, "page.tsx history case 应 setIsWaitingApproval(data.isWaitingApproval)"
    print("[OK] Test 6: page.tsx onmessage 处理 'session_created' + 'history' (覆盖 messages/approvalPhase)")


def test_start_agent_session_accepts_resume_param():
    """Test 7: startAgentSession 接受 resumeSessionId 第三参数 (用于 resume)"""
    content = read(APP_PAGE)
    # 匹配: const startAgentSession = (initialPrompt: string, path: string, resumeSessionId?: string) => {
    m = re.search(
        r"startAgentSession\s*=\s*\(\s*initialPrompt:\s*string\s*,\s*path:\s*string\s*,\s*resumeSessionId\??:\s*string\s*\)",
        content,
    )
    assert m, "startAgentSession 签名应接受 resumeSessionId?: string 第三参数"
    # 验证 onopen 内根据 resumeSessionId 选 start vs resume
    onopen_block = re.search(
        r"socket\.onopen\s*=\s*\(\)\s*=>\s*\{[^}]*(?:resumeSessionId|type:\s*\"resume\"|type:\s*\"start\")",
        content,
    )
    assert onopen_block, "socket.onopen 内应根据 resumeSessionId 选 'start' 或 'resume' 消息"
    print("[OK] Test 7: startAgentSession 接受 resumeSessionId 第三参数 + onopen 分发 start/resume")


def test_session_sidebar_uses_shared_types():
    """Test 8: session-sidebar.tsx 引用共享 lib/session-types, 不引用 lib/sessions"""
    content = read(SESSION_SIDEBAR)
    assert "from \"../lib/session-types\"" in content, "session-sidebar.tsx 应 import SessionMeta from '../lib/session-types'"
    # 不应自己重新定义 SessionMeta interface (避免跟共享 type 不一致)
    assert "interface SessionMeta" not in content, "session-sidebar.tsx 不应自己重新定义 SessionMeta (避免 type 漂移)"
    print("[OK] Test 8: session-sidebar.tsx 用共享 session-types, 不重定义 SessionMeta")


def test_no_indexeddb_in_frontend_source():
    """Test 9: 整个 frontend/ 源码无 indexedDB 实际调用 (允许 .next cache / node_modules / 注释里"v2 已删 IndexedDB"说明)"""
    # 只扫 .ts / .tsx 文件, 且只检测**代码行** (忽略 // 注释)
    matches = []
    for ts_file in FRONTEND.rglob("*.ts*"):
        if ".next" in ts_file.parts or "node_modules" in ts_file.parts:
            continue
        if not ts_file.is_file():
            continue
        try:
            lines = ts_file.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line in lines:
            stripped = line.strip()
            # 跳过空行 + 注释行
            if not stripped or stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
                continue
            if "indexedDB" in line:  # 只检查大小写敏感, 因 IndexedDB 是 API 命名
                matches.append(f"{ts_file}: {line.strip()}")
    assert not matches, f"frontend 源码不应有 indexedDB 实际调用 (允许注释), 命中: {matches}"
    print("[OK] Test 9: 整个 frontend/ 源码无 indexedDB 实际调用 (.ts/.tsx 全扫描, 注释除外)")


def test_no_persist_current_session_in_session_sidebar():
    """Test 10: SessionSidebar 组件无 persistCurrentSession 调用 (那是 page.tsx 内部 helper)"""
    content = read(SESSION_SIDEBAR)
    assert "persistCurrentSession" not in content, "session-sidebar.tsx 不应调 persistCurrentSession (那是 page.tsx 内部 helper, v2 已删)"
    print("[OK] Test 10: session-sidebar.tsx 无 persistCurrentSession 引用")


# === Step 5 fixup: "用户发完消息不点 sidebar 也看不到" bug 修复 ===

def test_backend_start_saves_metadata_synchronously():
    """Test 11 (后端): WS start 后**立即** GET /api/sessions 能看到新 session (修 fixup 1)

    修复前: session_created 在 _start_new_session 末尾立即发, 但 metadata.json 要等
    _checkpoint() fire-and-forget 异步落盘 (round_start 时). LLM 慢的话几秒到十几秒延迟,
    此时 GET /api/sessions 拉不到这个 session.

    修复: _start_new_session 里 Agent 创建后立即 agent.save_to_disk() 同步写盘.
    """
    import time
    from fastapi.testclient import TestClient
    import sys as _sys
    _sys.path.insert(0, str(REPO_ROOT / "src"))
    from fastapi.testclient import TestClient as _TestClient
    import server as _server
    import shutil as _shutil
    import tempfile as _tempfile

    # 隔离: SESSIONS_ROOT 重定向到 tmpdir
    _tmp = Path(_tempfile.mkdtemp(prefix="step5_fixup_"))
    _server.SESSIONS_ROOT = _tmp
    _tmp.mkdir(parents=True, exist_ok=True)
    _client = _TestClient(_server.app)

    # 1. WS start 一个新 session
    with _client.websocket_connect("/api/ws/agent") as ws:
        ws.send_json({"type": "start", "prompt": "测试", "docx_path": ""})
        frame = ws.receive_json()
        assert frame["type"] == "session_created"
        new_session_id = frame["session_id"]

    # 2. **不 sleep**, 立即 GET /api/sessions — 应该立即看到新 session
    resp = _client.get("/api/sessions")
    assert resp.status_code == 200
    sessions = resp.json()
    session_ids = [s["id"] for s in sessions]
    assert new_session_id in session_ids, (
        f"start 后 GET /api/sessions 应立即看到 {new_session_id}, 实际: {session_ids}. "
        f"这说明 _start_new_session 没同步写盘, metadata.json 还没落."
    )
    _shutil.rmtree(_tmp)
    print("[OK] Test 11: WS start 后**立即** GET /api/sessions 能看到新 session (同步写盘验证)")


def test_frontend_sidebar_open_triggers_refresh_sessions():
    """Test 12 (前端): sidebar 打开按钮 onClick 调 refreshSessions (修 fixup 2)

    修复前: onClick={() => setSessionSidebarOpen(v => !v)} 只切 state, 不拉列表.
    用户在发完消息后**隔几秒**才开 sidebar, 中间后端落盘的 session 不会自动更新到 state.
    修复: onClick 内 nextOpen=true 时 void refreshSessions().
    """
    content = read(APP_PAGE)
    # 验证 onClick 内 nextOpen 判断 + refreshSessions 调用
    sidebar_open_block = re.search(
        r"onClick\s*=\s*\{\s*\(\)\s*=>\s*\{[^}]*setSessionSidebarOpen[^}]*nextOpen[^}]*refreshSessions",
        content,
    )
    assert sidebar_open_block, (
        "page.tsx sidebar 打开按钮 onClick 应在 nextOpen=true 时调 refreshSessions() (v2 fix)"
    )
    print("[OK] Test 12: page.tsx sidebar 打开按钮 onClick 触发 refreshSessions() (懒加载)")


def test_frontend_handle_create_session_triggers_refresh():
    """Test 13 (前端): handleCreateSession 末尾调 refreshSessions (修 fixup 3)

    修复前: 用户点 sidebar 的"新建对话"按钮后, 下次开 sidebar 才能看到新 session.
    修复: handleCreateSession 末尾 void refreshSessions().
    """
    content = read(APP_PAGE)
    # 找 handleCreateSession 函数体, 验证末尾有 refreshSessions
    handle_create_block = re.search(
        r"const handleCreateSession\s*=\s*[^=]*=>\s*\{(.*?)\n\s*\};",
        content,
        re.DOTALL,
    )
    assert handle_create_block, "page.tsx 应有 handleCreateSession 函数"
    body = handle_create_block.group(1)
    assert "refreshSessions" in body, (
        "handleCreateSession 末尾应调 refreshSessions() (v2 fix: 新建后 sidebar 立即可见)"
    )
    # 验证在函数末尾 (refreshSessions 在 setSessionSidebarOpen(false) 之后)
    assert body.rfind("refreshSessions") > body.rfind("setSessionSidebarOpen(false)"), (
        "refreshSessions 应在 handleCreateSession 末尾 (在 setSessionSidebarOpen 之后)"
    )
    print("[OK] Test 13: page.tsx handleCreateSession 末尾调 refreshSessions (新建后 sidebar 立即可见)")


if __name__ == "__main__":
    test_old_sessions_lib_deleted()
    test_new_session_types_lib_exists()
    test_page_tsx_no_sessions_lib_import()
    test_page_tsx_no_indexeddb_crud_calls()
    test_page_tsx_uses_http_sessions_api()
    test_page_tsx_handles_session_created_and_history()
    test_start_agent_session_accepts_resume_param()
    test_session_sidebar_uses_shared_types()
    test_no_indexeddb_in_frontend_source()
    test_no_persist_current_session_in_session_sidebar()
    # === Step 5 fixup: "用户发完消息不点 sidebar 也看不到" bug 修复 ===
    test_backend_start_saves_metadata_synchronously()
    test_frontend_sidebar_open_triggers_refresh_sessions()
    test_frontend_handle_create_session_triggers_refresh()
    print()
    print("=" * 50)
    print("✓ All 13 Step 5 tests passed (10 base + 3 fixup)")
    print("=" * 50)
