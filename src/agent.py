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
    # v2: basic_tools 沙箱化 (Phase 3a)
    "ls",
    "read",
    "analyze_image_content",
    # v2: docx_tools 读类沙箱化 (Phase 3c)
    "read_docx_structure",
    "find_text",
    "diff_docx",
    # v2: docx_tools 写入类沙箱化 (Phase 3d) — 19 个
    "insert_text_at",
    "insert_text_in_table_cell",
    "insert_table_row_after",
    "set_paragraph_indent",
    "insert_table_after_paragraph",
    "insert_table_in_cell",
    "insert_table_column_after",
    "merge_table_cells_horizontal",
    "clear_table_cell",
    "delete_table_row",
    "replace_table_cell_text",
    "replace_text",
    "delete_text",
    "insert_paragraph_after",
    "set_text_format",
    "replace_text_like_sample",
    "insert_paragraph_after_like_sample",
    "replace_table_cell_like_sample",
    "insert_image_after_paragraph",
}

from openai import APITimeoutError, APIConnectionError, BadRequestError

from llm_adapter import LLMClientAdapter
from llm_adapter.response_parser import extract_reasoning
from llm_adapter.quirks import apply_quirk, QuirkAction
from docx_tools import call_tool
from context_manager import MessageManager
from state_machine import WorkflowTransitions, TransitionDirective
from session_persistence import SessionPersistence


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

# === 提示词与状态名常量已迁移到 src/prompts.py (Step A 重构) ===
# 这里重导出以保持 `from agent import SYSTEM_PROMPT` 等旧 import 兼容
from prompts import (
    STYLE_REVIEW,
    MD_DRAFT,
    WORD_EDITING,
    REVIEW_TOOL_NAMES,
    MD_DRAFT_TOOL_NAMES,
    WORD_EDITING_TOOL_NAMES,
    SYSTEM_PROMPT,
    tool_schemas_for_state,
    state_prompt,
)


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
                 session_id: str = "", session_dir: Optional[Path] = None,
                 stream_mode: bool = True):
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
        # === B 方案: finish_reason=None 流不完整重试计数 ===
        # 商汤 SenseNova 偶发"流静默关闭"(OpenAI 协议异常): finish_reason 缺失, content/tool_calls 都空
        # 表现为 reasoning-only 死循环 (复现: session-20260609-205746 第 13/14 轮)
        # 策略: 检测到 finish_reason=None + 无 tool_calls → 不污染 conversation, 重发请求
        self._stream_incomplete_retries = 0
        # === 流式 / 非流式 开关 ===
        # 用途:商汤 SenseNova 等 SSE 协议层有 bug 的 provider 在流式 reasoning→content 切换时
        # 偶发流静默关闭(2026-06-10 session-20260610-100416 04 章节 stall),前端点 toggle
        # 切到非流式,下一轮 step() 走 create_chat_completion_blocking()。
        # 默认 True(流式)保持现有 live reasoning UX;切换在下一轮请求生效,不打断当前请求。
        # stream_mode 由 server.py 在构造 Agent 时传入(读自 WS start 帧) — 让用户能
        # 在新会话启动前先把 toggle 拨到非流式,新会话直接以非流式开始(避免触发 stall 后再切)。
        self._stream_mode: bool = stream_mode
        # === v2: 持久化相关 ===
        self.session_id = session_id
        self.session_dir = session_dir  # Path("out") / "sessions" / session_id
        # Step B: 持久化层已抽出到 src/session_persistence.py
        # 用 weakref 避免双向循环引用 (用户补丁 1), lock 移入 persistence 内部
        self._persistence = SessionPersistence(self)

    # ─── v2 持久化: 委托给 SessionPersistence ────

    def _checkpoint(self) -> None:
        """5 个 Checkpoint 触发点统一调用: 委托给 SessionPersistence"""
        self._persistence.checkpoint()

    def save_to_disk(self) -> None:
        """同步写盘 — 委托给 SessionPersistence (向后兼容, 测试 / 旧调用方用)"""
        self._persistence.save_sync()

    @classmethod
    def load_from_disk(
        cls, session_dir: Path, llm_adapter: LLMClientAdapter,
        system_prompt: str, docx_path: str = "", log_path: Optional[Path] = None
    ) -> "Agent":
        """从 session_dir 反序列化 Agent 状态 (Step 2 server.py resume 时调用)"""
        # Step B: 读 3 个 JSON 委托给 SessionPersistence
        metadata, messages_data, workflow = SessionPersistence.read_session_files(session_dir)

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

    def set_stream_mode(self, stream_mode: bool) -> None:
        """切换流式 / 非流式 — 前端 toggle 调用, 下一轮 step() 生效。

        行为:
        - stream_mode=True:  下一轮走 create_chat_completion(stream=True) — 默认
        - stream_mode=False: 下一轮走 create_chat_completion_blocking() — 用于 SenseNova
                              等 SSE 协议层有 bug 的 provider

        注意:
        - 切换不打断当前正在进行的请求, 下一轮请求才用新模式 (原话 "下一条消息开始用新模式")
        - 不持久化: 重启 / 刷新页面后回到默认 (按用户原话不落盘)
        - server.py 在收到 WS "set_stream_mode" 消息时调用本方法
        """
        self._stream_mode = bool(stream_mode)
        self._append_log("stream_mode_changed", {"stream_mode": self._stream_mode})

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

            # --- 0. Pre-stream retry wrapper (流式 / 非流式共用 retry 循环) ---
            # 商汤 SenseNova 等 provider 在流式 reasoning→content 切换时偶发流静默关闭,
            # 前端点 toggle 切到非流式后, 下一轮走 create_chat_completion_blocking() 走 JSON 路径绕过 SSE bug。
            response_or_stream = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    if self._stream_mode:
                        response_or_stream = self.llm.create_chat_completion(
                            messages=request_messages,
                            tools=current_tool_schemas,
                            stream=True,
                        )
                    else:
                        response_or_stream = self.llm.create_chat_completion_blocking(
                            messages=request_messages,
                            tools=current_tool_schemas,
                        )
                    break
                except _RETRYABLE_EXC as e:
                    if attempt < _MAX_RETRIES:
                        delay = _RETRY_DELAYS[attempt]
                        mode = "stream" if self._stream_mode else "blocking"
                        self._append_log("流式重试", {"attempt": attempt + 1, "error": str(e), "delay": delay, "mode": mode})
                        yield {"type": "retrying", "attempt": attempt + 1, "delay": delay, "error": str(e)}
                        await asyncio.sleep(delay)
                        continue
                    mode = "stream" if self._stream_mode else "blocking"
                    self._append_log("流式重试耗尽", {"error": str(e), "total_attempts": attempt + 1, "mode": mode})
                    yield {"type": "error", "message": f"调用大模型失败（重试 {attempt + 1} 次后）: {e}"}
                    return
                except Exception as e:
                    mode = "stream" if self._stream_mode else "blocking"
                    self._append_log("模型调用失败", {"error": str(e), "mode": mode})
                    yield {"type": "error", "message": f"调用大模型失败: {str(e)}"}
                    return

            # --- 1. 拆解响应 — 流式迭代 chunks, 非流式拆 ChatCompletion 对象 ---
            tool_calls_map: dict = {}
            accumulated_content = ""
            accumulated_reasoning = ""
            reasoning_yielded: bool = False
            finish_reason = None
            usage = None
            stream_error: Exception | None = None

            if self._stream_mode:
                # === 现有流式路径(逻辑与原版完全一致, 仅数据来源从 `stream` 改成 `response_or_stream`)===
                try:
                    for chunk in response_or_stream:
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

                        # Reasoning(provider 无关) — 字段路径由 self.llm.reasoning_field 决定:
                        # - DeepSeek/Agnes: delta.reasoning_content (OpenAI 标准字段)
                        # - SenseNova:     delta.model_extra.reasoning (商汤专有扩展)
                        # 路径来自 config 或 llm_adapter._DEFAULT_REASONING_FIELDS 默认表。
                        rc = extract_reasoning(delta, self.llm.reasoning_field)
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
            else:
                # === 非流式路径: 把 ChatCompletion 拆成与流式归一化的事件 ===
                # 设计目标: 下游(quirk 判断 / append_assistant / tool 执行)对模式无感
                # 数据全部填到同样的 accumulated_content / accumulated_reasoning / tool_calls_map / finish_reason
                try:
                    response = response_or_stream
                    usage = getattr(response, "usage", None)
                    if response.choices:
                        choice = response.choices[0]
                        fr = getattr(choice, "finish_reason", None)
                        if fr:
                            finish_reason = fr
                        msg = getattr(choice, "message", None)
                        if msg is not None:
                            # Reasoning — SenseNova 非流式路径: message.model_extra.reasoning
                            # (与流式 delta.model_extra.reasoning 字段路径同源, 只是挂在 message 上)
                            extra = getattr(msg, "model_extra", None)
                            if isinstance(extra, dict):
                                rc = extra.get("reasoning")
                                if rc:
                                    accumulated_reasoning += rc
                                    reasoning_yielded = True
                                    self._append_log("chunk_event", {"round": self._round_index, "type": "reasoning", "len": len(rc), "cum": len(accumulated_reasoning), "mode": "blocking"})
                                    yield {"type": "reasoning", "delta": rc}
                            # Content — OpenAI SDK 在非流式下返回完整字符串, 一次 yield
                            c = getattr(msg, "content", None)
                            if c:
                                accumulated_content += c
                                self._append_log("chunk_event", {"round": self._round_index, "type": "content", "len": len(c), "cum": len(accumulated_content), "mode": "blocking"})
                                yield {"type": "content", "delta": c}
                            # Tool calls — 非流式下一次性填入, 不需要跨对象累积 arguments
                            tcs = getattr(msg, "tool_calls", None)
                            if tcs:
                                for tc in tcs:
                                    idx = getattr(tc, "index", 0) or 0
                                    if idx not in tool_calls_map:
                                        tool_calls_map[idx] = {
                                            "id": tc.id or "",
                                            "name": (tc.function.name if tc.function else "") or "",
                                            "arguments": (tc.function.arguments if tc.function else "") or "",
                                        }
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

            # --- 4.5 Quirk 系统: 让 provider 声明的 quirks 决定本轮是否触发特殊处理 ---
            # 实现/启用边界:
            #   实现: src/llm_adapter/quirks.py 中 @register_quirk("...") 装饰的函数
            #   启用: self.llm.quirks tuple(来自 config.providers.<name>.quirks
            #         或 _DEFAULT_QUIRKS 默认表)
            # 当前唯一的 quirk: stream_empty_retry(替代旧 if-else, 行为完全一致)
            #   现象: stream_error=None + finish_reason=None + tool_calls 空 → server 静默关闭流
            #   复现: session-20260609-205746 R13/14
            # retry budget 仍归 agent 管 — quirk 只回答"这轮是否该 retry", 不管全局预算
            _MAX_INCOMPLETE_STREAM_RETRY = 2
            quirk_retry_triggered = False
            for quirk_name in self.llm.quirks:
                directive = apply_quirk(quirk_name, {
                    "finish_reason": finish_reason,
                    "tool_calls_map": tool_calls_map,
                    "accumulated_content": accumulated_content,
                    "accumulated_reasoning": accumulated_reasoning,
                })
                if directive.action == QuirkAction.RETRY_REQUEST:
                    if self._stream_incomplete_retries < _MAX_INCOMPLETE_STREAM_RETRY:
                        self._stream_incomplete_retries += 1
                        self._append_log("stream_incomplete_retry", {
                            "round": self._round_index,
                            "attempt": self._stream_incomplete_retries,
                            "trigger_quirk": quirk_name,
                            "reason": directive.reason,
                            "had_content": len(accumulated_content) > 0,
                            "had_reasoning": len(accumulated_reasoning) > 0,
                            "reasoning_len": len(accumulated_reasoning),
                        })
                        # 关键: 不 append_assistant, conversation 不动; 后面 continue 重发请求
                        quirk_retry_triggered = True
                        break    # 跳出 quirk 循环
                    # 重试耗尽: 重置计数, 落地到下面原有路径作为兜底
                    self._append_log("stream_incomplete_retry_exhausted", {
                        "round": self._round_index,
                        "max_retries": _MAX_INCOMPLETE_STREAM_RETRY,
                        "trigger_quirk": quirk_name,
                    })
                    self._stream_incomplete_retries = 0
                    break       # 跳出 quirk 循环, 走原路径(quirk_retry_triggered 仍 False)

            if quirk_retry_triggered:
                # (_round_index 会在下次 while 顶部自增, 重试占独立 round, 日志可追溯)
                continue
            # 没有 quirk 触发 retry → 清零计数, 避免跨轮累积
            self._stream_incomplete_retries = 0

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

            # 状态机转换检查 (Step C: 评估逻辑已迁到 state_machine.WorkflowTransitions)
            if self.workflow_state == STYLE_REVIEW:
                # 反复评估直到 directive 不是 yield_approval (即用户已审批 / 错误 / revise)
                while True:
                    directive = WorkflowTransitions.evaluate_style_review(
                        self.stage_called_tools, self._pending_feedback,
                    )
                    self._pending_feedback = None
                    if directive.action == "correct":
                        self._append_log("阶段校验失败", {"reason": "未完成样式分析与角色绑定", "correction": directive.user_message})
                        self.msg_mgr.append_user(directive.user_message)
                        yield directive.extra_event
                        break  # 退出 inner while, 回到 step 主 while 跑 LLM
                    if directive.action == "yield_approval":
                        self._append_log("等待用户确认样式审核", {"state": self.workflow_state})
                        self._pending_approval = True  # v2: 标记"等待审批", 供 server.py 在 history 响应里推 isWaitingApproval
                        self._checkpoint()  # Checkpoint 4: STYLE_REVIEW 审批挂起前落盘
                        yield {"type": "wait_approval", "phase": directive.phase, "content": accumulated_content}
                        # ⬆️ 生成器在这里暂停，等 ws_agent 调用 on_user_feedback() 后恢复
                        # 继续 inner while, 此时 _pending_feedback 已被设置, 下一轮 evaluate 走 advance/revise
                        continue
                    if directive.action == "advance":
                        self._append_log("用户样式审核确认", {"approved": True, "feedback": ""})
                        self.stage_called_tools.pop(STYLE_REVIEW, None)
                        self.workflow_state = directive.to_state
                        if directive.should_clear_drafts:
                            self.draft_files_written = []   # 新一轮草稿周期, 清空旧路径
                        self._append_log("状态流转", {"from": STYLE_REVIEW, "to": MD_DRAFT})
                        self.msg_mgr.append_user(directive.user_message)
                        break  # 退出 inner while, 回到 step 主 while 跑 LLM
                    if directive.action == "revise":
                        if directive.extra_event and directive.extra_event.get("type") == "error":
                            self._append_log("非预期指令，关闭连接", {"feedback": directive.user_message})
                            yield directive.extra_event
                            return
                        self._append_log("用户样式审核确认", {"approved": False, "feedback": directive.user_message})
                        self.msg_mgr.append_user(directive.user_message)
                        break  # 退出 inner while, 回到 step 主 while 跑 LLM
                continue  # 退出本块, 回到 step 主 while 顶部

            if self.workflow_state == MD_DRAFT:
                # 读取本轮所有写过的草稿文件, 用 === filename === 分隔
                draft_parts: list[str] = []
                for path_str in self.draft_files_written:
                    p = Path(path_str)
                    if p.exists():
                        draft_parts.append(f"=== {p.name} ===\n{p.read_text(encoding='utf-8')}")
                draft_content = "\n\n".join(draft_parts) if draft_parts else ""

                # 反复评估直到 directive 不是 yield_approval
                while True:
                    directive = WorkflowTransitions.evaluate_md_draft(
                        self.stage_called_tools, self.draft_files_written, draft_content, self._pending_feedback,
                    )
                    self._pending_feedback = None
                    if directive.action == "yield_approval":
                        self._append_log("等待用户确认 Markdown 草稿", {"state": self.workflow_state})
                        self._pending_approval = True  # v2: 标记"等待审批", 供 server.py 在 history 响应里推 isWaitingApproval
                        self._checkpoint()  # Checkpoint 5: MD_DRAFT 审批挂起前落盘
                        yield {"type": "wait_approval", "phase": directive.phase, "content": accumulated_content, "draft_content": draft_content}
                        # ⬆️ 生成器在这里暂停，等 ws_agent 调用 on_user_feedback() 后恢复
                        # 继续 inner while, 此时 _pending_feedback 已被设置, 下一轮 evaluate 走 advance/revise
                        continue
                    if directive.action == "advance":
                        self._append_log("用户草稿确认", {"approved": True, "feedback": ""})
                        self.workflow_state = directive.to_state
                        self._append_log("状态流转", {"from": MD_DRAFT, "to": WORD_EDITING})
                        self.msg_mgr.append_user(directive.user_message)
                        break  # 退出 inner while, 回到 step 主 while 跑 LLM
                    if directive.action == "revise":
                        if directive.extra_event and directive.extra_event.get("type") == "error":
                            self._append_log("非预期指令，关闭连接", {"feedback": directive.user_message})
                            yield directive.extra_event
                            return
                        self._append_log("用户草稿确认", {"approved": False, "feedback": directive.user_message})
                        if directive.should_clear_drafts:
                            self.draft_files_written = []   # 修订循环, 清空旧草稿路径
                        self.msg_mgr.append_user(directive.user_message)
                        break  # 退出 inner while, 回到 step 主 while 跑 LLM
                continue  # 退出本块, 回到 step 主 while 顶部

            # WORD_EDITING 结束
            self._append_log("写入与编译流完成", {"state": self.workflow_state})
            self._checkpoint()  # Checkpoint 6: 完结前落盘
            yield {"type": "done", "content": accumulated_content}
            return