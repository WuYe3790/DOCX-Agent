import os
import sys
import json
import uuid
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

sys.path.append(str(Path(__file__).parent))

from llm_adapter import LLMClientAdapter
from docx_tools import TOOLS_SCHEMA, call_tool, render_tools_prompt
from context_manager import MessageManager
from docx_tools.analyze_docx_style_samples import analyze_docx_style_samples
from md_tools.parse_markdown_draft import parse_markdown_draft
from md_tools.markdown_to_word import markdown_to_word
from docx_tools.diff_docx import diff_docx
from agent import Agent, SYSTEM_PROMPT, create_log_file, append_log

app = FastAPI(title="DOCX-Agent Backend API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("out/uploads")
DRAFT_DIR = Path("out/drafts")
SESSIONS_ROOT = Path("out/sessions")  # v2: 每个 session 一个目录
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DRAFT_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_ROOT.mkdir(parents=True, exist_ok=True)


class StyleAnalyzeRequest(BaseModel):
    docx_path: str


class ParseDraftRequest(BaseModel):
    markdown_content: str


class SaveDraftRequest(BaseModel):
    filename: str
    content: str


class CompileRequest(BaseModel):
    docx_path: str
    output_path: str
    actions: List[Dict[str, Any]]
    markdown_path: Optional[str] = None
    style_profile_path: Optional[str] = None
    style_mapping: Optional[Dict[str, str]] = None


class DiffRequest(BaseModel):
    before_docx: str
    after_docx: str
    marker_prefix: Optional[str] = ""


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        suffix = Path(file.filename).suffix
        if suffix.lower() not in [".docx", ".docm"]:
            raise HTTPException(status_code=400, detail="只支持上传 .docx / .docm 格式文件")

        file_id = str(uuid.uuid4())[:8]
        filename = f"{Path(file.filename).stem}_{file_id}{suffix}"
        dest_path = UPLOAD_DIR / filename

        with dest_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "status": "ok",
            "filename": file.filename,
            "saved_name": filename,
            "absolute_path": str(dest_path.resolve()),
            "relative_path": f"out/uploads/{filename}",
            "timestamp": datetime.now().timestamp()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")


@app.post("/api/style/analyze")
async def analyze_style(req: StyleAnalyzeRequest):
    try:
        if not Path(req.docx_path).exists():
            raise HTTPException(status_code=404, detail="指定路径的文档不存在")
        result_json = analyze_docx_style_samples(req.docx_path)
        return json.loads(result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/draft/parse")
async def parse_draft(req: ParseDraftRequest):
    try:
        temp_draft_path = DRAFT_DIR / "temp_draft.md"
        temp_draft_path.write_text(req.markdown_content, encoding="utf-8")
        result_json = parse_markdown_draft(str(temp_draft_path))
        return json.loads(result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/drafts/list")
async def list_drafts(since: Optional[float] = None):
    try:
        files = []
        for file in DRAFT_DIR.glob("*.md"):
            if file.name != "temp_draft.md":
                if since is not None:
                    if file.stat().st_mtime < (since - 5.0):
                        continue
                files.append(file.name)
        return {"status": "ok", "files": sorted(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/drafts/read")
async def read_draft(filename: str):
    try:
        safe_path = (DRAFT_DIR / filename).resolve()
        if not safe_path.is_relative_to(DRAFT_DIR.resolve()):
            raise HTTPException(status_code=400, detail="非法路径访问")
        if not safe_path.exists():
            raise HTTPException(status_code=404, detail="草稿文件不存在")
        content = safe_path.read_text(encoding="utf-8")
        return {"status": "ok", "filename": filename, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/drafts/save")
async def save_draft(req: SaveDraftRequest):
    try:
        safe_path = (DRAFT_DIR / req.filename).resolve()
        if not safe_path.is_relative_to(DRAFT_DIR.resolve()):
            raise HTTPException(status_code=400, detail="非法路径访问")
        safe_path.write_text(req.content, encoding="utf-8")
        return {"status": "ok", "message": "保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/word/compile")
async def compile_word(req: CompileRequest):
    try:
        result_json = markdown_to_word(
            docx_path=req.docx_path,
            output_path=req.output_path,
            actions=req.actions,
            markdown_path=req.markdown_path,
            style_profile_path=req.style_profile_path,
            style_mapping=req.style_mapping
        )
        return json.loads(result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/word/diff")
async def word_diff(req: DiffRequest):
    try:
        result_json = diff_docx(
            before_docx=req.before_docx,
            after_docx=req.after_docx,
            marker_prefix=req.marker_prefix
        )
        return json.loads(result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/download")
async def download_file(path: str):
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.websocket("/api/ws/agent")
async def ws_agent(websocket: WebSocket):
    """WebSocket 接入层：转发事件给 Agent，接收用户反馈

    v2 startup 协议 (避坑 3: HTTP/WS 分离):
      - 前→后:  {type: "start", prompt, docx_path}        新建会话
      - 前→后:  {type: "resume", session_id}             恢复会话
      - 后→前:  {type: "session_created", ...}           start 成功
      - 后→前:  {type: "history", messages, ...}         resume 成功
      - 后→前:  {type: "error", message}                 失败
    现有对话事件流 (round_start/reasoning/content/tool_start/tool_end/wait_approval/done) 0 改动.
    """
    await websocket.accept()
    adapter = LLMClientAdapter()
    model = adapter.get_model_name()

    msg_mgr = MessageManager(SYSTEM_PROMPT, token_threshold=150_000)
    msg_mgr.reset()

    # v2: 抽出 startup 解析 + Agent 创建, 让主循环只管"已经有一个 agent, 跑 step()"
    try:
        init_data = await websocket.receive_json()
        init_type = init_data.get("type")

        # === startup 命令分发 (3 种) ===
        if init_type == "start":
            agent, error_msg = await _start_new_session(init_data, adapter, model, msg_mgr)
            if error_msg:
                await websocket.send_json({"type": "error", "message": error_msg})
                await websocket.close()
                return

            # 第一个 frame: session_created
            await websocket.send_json({
                "type": "session_created",
                "session_id": agent.session_id,
                "docx_path": agent.docx_path,
                "approvalPhase": None,
                "isWaitingApproval": False,
            })

        elif init_type == "resume":
            agent, error_msg = await _resume_existing_session(init_data, adapter)
            if error_msg:
                await websocket.send_json({"type": "error", "message": error_msg})
                await websocket.close()
                return

            # 第一个 frame: history (前端用 messages 恢复, 用 approvalPhase/isWaitingApproval 还原按钮)
            await websocket.send_json({
                "type": "history",
                "session_id": agent.session_id,
                "docxPath": agent.docx_path,
                "messages": list(agent.msg_mgr._entries),
                "approvalPhase": agent.workflow_state if agent.workflow_state in ("style_review", "md_draft", "word_editing") else None,
                "isWaitingApproval": agent._pending_approval,
            })

        else:
            await websocket.send_json({"type": "error", "message": "必须先发送 'start' 或 'resume' 命令"})
            await websocket.close()
            return

        # === heartbeat (startup 成功后启动) ===
        async def send_heartbeat():
            while True:
                await asyncio.sleep(15)
                try:
                    await websocket.send_json({"type": "heartbeat"})
                    await asyncio.sleep(0)
                except:
                    break

        heartbeat_task = asyncio.create_task(send_heartbeat())

        # === 主事件循环 (现有逻辑, 0 改动) ===
        try:
            async for event in agent.step():
                await websocket.send_json(event)
                if event["type"] == "wait_approval":
                    client_res = await websocket.receive_json()
                    agent.on_user_feedback(client_res)
        except WebSocketDisconnect:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            print("WebSocket 连接断开")

    except WebSocketDisconnect:
        print("WebSocket 连接断开 (startup 阶段)")
    except Exception as e:
        print(f"WebSocket 异常: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": f"系统内部异常: {str(e)}"})
        except:
            pass


async def _start_new_session(init_data: dict, adapter: LLMClientAdapter, model: str, msg_mgr: MessageManager):
    """v2: 处理 {type: "start", prompt, docx_path}.

    Returns: (agent, error_msg)
      - 成功: (Agent, None)
      - 失败: (None, "错误消息")
    """
    user_prompt = (init_data.get("prompt") or "").strip()
    docx_path = init_data.get("docx_path") or ""

    if not user_prompt:
        return None, "参数 prompt 不能为空"

    # v2: 生成 session_id + session_dir
    session_id = f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    session_dir = SESSIONS_ROOT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    log_path = create_log_file(session_dir)
    provider = adapter.get_provider()
    start_config = {
        "session_id": session_id,  # v2: 启动配置里加 session_id, 方便日志关联
        "provider": provider,
        "model": model,
        "tool_count": len(TOOLS_SCHEMA),
        "interface": "websocket_api",
        "docx_path": docx_path,
    }
    if provider == "deepseek":
        start_config["thinking_type"] = adapter.get_thinking_type()
    elif provider == "sensenova":
        start_config["reasoning_effort"] = adapter.get_reasoning_effort()

    append_log(log_path, "启动配置 (Web 终端)", start_config)
    append_log(log_path, "用户输入", user_prompt)

    msg_mgr.append_user(user_prompt)

    agent = Agent(
        system_prompt=SYSTEM_PROMPT,
        llm_adapter=adapter,
        msg_mgr=msg_mgr,
        docx_path=docx_path,
        log_path=log_path,
        session_id=session_id,  # v2
        session_dir=session_dir,  # v2
    )

    return agent, None


async def _resume_existing_session(init_data: dict, adapter: LLMClientAdapter):
    """v2: 处理 {type: "resume", session_id}.

    Returns: (agent, error_msg)
      - 成功: (Agent, None) - 从 out/sessions/<id>/ 反序列化
      - 失败: (None, "错误消息")
    """
    session_id = (init_data.get("session_id") or "").strip()
    if not session_id:
        return None, "resume 必须传 session_id"

    session_dir = SESSIONS_ROOT / session_id
    metadata_path = session_dir / "metadata.json"
    if not session_dir.exists() or not metadata_path.exists():
        return None, f"session {session_id} not found"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    log_path = create_log_file(session_dir)  # 续写同一个 session 的 logs/
    append_log(log_path, "恢复会话 (Web 终端)", {
        "session_id": session_id,
        "workflow_state": metadata.get("workflow_state"),
    })

    agent = Agent.load_from_disk(
        session_dir=session_dir,
        llm_adapter=adapter,
        system_prompt=SYSTEM_PROMPT,
        docx_path=metadata.get("docx_path", ""),
        log_path=log_path,
    )
    return agent, None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)