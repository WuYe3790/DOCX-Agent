"""
DOCX Agent 核心模块：异步生成器风格的 agent 循环。
server.py 通过 async for event in agent.step() 驱动，事件实时逐个发送。
"""

import sys
from pathlib import Path

# Ensure src directory is in path for imports
sys.path.append(str(Path(__file__).parent))

import asyncio
import json
import uuid
from typing import Optional


# === v2: 避坑 1 核心 — SESSION_TOOLS 集合 ===
# 这些工具的 Python 函数签名接受 session_id, 但 LLM 看到的 tools_schema **不**含 session_id
# agent.py tool dispatcher 反射调用前会**隐式注入** session_id (= self.session_id)
# LLM 传什么都无效, 即使 LLM 幻觉瞎传 session_id 也会被 self.session_id 覆盖
# 注意: 只列 LLM **可见**工具 (在 TOOLS_SCHEMA 里), 内部 helper (如 apply_markdown_ir_after_paragraph)
# 不在此集合 — 它们通过 markdown_to_word 间接传 session_id, 不走 dispatcher
SESSION_TOOLS = {
    "write_markdown_draft",
    "read_markdown_draft",
    "parse_markdown_draft",
    "apply_markdown_ir_to_table_cell",
    "markdown_to_word",
    "analyze_docx_style_samples",
}

from openai import APITimeoutError, APIConnectionError, BadRequestError

from llm_adapter import LLMClientAdapter
from docx_tools import TOOLS_SCHEMA, call_tool, render_tools_prompt
from context_manager import MessageManager


# 流式调用可重试的异常（pre-stream 阶段）
_RETRYABLE_EXC = (APITimeoutError, APIConnectionError)
_MAX_RETRIES = 2
_RETRY_DELAYS = [1.0, 2.0]  # 两次重试的退避秒数


def create_log_file(session_dir: Optional[Path] = None) -> Path:
    """会话专属日志: 写到 session_dir/logs/ (如果提供), 否则全局 logs/ (向后兼容)"""
    from datetime import datetime
    if session_dir:
        log_dir = session_dir / "logs"
    else:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"agent_{timestamp}.log"


def append_log(log_path, title, data=None):
    if log_path:
        from datetime import datetime
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

# 常量
STYLE_REVIEW = "style_review"
MD_DRAFT = "md_draft"
WORD_EDITING = "word_editing"

REVIEW_TOOL_NAMES = {"analyze_docx_style_samples", "bind_styles_to_roles", "read_docx_structure", "ls"}
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
5. 在用户确认样式之前，你必须调用 bind_styles_to_roles，**先读取 style_samples 数组**（每个 sample 的 format / paragraph_format / context 字段），根据字体/字号/颜色/上下文为 5 个标准角色（title / section_heading / body / table_cell / placeholder）**各显式选一个最匹配的 sample_id**，通过 bindings 参数传入。**不允许省略任何角色，也不允许凭印象分配**——找不到合适 sample 的角色也要选最接近的。
6. 列出样式建议和结构概述后，你必须立刻停止回答并等待用户确认！不要继续查看其他目录或文件，不要谈及草稿生成或下一阶段工作。
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


class Agent:
    """
    Agent 核心类：异步生成器风格的 agent 循环。

    使用方式：
        async for event in agent.step():
            await websocket.send_json(event)
            if event["type"] == "wait_approval":
                agent.on_user_feedback(await websocket.receive_json())

    step() 是 async generator，每次 yield 一个事件，协程自动暂停/恢复。
    """

    def __init__(self, system_prompt: str, llm_adapter: LLMClientAdapter,
                 msg_mgr: MessageManager, docx_path: str = "", log_path: Optional[Path] = None,
                 session_id: str = "", session_dir: Optional[Path] = None):
        self.system_prompt = system_prompt
        self.msg_mgr = msg_mgr
        self.llm = llm_adapter
        self.docx_path = docx_path
        self.log_path = log_path
        self.workflow_state = STYLE_REVIEW
        self.stage_called_tools = {}  # {stage_name: set(tool_names)}
        self._pending_feedback = None
        self._pending_approval = False  # v2: resume 时由 server 读出, 判断前端要不要展示"待审批"按钮
        self._round_index = 0
        self.draft_files_written: list[str] = []   # 追踪 MD_DRAFT 阶段写过的所有 .md 路径
        # === v2: 持久化相关 ===
        self.session_id = session_id
        self.session_dir = session_dir  # Path("out") / "sessions" / session_id
        self._save_lock = asyncio.Lock()  # 写盘异步锁 (避坑 2: tool_start/tool_end 间隔 < 几毫秒 时的文件写花)

    # ─── v2 持久化: save/load + 锁 + Checkpoint ────

    def _checkpoint(self) -> None:
        """5 个 Checkpoint 触发点统一调用: fire-and-forget 后台 save"""
        if self.session_dir:  # 无 session_dir 时 (测试场景) 跳过
            asyncio.create_task(self._background_save())

    async def _background_save(self) -> None:
        """异步串行化写盘: 同一 session 同一时刻只有一个写盘线程"""
        if not self.session_dir:
            return
        async with self._save_lock:  # 锁
            await asyncio.to_thread(self.save_to_disk)

    def save_to_disk(self) -> None:
        """同步写盘 (实际 I/O 在 thread) - 序列化 3 个 JSON 到 self.session_dir"""
        if not self.session_dir:
            return
        self.session_dir.mkdir(parents=True, exist_ok=True)
        (self.session_dir / "metadata.json").write_text(
            json.dumps(self._metadata_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        (self.session_dir / "messages.json").write_text(
            json.dumps(self._messages_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        (self.session_dir / "workflow.json").write_text(
            json.dumps(self._workflow_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        # 注意: 草稿文件 (.md) / style_profiles/ / uploads/ **不需要** "snapshot" 复制 —
        # 它们从诞生起就在 session_dir/drafts/ / style_profiles/ / uploads/ 下
        # (工具 dispatcher 隐式注入 session_id 派生 session_dir 写入, 避坑 1)

    def _metadata_dict(self) -> dict:
        from datetime import datetime
        return {
            "session_id": self.session_id,
            "title": (Path(self.docx_path).stem if self.docx_path else "新会话"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "docx_path": self.docx_path,
            "provider": self.llm.get_provider() if hasattr(self.llm, "get_provider") else "",
            "model": self.llm.get_model_name() if hasattr(self.llm, "get_model_name") else "",
            "workflow_state": self.workflow_state,
            "session_complete": False,
            "pending_approval": self._pending_approval,  # v2: resume 时供 server.py 推 isWaitingApproval
        }

    def _messages_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "system_prompt": self.msg_mgr._system_prompt,
            "entries": list(self.msg_mgr._entries),
            "total_input_tokens": self.msg_mgr._total_input_tokens,
            "last_prompt_tokens": self.msg_mgr._last_prompt_tokens,
        }

    def _workflow_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "workflow_state": self.workflow_state,
            "stage_called_tools": {k: sorted(v) for k, v in self.stage_called_tools.items()},
            "draft_files_written": list(self.draft_files_written),
            "round_index": self._round_index,
        }

    @classmethod
    def load_from_disk(
        cls, session_dir: Path, llm_adapter: LLMClientAdapter,
        system_prompt: str, docx_path: str = "", log_path: Optional[Path] = None
    ) -> "Agent":
        """从 session_dir 反序列化 Agent 状态 (Step 2 server.py resume 时调用)"""
        metadata = json.loads((session_dir / "metadata.json").read_text(encoding="utf-8"))
        messages_data = json.loads((session_dir / "messages.json").read_text(encoding="utf-8"))
        workflow = json.loads((session_dir / "workflow.json").read_text(encoding="utf-8"))

        msg_mgr = MessageManager(system_prompt)
        msg_mgr._entries = list(messages_data["entries"])
        # v3: 加载时清理旧数据 — 修复 DeepSeek 400 反复出现
        # 旧版本 (c2d4322 之前) 保存的 messages.json 含 {"role": "assistant", "tool_calls": []}
        # DeepSeek 严格校验会报 400 (Messages with role 'tool' must be a response to ...)
        msg_mgr._sanitize_entries()
        msg_mgr._total_input_tokens = messages_data["total_input_tokens"]
        msg_mgr._last_prompt_tokens = messages_data["last_prompt_tokens"]

        agent = cls(
            system_prompt=system_prompt, llm_adapter=llm_adapter,
            msg_mgr=msg_mgr, docx_path=docx_path, log_path=log_path,
            session_id=metadata["session_id"], session_dir=session_dir,
        )
        agent.workflow_state = workflow["workflow_state"]
        agent.stage_called_tools = {k: set(v) for k, v in workflow["stage_called_tools"].items()}
        agent.draft_files_written = list(workflow["draft_files_written"])
        agent._round_index = workflow["round_index"]
        agent._pending_approval = metadata.get("pending_approval", False)  # v2: 恢复"是否在等审批"标志
        return agent

    # ─── 日志 ────────────────────────────────────────────

    def _append_log(self, title: str, data=None):
        if self.log_path:
            from datetime import datetime
            with self.log_path.open("a", encoding="utf-8") as f:
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

    # ─── 核心驱动：异步生成器 ────────────────────────────

    def on_user_feedback(self, client_msg: dict):
        """WS handler 在收到用户操作后调用, v3 路由扩展.

        支持的 type:
          - "continue": 用户在 paused 状态 (如 word_editing 中断) 发了新消息
            → append_user 注入到 messages, 下次 step() 会带去 LLM
          - "approve": 用户在 wait_approval 状态点审批按钮
            → 存入 _pending_feedback, 走原 step() 内部 approved 逻辑
          - 其他 (兼容老版本): 透传到 _pending_feedback, 由 step() 内部判断
        """
        msg_type = client_msg.get("type")
        if msg_type == "continue":
            # 用户在 paused 状态发了新 prompt → 当作新一轮对话入口
            prompt = (client_msg.get("prompt") or "").strip()
            if prompt:
                self.msg_mgr.append_user(prompt)
            # 注意: 不设 _pending_feedback 也不改 _pending_approval
            # 下次 step() 会把这条 user 消息作为上下文带去 LLM
        elif msg_type == "approve":
            # 审批: 透传到 _pending_feedback, 走原 step() 内部判断
            self._pending_feedback = client_msg
            # v2: 不再是"等待审批"状态 (step() 恢复后会判断 approved 分支)
            self._pending_approval = False
        else:
            # 兜底: 其他潜在逻辑 (如单独的 "feedback" type) — 走原逻辑
            self._pending_feedback = client_msg
            self._pending_approval = False

    async def step(self):
        """
        异步生成器：每 yield 一个事件，WS 立即发给前端。
        遇到 wait_approval 时 yield 并暂停，等 WS handler 调用 on_user_feedback() 后恢复。

        v3: resume 时不立刻调 LLM
        ── 设计 ──
        resume 路径 (server.py 在 init_type=="resume" 时设 agent._is_resume=True):
        step() 第一次被调 → yield 一个 paused 事件, 立即 return
        退出生成器后, server.py 等用户消息, 收到后调 on_user_feedback
        然后再次调 step() (此时 _is_resume 已被 self._is_resume = False 清除)
        → 进入正常 while 循环, 调 LLM

        这样:
        - 切历史不会立即消耗 LLM 配额 (Bug C 修复)
        - 前端拿到 paused 事件后可以根据 is_waiting_approval 决定 UI
        - 用户主动发消息才会续跑
        """
        # === v3: resume 早期 return — yield paused 不调 LLM ===
        if getattr(self, "_is_resume", False):
            self._is_resume = False  # 一次性标记, 第二次进入 while 循环
            yield {
                "type": "paused",
                "phase": self.workflow_state,
                "is_waiting_approval": self._pending_approval,
                "reason": "resume_paused",
            }
            return  # 退出生成器, 等 server.py 收到用户消息后再次调用 step()

        # === v3: 已完成状态 — yield done 不调 LLM ===
        # 防止已经 done 的 session 被 resume 时又调 LLM 续跑
        if self.workflow_state == "done":
            yield {"type": "done", "content": ""}
            return

        while True:
            self._round_index += 1
            current_tool_schemas = tool_schemas_for_state(self.workflow_state)
            current_tool_names = {schema["function"]["name"] for schema in current_tool_schemas}

            state_prompt_text = state_prompt(self.workflow_state, current_tool_schemas)
            request_messages = self.msg_mgr.build_request_messages(state_prompt_text)

            yield {
                "type": "round_start",
                "round": self._round_index,
                "workflow_state": self.workflow_state,
                "allowed_tools": list(current_tool_names),
                "token_count": self.msg_mgr.last_prompt_tokens,
            }
            self._checkpoint()  # Checkpoint 1: round_start 消息已发, 落盘

            self._append_log(f"第 {self._round_index} 轮模型请求", {
                "workflow_state": self.workflow_state,
                "message_count": len(request_messages),
                "tool_names": sorted(list(current_tool_names)),
            })

            # --- 0. Pre-stream retry wrapper ---
            stream = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    stream = self.llm.create_chat_completion(
                        messages=request_messages,
                        tools=current_tool_schemas,
                        stream=True,
                    )
                    break
                except _RETRYABLE_EXC as e:
                    if attempt < _MAX_RETRIES:
                        delay = _RETRY_DELAYS[attempt]
                        self._append_log("流式重试", {"attempt": attempt + 1, "error": str(e), "delay": delay})
                        yield {"type": "retrying", "attempt": attempt + 1, "delay": delay, "error": str(e)}
                        await asyncio.sleep(delay)
                        continue
                    self._append_log("流式重试耗尽", {"error": str(e), "total_attempts": attempt + 1})
                    yield {"type": "error", "message": f"调用大模型失败（重试 {attempt + 1} 次后）: {e}"}
                    return
                except Exception as e:
                    self._append_log("模型调用失败", {"error": str(e)})
                    yield {"type": "error", "message": f"调用大模型失败: {str(e)}"}
                    return

            # --- 1. Iterate streaming chunks, accumulate + yield deltas ---
            tool_calls_map: dict = {}
            accumulated_content = ""
            accumulated_reasoning = ""
            reasoning_yielded: bool = False
            finish_reason = None
            usage = None
            stream_error: Exception | None = None

            try:
                for chunk in stream:
                    chunk_usage = getattr(chunk, "usage", None)
                    if chunk_usage:
                        usage = chunk_usage
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    fr = getattr(choice, "finish_reason", None)
                    if fr:
                        finish_reason = fr
                    delta = getattr(choice, "delta", None)
                    if delta is None:
                        continue

                    # Reasoning（多厂商兼容）：
                    # - DeepSeek: delta.reasoning_content（标准）
                    # - SenseNova: delta.model_extra['reasoning']（专有扩展）
                    rc = getattr(delta, "reasoning_content", None)
                    if not rc:
                        model_extra = getattr(delta, "model_extra", None) or {}
                        rc = model_extra.get("reasoning") if isinstance(model_extra, dict) else None
                    if rc:
                        accumulated_reasoning += rc
                        reasoning_yielded = True
                        self._append_log("chunk_event", {"round": self._round_index, "type": "reasoning", "len": len(rc), "cum": len(accumulated_reasoning)})
                        yield {"type": "reasoning", "delta": rc}

                    # Content
                    c = getattr(delta, "content", None)
                    if c:
                        accumulated_content += c
                        self._append_log("chunk_event", {"round": self._round_index, "type": "content", "len": len(c), "cum": len(accumulated_content)})
                        yield {"type": "content", "delta": c}

                    # Tool calls（跨 chunk 累积 arguments）
                    tcs = getattr(delta, "tool_calls", None)
                    if tcs:
                        for tc in tcs:
                            idx = tc.index
                            if idx not in tool_calls_map:
                                tool_calls_map[idx] = {
                                    "id": tc.id or "",
                                    "name": (tc.function.name if tc.function else "") or "",
                                    "arguments": (tc.function.arguments if tc.function else "") or "",
                                }
                            else:
                                if tc.function:
                                    if tc.function.name:
                                        tool_calls_map[idx]["name"] += tc.function.name
                                    if tc.function.arguments:
                                        tool_calls_map[idx]["arguments"] += tc.function.arguments
                                if tc.id:
                                    tool_calls_map[idx]["id"] = tc.id
            except Exception as e:
                stream_error = e

            # Reasoning 阶段结束 → 通知前端固化（消除思考-工具视觉脱节）
            if reasoning_yielded:
                yield {"type": "reasoning_end"}

            # --- 2. Mid-stream failure: discard partial, abort ---
            if stream_error is not None:
                self._append_log("模型流中断", {
                    "error": str(stream_error),
                    "partial_content_len": len(accumulated_content),
                    "partial_reasoning_len": len(accumulated_reasoning),
                })
                yield {"type": "error", "message": f"流式调用中断: {stream_error}"}
                return

            # --- 3. Log assembled response ---
            log_msg = {"role": "assistant", "finish_reason": finish_reason}
            if tool_calls_map:
                log_msg["tool_calls"] = [
                    {"id": v["id"], "type": "function", "function": {"name": v["name"], "arguments": v["arguments"]}}
                    for v in tool_calls_map.values()
                ]
            if accumulated_content:
                log_msg["content"] = accumulated_content
            if accumulated_reasoning:
                log_msg["reasoning_content"] = accumulated_reasoning
            self._append_log(f"第 {self._round_index} 轮模型响应", log_msg)

            # --- 4. Token tracking ---
            self.msg_mgr.update_token_count(usage)
            if usage:
                self._append_log(f"第 {self._round_index} 轮 token", {
                    "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                    "completion_tokens": getattr(usage, "completion_tokens", 0),
                })

            # 有工具调用时：逐个执行并 yield 事件
            if tool_calls_map:
                tool_calls_list = [
                    {
                        # v3: 流式空 id 兜底 — DeepSeek 严格校验拒绝空 id
                        # 极少见: LLM 服务端没返回 id, 或 chunk 累积时所有 tc.id 都为 None/空
                        # 生成 call_<idx>_<random> 兜底, 保证 tool_call_id 永远非空
                        "id": tool_calls_map[idx]["id"] or f"call_{idx}_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tool_calls_map[idx]["name"],
                            "arguments": tool_calls_map[idx]["arguments"]
                        }
                    }
                    for idx in sorted(tool_calls_map.keys())
                ]
                self.msg_mgr.append_assistant(tool_calls_list, accumulated_content, accumulated_reasoning)
                # v3: Bug A 防御 — 立即 checkpoint, 关闭"assistant 落盘后断网"窗口
                # 原 _checkpoint() 在 line 498 (tool_start 之后), 中间 ~30-50ms 断网
                # 会导致 assistant(tool_calls) 落盘但 tool result 没进, resume 时
                # OpenAI 校验 messages 序列不完整 → 400 invalid_request_error
                self._checkpoint()  # Checkpoint 1.5: assistant 消息已 append

                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    args = tc["function"]["arguments"]

                    self._append_log(f"调用工具: {name}", {"tool": name, "arguments": args})
                    self._append_log("chunk_event", {"round": self._round_index, "type": "tool_start", "name": name})

                    yield {"type": "tool_start", "name": name, "arguments": args}
                    self._checkpoint()  # Checkpoint 2: tool "running" 状态入库

                    if name not in current_tool_names:
                        result = json.dumps({
                            "status": "error",
                            "tool": name,
                            "message": f"当前状态 ({self.workflow_state}) 不允许调用该工具"
                        }, ensure_ascii=False)
                    else:
                        # v2: 避坑 1 — 反射调用前隐式注入 session_id
                        # 重要: 即便 LLM 在 args 里瞎传了 session_id, 我们也**覆盖**为 self.session_id (安全)
                        call_args_str = args
                        if name in SESSION_TOOLS:
                            try:
                                call_args_dict = json.loads(args) if isinstance(args, str) else dict(args)
                            except (json.JSONDecodeError, TypeError):
                                call_args_dict = {}
                            call_args_dict["session_id"] = self.session_id  # ← 关键: 用 Agent 自己的 session_id 覆盖
                            call_args_str = json.dumps(call_args_dict, ensure_ascii=False)
                        try:
                            result = await asyncio.to_thread(call_tool, name, call_args_str)
                        except Exception as e:
                            result = json.dumps({
                                "status": "error",
                                "tool": name,
                                "message": f"工具执行异常: {str(e)}"
                            }, ensure_ascii=False)

                    self._append_log(f"工具结果: {name}", result)
                    yield {"type": "tool_end", "name": name, "result": result}
                    self._checkpoint()  # Checkpoint 3: tool "success/error" 状态入库
                    self.msg_mgr.append_tool_result(tc["id"], result)

                    # 追踪 write_markdown_draft 写入的文件路径, 供 wait_approval 读取
                    if name == "write_markdown_draft":
                        try:
                            result_data = json.loads(result)
                            if result_data.get("status") == "ok" and result_data.get("markdown_path"):
                                self.draft_files_written.append(result_data["markdown_path"])
                        except Exception:
                            pass   # 非致命: 解析失败不影响主流程

                    if self.workflow_state not in self.stage_called_tools:
                        self.stage_called_tools[self.workflow_state] = set()
                    self.stage_called_tools[self.workflow_state].add(name)

                # 工具执行完后，继续循环，重新调 LLM
                continue

            # 无工具调用：处理 LLM 的文本响应
            self.msg_mgr.append_assistant([], accumulated_content, accumulated_reasoning)

            content_stripped = (accumulated_content or "").strip()
            if len(content_stripped) < 5:
                if self.workflow_state == STYLE_REVIEW:
                    guidance = "你当前处于样式审核阶段，请基于已读取的文档信息直接输出样式分析结果（列出 sample_id 与对应格式特征），不要尝试查看其他目录或文件。"
                elif self.workflow_state == MD_DRAFT:
                    guidance = "请直接输出 Markdown 草稿内容或给出下一步草稿计划。"
                else:
                    guidance = "请基于当前可用工具直接执行操作或给出分析结果。"

                self._append_log("空响应自动引导", {"workflow_state": self.workflow_state, "content_length": len(content_stripped)})
                self.msg_mgr.append_user(guidance)
                yield {"type": "content", "delta": f"\n\n*[系统引导] {guidance}*"}
                continue

            # 状态机转换检查
            if self.workflow_state == STYLE_REVIEW:
                called = self.stage_called_tools.get(STYLE_REVIEW, set())
                if "analyze_docx_style_samples" not in called or "bind_styles_to_roles" not in called:
                    correction_msg = (
                        "请先调用 analyze_docx_style_samples 分析样式，"
                        "再读取 style_samples 数组并显式调用 bind_styles_to_roles"
                        "（bindings 必须填 5 个标准角色的 sample_id），"
                        "最后再让用户审核。"
                    )
                    self.msg_mgr.append_user(correction_msg)
                    self._append_log("阶段校验失败", {"reason": "未完成样式分析与角色绑定", "correction": correction_msg})
                    yield {"type": "content", "delta": f"\n\n*[系统提示] {correction_msg}*"}
                    continue

                self._append_log("等待用户确认样式审核", {"state": self.workflow_state})
                self._pending_approval = True  # v2: 标记"等待审批", 供 server.py 在 history 响应里推 isWaitingApproval
                self._checkpoint()  # Checkpoint 4: STYLE_REVIEW 审批挂起前落盘
                yield {"type": "wait_approval", "phase": STYLE_REVIEW, "content": accumulated_content}
                # ⬆️ 生成器在这里暂停，等 ws_agent 调用 on_user_feedback() 后恢复

                # 恢复时读取用户反馈
                feedback = self._pending_feedback
                self._pending_feedback = None

                if feedback.get("type") != "approve":
                    self._append_log("非预期指令，关闭连接", feedback)
                    yield {"type": "error", "message": "指令类型应为 approve"}
                    return

                approved = feedback.get("approved", False)
                fb_text = feedback.get("feedback", "").strip()
                self._append_log("用户样式审核确认", {"approved": approved, "feedback": fb_text})

                if approved:
                    self.stage_called_tools.pop(STYLE_REVIEW, None)
                    self.workflow_state = MD_DRAFT
                    self.draft_files_written = []   # 新一轮草稿周期, 清空旧路径
                    self._append_log("状态流转", {"from": STYLE_REVIEW, "to": MD_DRAFT})
                    continue_msg = "用户已确认样式审核结果。请基于最初任务和当前上下文，先生成 Markdown 草稿并保存到 out/drafts，然后读取或解析草稿供用户审核；不要编辑 docx。"
                    self.msg_mgr.append_user(continue_msg)
                else:
                    self.msg_mgr.append_user(f"用户未确认样式审核结果，并给出反馈意见：{fb_text}。请重新分析样式与结构。")
                continue

            if self.workflow_state == MD_DRAFT:
                # 读取本轮所有写过的草稿文件, 用 === filename === 分隔
                draft_parts: list[str] = []
                for path_str in self.draft_files_written:
                    p = Path(path_str)
                    if p.exists():
                        draft_parts.append(f"=== {p.name} ===\n{p.read_text(encoding='utf-8')}")
                draft_content = "\n\n".join(draft_parts) if draft_parts else ""

                self._append_log("等待用户确认 Markdown 草稿", {"state": self.workflow_state})
                self._pending_approval = True  # v2: 标记"等待审批", 供 server.py 在 history 响应里推 isWaitingApproval
                self._checkpoint()  # Checkpoint 5: MD_DRAFT 审批挂起前落盘
                yield {"type": "wait_approval", "phase": MD_DRAFT, "content": accumulated_content, "draft_content": draft_content}

                feedback = self._pending_feedback
                self._pending_feedback = None

                if feedback.get("type") != "approve":
                    self._append_log("非预期指令，关闭连接", feedback)
                    yield {"type": "error", "message": "指令类型应为 approve"}
                    return

                approved = feedback.get("approved", False)
                fb_text = feedback.get("feedback", "").strip()
                self._append_log("用户草稿确认", {"approved": approved, "feedback": fb_text})

                if approved:
                    self.workflow_state = WORD_EDITING
                    self._append_log("状态流转", {"from": MD_DRAFT, "to": WORD_EDITING})
                    continue_msg = "用户已确认 Markdown 草稿。请读取 Word 结构并解析 Markdown IR，选择目标表格坐标和 style_mapping，用 markdown_to_word 的 actions 编译写入 Word，最后调用 diff_docx 验证。"
                    self.msg_mgr.append_user(continue_msg)
                else:
                    self.draft_files_written = []   # 修订循环, 清空旧草稿路径
                    self.msg_mgr.append_user(f"用户未通过 Markdown 草稿，修改建议：{fb_text}。请利用 write_markdown_draft 修订草稿并展示给用户。")
                continue

            # WORD_EDITING 结束
            self._append_log("写入与编译流完成", {"state": self.workflow_state})
            self._checkpoint()  # Checkpoint 6: 完结前落盘
            yield {"type": "done", "content": accumulated_content}
            return