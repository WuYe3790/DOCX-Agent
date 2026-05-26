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

# Ensure src directory is in path for imports
sys.path.append(str(Path(__file__).parent))

# Import agent configurations and tools
from llm_adapter import LLMClientAdapter
from docx_tools import TOOLS_SCHEMA, call_tool, render_tools_prompt
from docx_tools.analyze_docx_style_samples import analyze_docx_style_samples
from md_tools.parse_markdown_draft import parse_markdown_draft
from md_tools.markdown_to_word import markdown_to_word
from docx_tools.diff_docx import diff_docx

# Constants from docx_agent_demo.py
STYLE_REVIEW = "style_review"
MD_DRAFT = "md_draft"
WORD_EDITING = "word_editing"

REVIEW_TOOL_NAMES = {"analyze_docx_style_samples", "read_docx_structure", "ls"}
MD_DRAFT_TOOL_NAMES = {
    "write_markdown_draft",
    "read_markdown_draft",
    "parse_markdown_draft",
    "ls",
    "read",
    "analyze_image_content",
}
WORD_EDITING_TOOL_NAMES = {
    "read_docx_structure",
    "write_markdown_draft",
    "read_markdown_draft",
    "parse_markdown_draft",
    "markdown_to_word",
    "diff_docx",
    "ls",
    "read",
    "analyze_image_content",
}

SYSTEM_PROMPT = """
你是一个精细 DOCX 编辑 agent。

目标：
1. 先读取文档结构或查找锚点，不要盲改。
2. 插入文字时优先保留原 run 格式。
3. 编辑后必须调用 diff_docx 验证变化。
4. 只解释和用户请求相关的变化，注意区分 word/document.xml 的业务变化和 Office 保存噪声。
5. 表格 action 的 table_index 按 //w:tbl 全文计数，嵌套表格也会计数；调用前必须用 read_docx_structure 返回的 depth、父表格坐标、direct_text 确认目标表格、行、列。普通正文 action 使用 write_markdown_to_paragraph（支持段落、标题、列表、图片、表格等所有元素在段落流中的动态编译与自动创建），必须同时传入 paragraph_index 和 anchor_text 定位，以防文本错位插入。
6. 工具由程序按当前状态动态提供。你只能调用当前可见工具，不要臆造不可见工具。
7. 当需要理解图表、截图、排版样式等图片视觉内容时，使用 analyze_image_content 进行多模态识图确认，不要凭文件名猜测图片内容。
8. 当需要查看外部代码、Markdown 文档或其他文本文件内容时，使用 read 工具。大文件用 offset/limit 分段读取，每次不超过 500 行以免上下文溢出。
""".strip()

def tool_schemas_for_state(state: str):
    if state == STYLE_REVIEW:
        allowed = REVIEW_TOOL_NAMES
    elif state == MD_DRAFT:
        allowed = MD_DRAFT_TOOL_NAMES
    else:
        allowed = WORD_EDITING_TOOL_NAMES
    return [schema for schema in TOOLS_SCHEMA if schema["function"]["name"] in allowed]

def state_prompt(state: str, available_tool_schemas) -> str:
    if state == STYLE_REVIEW:
        state_rule = """
当前状态：样式审核。
你的任务：仅对模板文档进行只读分析，提取格式特征与文档结构。
规则：
1. 你现在只能做样式和结构分析，不能编辑文档。
2. 请优先调用 analyze_docx_style_samples；若文档路径不明确，可用 ls 查看目录找到 docx 文件后调用 read_docx_structure。ls 仅用于定位文档路径，严禁浏览与文档无关的其他目录。
3. 此阶段唯一目标是提取 docx 自身的样式和结构信息。如果用户请求中提到了与 docx 不相关的其他文件或目录（如代码、截图、图片等），在本阶段完全忽略它们。你当前阶段的唯一有效输出是样式分析结果，其他意图均无法执行。
4. 拿到样式样本后，用简短中文列出你建议的正文、章节标题、表格字段名、表格填写值等 sample_id 与文档结构概述，并提示用户核对。
5. 列出样式建议和结构概述后，你必须立刻停止回答并等待用户确认！不要继续查看其他目录或文件，不要谈及草稿生成或下一阶段工作。
""".strip()
    elif state == MD_DRAFT:
        state_rule = """
当前状态：Markdown 草稿生成。
你的任务：根据第一阶段确定的样式特征与用户的需求内容，编写出用于填入 Word 的 Markdown 草稿文件。
规则：
1. 你现在只能生成、读取和解析 Markdown 草稿，不能编辑 docx。
2. 请用 write_markdown_draft 按文档区域生成 Markdown 片段，保存到 out/drafts；不要写成包含全流程说明的单个自由草稿。
3. 长正文块可以单独生成 Markdown 文件，例如 experiment_platform.md 等。
4. 每个片段只写最终要进入 Word 的内容，不要包含编辑计划。
5. 如果需要插入图片，草稿中应使用标准 Markdown 图片语法：![描述|对齐方式](图片路径)，对齐方式支持 left/center/right，默认 center。例如：![图表说明|center](out/media/image.png)。先用 analyze_image_content 理解图片内容再写描述，不要仅凭文件名猜测。
6. 如需参考外部代码、报告 md 文件或测试用例等内容作为草稿素材，使用 read 工具读取。
7. 写完后用 read_markdown_draft 或 parse_markdown_draft 展示草稿结构，方便用户确认。
8. 列出草稿结构后，你必须立刻停止回答，等待用户审核草稿。用户没有确认前，不要尝试写入 Word，也不要进入下一阶段。
""".strip()
    else:
        state_rule = """
当前状态：Word 写入与编译。
你的任务：将用户确认的 Markdown 草稿通过编译器写入并替换到 Word 模板对应的位置，最后进行比对验证。
规则：
1. 你现在只能读取 Word 结构、解析 Markdown 片段、调用 markdown_to_word 编译写入，并用 diff_docx 验证。
2. 写入前用 read_docx_structure 确认目标位置，用 parse_markdown_draft 确认 Markdown block_id/support/diagnostics。
3. 普通正文写入只用 write_markdown_to_paragraph（支持段落、标题、列表、图片、表格流式编译与自动生成）；表格单元格写入只用 write_markdown_to_table_cell。
4. 填充或替换占位段落时，用 write_markdown_to_paragraph 的 mode=replace；需要追加内容时使用 mode=after。
5. 一个 Markdown 文件有多个区域时，用 include_block_ids 或 line_start/line_end 选择局部块。
6. 不要引用 markdown_to_word 返回的 temporary_output_path；多步编辑应放在同一次 markdown_to_word.actions 中。
7. 如果 Markdown 片段不适合写入，可以用 write_markdown_draft 修订草稿，但不能绕过 markdown_to_word 直接编辑 docx。
8. 写入后必须调用 diff_docx 验证变化。
""".strip()

    return f"{state_rule}\n\n当前可用工具：\n{render_tools_prompt(available_tool_schemas)}"

def create_log_file() -> Path:
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"docx_agent_{timestamp}.log"

def append_log(log_path: Path, title: str, data=None) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 80}\n")
        f.write(f"{datetime.now().isoformat(timespec='seconds')} | {title}\n")
        f.write(f"{'=' * 80}\n")
        if data is None:
            return
        if isinstance(data, str):
            f.write(data)
        else:
            f.write(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        f.write("\n")

# Initialize FastAPI
app = FastAPI(title="DOCX-Agent Backend API", version="1.0.0")

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Output paths config
UPLOAD_DIR = Path("out/uploads")
DRAFT_DIR = Path("out/drafts")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DRAFT_DIR.mkdir(parents=True, exist_ok=True)

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
    """上传 DOCX 文件到临时工作区"""
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
    """运行模板样式特征分析"""
    try:
        if not Path(req.docx_path).exists():
            raise HTTPException(status_code=404, detail="指定路径的文档不存在")
        result_json = analyze_docx_style_samples(req.docx_path)
        return json.loads(result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/draft/parse")
async def parse_draft(req: ParseDraftRequest):
    """解析 Markdown 草稿，返回 AST Node 与诊断"""
    try:
        temp_draft_path = DRAFT_DIR / "temp_draft.md"
        temp_draft_path.write_text(req.markdown_content, encoding="utf-8")
        result_json = parse_markdown_draft(str(temp_draft_path))
        return json.loads(result_json)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/drafts/list")
async def list_drafts(since: Optional[float] = None):
    """获取 out/drafts 目录下的所有草稿文件列表"""
    try:
        files = []
        for file in DRAFT_DIR.glob("*.md"):
            # Exclude temp_draft.md to keep workspace clean
            if file.name != "temp_draft.md":
                if since is not None:
                    # Filter by modification time with a 5-second safety buffer
                    if file.stat().st_mtime < (since - 5.0):
                        continue
                files.append(file.name)
        return {"status": "ok", "files": sorted(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/drafts/read")
async def read_draft(filename: str):
    """读取指定草稿文件的内容"""
    try:
        # Prevent directory traversal attacks
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
    """保存用户编辑的草稿内容到文件"""
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
    """编译 Markdown 片段到 DOCX 模板"""
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
    """对比两份 DOCX 差异"""
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
    """下载生成的 Word 文件"""
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
    """Agent 状态机交互循环 WebSockets 接口"""
    await websocket.accept()
    adapter = LLMClientAdapter()
    model = adapter.get_model_name()
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    workflow_state = STYLE_REVIEW
    
    try:
        # Wait for the start trigger from frontend
        init_data = await websocket.receive_json()
        if init_data.get("type") != "start":
            await websocket.send_json({"type": "error", "message": "必须先发送 'start' 命令"})
            await websocket.close()
            return
            
        user_prompt = init_data.get("prompt")
        docx_path = init_data.get("docx_path")
        
        if not user_prompt or not docx_path:
            await websocket.send_json({"type": "error", "message": "参数 prompt 和 docx_path 不能为空"})
            await websocket.close()
            return
            
        # Initialize file logging
        log_path = create_log_file()
        provider = adapter.get_provider()
        start_config = {
            "provider": provider,
            "model": model,
            "tool_count": len(TOOLS_SCHEMA),
            "interface": "websocket_api",
            "docx_path": docx_path
        }
        if provider == "deepseek":
            start_config["thinking_type"] = adapter.get_thinking_type()
        elif provider == "sensenova":
            start_config["reasoning_effort"] = adapter.get_reasoning_effort()

        append_log(log_path, "启动配置 (Web 终端)", start_config)
        append_log(log_path, "用户输入", user_prompt)
        
        messages.append({"role": "user", "content": user_prompt})
        
        round_index = 0
        while True:
            round_index += 1
            current_tool_schemas = tool_schemas_for_state(workflow_state)
            current_tool_names = {schema["function"]["name"] for schema in current_tool_schemas}
            
            combined_system = f"{SYSTEM_PROMPT}\n\n{state_prompt(workflow_state, current_tool_schemas)}"
            request_messages = [{"role": "system", "content": combined_system}] + messages[1:]
            
            # Send current step meta back to frontend
            await websocket.send_json({
                "type": "round_start",
                "round": round_index,
                "workflow_state": workflow_state,
                "allowed_tools": list(current_tool_names)
            })
            
            # Log model request
            req_log = {
                "provider": adapter.get_provider(),
                "model": model,
                "workflow_state": workflow_state,
                "message_count": len(request_messages),
                "tool_names": sorted(list(current_tool_names)),
            }
            append_log(log_path, f"第 {round_index} 轮模型请求", req_log)
            
            # Call LLM client with streaming
            try:
                response_stream = adapter.create_chat_completion(
                    messages=request_messages,
                    tools=current_tool_schemas,
                    stream=True
                )
            except Exception as e:
                append_log(log_path, "模型调用失败", {"error": str(e)})
                await websocket.send_json({"type": "error", "message": f"调用大模型失败: {str(e)}"})
                break
                
            accumulated_reasoning = ""
            accumulated_content = ""
            tool_calls_map = {}
            
            # Read streaming response chunks
            for chunk in response_stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                # Check for DeepSeek-style reasoning thinking block
                reasoning_chunk = getattr(delta, "reasoning_content", None)
                if reasoning_chunk:
                    accumulated_reasoning += reasoning_chunk
                    await websocket.send_json({"type": "reasoning", "delta": reasoning_chunk})
                    
                # Content delta
                content_chunk = getattr(delta, "content", None)
                if content_chunk:
                    accumulated_content += content_chunk
                    await websocket.send_json({"type": "content", "delta": content_chunk})
                    
                # Tool calls delta
                tool_calls = getattr(delta, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_map[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_map[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_map[idx]["arguments"] += tc.function.arguments

            # Log model response
            log_msg = {"role": "assistant"}
            if tool_calls_map:
                log_msg["tool_calls"] = [
                    {
                        "id": v["id"],
                        "type": "function",
                        "function": {"name": v["name"], "arguments": v["arguments"]}
                    } for v in tool_calls_map.values()
                ]
            if accumulated_content:
                log_msg["content"] = accumulated_content
            if accumulated_reasoning:
                log_msg["reasoning_content"] = accumulated_reasoning
            append_log(log_path, f"第 {round_index} 轮模型响应", log_msg)

            # Process tool execution if requested
            if tool_calls_map:
                tool_calls_list = []
                for idx in sorted(tool_calls_map.keys()):
                    tc_val = tool_calls_map[idx]
                    tool_calls_list.append({
                        "id": tc_val["id"],
                        "type": "function",
                        "function": {
                            "name": tc_val["name"],
                            "arguments": tc_val["arguments"]
                        }
                    })
                
                # Add LLM choice to messages history
                assistant_msg = {"role": "assistant", "tool_calls": tool_calls_list}
                if accumulated_content:
                    assistant_msg["content"] = accumulated_content
                messages.append(assistant_msg)
                
                # Run each tool call and stream outputs back
                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    args = tc["function"]["arguments"]
                    
                    append_log(log_path, f"调用工具: {name}", {"tool": name, "arguments": args})
                    await websocket.send_json({
                        "type": "tool_start", 
                        "name": name, 
                        "arguments": args
                    })
                    
                    if name not in current_tool_names:
                        result = json.dumps({
                            "status": "error",
                            "tool": name,
                            "message": f"当前状态 ({workflow_state}) 不允许调用该工具"
                        }, ensure_ascii=False)
                    else:
                        try:
                            # Run tool execution
                            result = call_tool(name, args)
                        except Exception as e:
                            result = json.dumps({
                                "status": "error",
                                "tool": name,
                                "message": f"工具执行异常: {str(e)}"
                            }, ensure_ascii=False)
                            
                    append_log(log_path, f"工具结果: {name}", result)
                    await websocket.send_json({
                        "type": "tool_end",
                        "name": name,
                        "result": result
                    })
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result
                    })
                
                # Continue LLM completion loop with tool outputs
                continue
                
            # No tool calls: LLM finished responding in current round
            assistant_msg = {"role": "assistant", "content": accumulated_content}
            if accumulated_reasoning:
                assistant_msg["reasoning_content"] = accumulated_reasoning
            messages.append(assistant_msg)
            
            content_stripped = (accumulated_content or "").strip()
            if len(content_stripped) < 200:
                if workflow_state == STYLE_REVIEW:
                    guidance = "你当前处于样式审核阶段，请基于已读取的文档信息直接输出样式分析结果（列出 sample_id 与对应格式特征），不要尝试查看其他目录或文件。"
                elif workflow_state == MD_DRAFT:
                    guidance = "请直接输出 Markdown 草稿内容或给出下一步草稿计划。"
                else:
                    guidance = "请基于当前可用工具直接执行操作或给出分析结果。"
                
                append_log(log_path, "空响应自动引导", {"workflow_state": workflow_state, "content_length": len(content_stripped)})
                messages.append({"role": "user", "content": guidance})
                
                await websocket.send_json({
                    "type": "content",
                    "delta": f"\n\n*[系统引导] {guidance}*"
                })
                continue
            
            # State Machine Checkpoint Transitions
            if workflow_state == STYLE_REVIEW:
                append_log(log_path, "等待用户确认样式审核", {"state": workflow_state})
                # Tell client we are waiting for style approval
                await websocket.send_json({
                    "type": "wait_approval",
                    "phase": STYLE_REVIEW,
                    "content": accumulated_content
                })
                
                # Await client response
                client_res = await websocket.receive_json()
                if client_res.get("type") != "approve":
                    append_log(log_path, "非预期指令，关闭连接", client_res)
                    await websocket.send_json({"type": "error", "message": "指令类型应为 approve"})
                    break
                    
                approved = client_res.get("approved", False)
                feedback = client_res.get("feedback", "").strip()
                append_log(log_path, "用户样式审核确认", {"approved": approved, "feedback": feedback})
                
                if approved:
                    workflow_state = MD_DRAFT
                    append_log(log_path, "状态流转", {"from": STYLE_REVIEW, "to": MD_DRAFT})
                    continue_msg = "用户已确认样式审核结果。请基于最初任务和当前上下文，先生成 Markdown 草稿并保存到 out/drafts，然后读取或解析草稿供用户审核；不要编辑 docx。"
                    messages.append({"role": "user", "content": continue_msg})
                else:
                    messages.append({
                        "role": "user", 
                        "content": f"用户未确认样式审核结果，并给出反馈意见：{feedback}。请重新分析样式与结构。"
                    })
                    
            elif workflow_state == MD_DRAFT:
                append_log(log_path, "等待用户确认 Markdown 草稿", {"state": workflow_state})
                # Tell client we are waiting for draft approval
                await websocket.send_json({
                    "type": "wait_approval",
                    "phase": MD_DRAFT,
                    "content": accumulated_content
                })
                
                # Await client response
                client_res = await websocket.receive_json()
                if client_res.get("type") != "approve":
                    append_log(log_path, "非预期指令，关闭连接", client_res)
                    await websocket.send_json({"type": "error", "message": "指令类型应为 approve"})
                    break
                    
                approved = client_res.get("approved", False)
                feedback = client_res.get("feedback", "").strip()
                append_log(log_path, "用户草稿确认", {"approved": approved, "feedback": feedback})
                
                if approved:
                    workflow_state = WORD_EDITING
                    append_log(log_path, "状态流转", {"from": MD_DRAFT, "to": WORD_EDITING})
                    continue_msg = "用户已确认 Markdown 草稿。请读取 Word 结构并解析 Markdown IR，选择目标表格坐标和 style_mapping，用 markdown_to_word 的 actions 编译写入 Word，最后调用 diff_docx 验证。"
                    messages.append({"role": "user", "content": continue_msg})
                else:
                    messages.append({
                        "role": "user", 
                        "content": f"用户未通过 Markdown 草稿，修改建议：{feedback}。请利用 write_markdown_draft 修订草稿并展示给用户。"
                    })
                    
            else: # WORD_EDITING
                append_log(log_path, "写入与编译流完成", {"state": workflow_state})
                # Compilation completed, return completion status
                await websocket.send_json({
                    "type": "done",
                    "content": accumulated_content
                })
                
                # Wait for potential follow-up requirements
                client_res = await websocket.receive_json()
                if client_res.get("type") == "continue":
                    next_prompt = client_res.get("prompt", "")
                    append_log(log_path, "用户输入追加需求", next_prompt)
                    messages.append({"role": "user", "content": next_prompt})
                else:
                    append_log(log_path, "收到关闭/非继续指令，结束会话", client_res)
                    break
                    
    except WebSocketDisconnect:
        print("WebSocket 连接断开")
    except Exception as e:
        print(f"WebSocket 异常: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": f"系统内部异常: {str(e)}"})
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
