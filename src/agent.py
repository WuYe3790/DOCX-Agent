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
from typing import Optional

from llm_adapter import LLMClientAdapter
from docx_tools import TOOLS_SCHEMA, call_tool, render_tools_prompt
from context_manager import MessageManager


def create_log_file():
    from datetime import datetime
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"docx_agent_{timestamp}.log"


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
                 msg_mgr: MessageManager, docx_path: str = "", log_path: Optional[Path] = None):
        self.system_prompt = system_prompt
        self.msg_mgr = msg_mgr
        self.llm = llm_adapter
        self.docx_path = docx_path
        self.log_path = log_path
        self.workflow_state = STYLE_REVIEW
        self.stage_called_tools = {}  # {stage_name: set(tool_names)}
        self._pending_feedback = None
        self._round_index = 0

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

    def on_user_feedback(self, client_res: dict):
        """WS handler 在收到用户确认后调用，存入内部状态供生成器恢复时读取"""
        self._pending_feedback = client_res

    async def step(self):
        """
        异步生成器：每 yield 一个事件，WS 立即发给前端。
        遇到 wait_approval 时 yield 并暂停，等 WS handler 调用 on_user_feedback() 后恢复。
        """
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

            self._append_log(f"第 {self._round_index} 轮模型请求", {
                "workflow_state": self.workflow_state,
                "message_count": len(request_messages),
                "tool_names": sorted(list(current_tool_names)),
            })

            try:
                response = self.llm.create_chat_completion(
                    messages=request_messages,
                    tools=current_tool_schemas,
                    stream=False
                )
            except Exception as e:
                self._append_log("模型调用失败", {"error": str(e)})
                yield {"type": "error", "message": f"调用大模型失败: {str(e)}"}
                return

            tool_calls_map = {}
            accumulated_content = ""
            accumulated_reasoning = ""

            if response.choices:
                message = response.choices[0].message
                if message:
                    accumulated_reasoning = getattr(message, "reasoning_content", "") or ""
                    accumulated_content = getattr(message, "content", "") or ""
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls:
                        for tc in tool_calls:
                            idx = tc.index
                            tool_calls_map[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "arguments": tc.function.arguments if tc.function else ""
                            }

            log_msg = {"role": "assistant"}
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

            usage = getattr(response, "usage", None)
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
                        "id": tool_calls_map[idx]["id"],
                        "type": "function",
                        "function": {
                            "name": tool_calls_map[idx]["name"],
                            "arguments": tool_calls_map[idx]["arguments"]
                        }
                    }
                    for idx in sorted(tool_calls_map.keys())
                ]
                self.msg_mgr.append_assistant(tool_calls_list, accumulated_content)

                for tc in tool_calls_list:
                    name = tc["function"]["name"]
                    args = tc["function"]["arguments"]

                    self._append_log(f"调用工具: {name}", {"tool": name, "arguments": args})

                    yield {"type": "tool_start", "name": name, "arguments": args}

                    if name not in current_tool_names:
                        result = json.dumps({
                            "status": "error",
                            "tool": name,
                            "message": f"当前状态 ({self.workflow_state}) 不允许调用该工具"
                        }, ensure_ascii=False)
                    else:
                        try:
                            result = await asyncio.to_thread(call_tool, name, args)
                        except Exception as e:
                            result = json.dumps({
                                "status": "error",
                                "tool": name,
                                "message": f"工具执行异常: {str(e)}"
                            }, ensure_ascii=False)

                    self._append_log(f"工具结果: {name}", result)
                    yield {"type": "tool_end", "name": name, "result": result}
                    self.msg_mgr.append_tool_result(tc["id"], result)

                    if self.workflow_state not in self.stage_called_tools:
                        self.stage_called_tools[self.workflow_state] = set()
                    self.stage_called_tools[self.workflow_state].add(name)

                # 工具执行完后，继续循环，重新调 LLM
                continue

            # 无工具调用：处理 LLM 的文本响应
            self.msg_mgr.append_assistant([], accumulated_content)

            content_stripped = (accumulated_content or "").strip()
            if len(content_stripped) < 200:
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
                if "analyze_docx_style_samples" not in self.stage_called_tools.get(STYLE_REVIEW, set()):
                    correction_msg = "请先调用 analyze_docx_style_samples 分析文档样式，再进行其他操作。"
                    self.msg_mgr.append_user(correction_msg)
                    self._append_log("阶段校验失败", {"reason": "未调用样式分析工具", "correction": correction_msg})
                    yield {"type": "content", "delta": f"\n\n*[系统提示] {correction_msg}*"}
                    continue

                self._append_log("等待用户确认样式审核", {"state": self.workflow_state})
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
                    self._append_log("状态流转", {"from": STYLE_REVIEW, "to": MD_DRAFT})
                    continue_msg = "用户已确认样式审核结果。请基于最初任务和当前上下文，先生成 Markdown 草稿并保存到 out/drafts，然后读取或解析草稿供用户审核；不要编辑 docx。"
                    self.msg_mgr.append_user(continue_msg)
                else:
                    self.msg_mgr.append_user(f"用户未确认样式审核结果，并给出反馈意见：{fb_text}。请重新分析样式与结构。")
                continue

            if self.workflow_state == MD_DRAFT:
                self._append_log("等待用户确认 Markdown 草稿", {"state": self.workflow_state})
                yield {"type": "wait_approval", "phase": MD_DRAFT, "content": accumulated_content}

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
                    self.msg_mgr.append_user(f"用户未通过 Markdown 草稿，修改建议：{fb_text}。请利用 write_markdown_draft 修订草稿并展示给用户。")
                continue

            # WORD_EDITING 结束
            self._append_log("写入与编译流完成", {"state": self.workflow_state})
            yield {"type": "done", "content": accumulated_content}
            return