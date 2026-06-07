import json
from typing import Optional


class MessageManager:
    """
    消息管理模块：封装 messages 的累积、请求构建、token 追踪和去重。

    去重策略：
    - 内部使用 _entries 列表按时间顺序追加（append-only）
    - 重建请求时（build_request_messages）从后往前扫，对同一 target 的旧 tool call + tool result 配对删除
    - 去重范围：write_markdown_draft 和 read_markdown_draft
    - 配对删除原则：tool call 和其 tool result 必须一起删，否则 model 会困惑
    """

    def __init__(self, system_prompt: str, token_threshold: int = 150_000):
        self._system_prompt = system_prompt
        self._token_threshold = token_threshold
        self._entries: list[dict] = []          # 按时间顺序追加的消息片段
        self._total_input_tokens: int = 0
        self._last_prompt_tokens: int = 0       # 最近一次请求的 prompt token 数

    # ─── 消息操作 ────────────────────────────────────────

    def reset(self):
        """清空状态（新建会话时调用）"""
        self._entries = []
        self._total_input_tokens = 0

    def append_user(self, content: str):
        self._entries.append({"role": "user", "content": content})

    def append_assistant(self, tool_calls: list, content: str = ""):
        msg: dict = {"role": "assistant"}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if content:
            msg["content"] = content
        self._entries.append(msg)

    def append_tool_result(self, tool_call_id: str, content: str):
        self._entries.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        })

    def build_request_messages(self, state_prompt: str) -> list[dict]:
        """
        构建发给 LLM 的消息列表。

        v3 重写：两遍扫描 + assistant→tool 完整性校验。
        ── 第一遍（正向）：建立 tool_call_id → tool_result 映射 ──
        ── 第二遍（反向）：去重 + 完整性过滤 + content 兜底
        防御：
          1A-1: json.loads 防 JSONDecodeError (LLM 流式空串/截断)
          1A-2: 没有 tool result 跟进的 tool_call 被丢弃 (OpenAI 400 防御)
          兜底: kept_tc 空 + 有 content → 保留纯文本 assistant (不丢"我来做X"那种话)
        """
        # ── 第一遍（正向）：tool_call_id → tool_result 映射 ──
        #
        # 用于第二遍验证: assistant(tool_calls) 中的每条 tool_call 必须有对应
        # tool 消息, 否则会被丢弃 (避免 OpenAI 400 invalid_request_error)
        tool_results: dict = {}
        for entry in self._entries:
            if entry.get("role") == "tool":
                tc_id = entry.get("tool_call_id")
                if tc_id:
                    tool_results[tc_id] = entry  # 后写覆盖前写 (key 唯一)

        # ── 第二遍（反向）：去重 + 完整性过滤 + content 兜底 ──
        #
        # seen: {(tool_name, target): tool_call_id}
        #   从后往前扫, 记录每个 (tool_name, target) 最新的 tool_call_id
        #
        # skip_tc_ids: set[str]
        #   标记被去重掉 (被更新的同 target 覆盖) 的旧 tool_call_id
        #   它们对应的 tool result 也要被丢弃
        seen = {}
        skip_tc_ids = set()
        result_rev: list[dict] = []

        for entry in reversed(self._entries):
            role = entry.get("role")

            # ── 普通 user 消息：直接保留 ──
            if role == "user":
                result_rev.append(entry)
                continue

            # ── 无工具调用的 assistant 消息：直接保留 ──
            if role == "assistant" and not entry.get("tool_calls"):
                result_rev.append(entry)
                continue

            # ── 有工具调用的 assistant 消息：检查每个 tool_call ──
            if role == "assistant" and entry.get("tool_calls"):
                kept_tc = []

                for tc in entry["tool_calls"]:
                    tool_name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]

                    # 1A-1 修复: 防 JSONDecodeError
                    # LLM 流式输出可能产生损坏的 arguments (空串/截断)
                    # 降级为 {} 让 _dedup_key 返回 None → 当作非去重范围处理
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args) if raw_args else {}
                        except json.JSONDecodeError:
                            args = {}
                    else:
                        args = raw_args

                    key = self._dedup_key(tool_name, args)
                    tc_id = tc["id"]

                    # 1A-2 修复: 验证 tool_call 有对应 tool result
                    # 没有 tool result 跟进 → 丢弃这条 tool_call
                    # (场景: 断网导致 assistant 落盘但 tool result 没进, 或
                    #  旧版本残缺 messages.json 被加载)
                    if tc_id not in tool_results:
                        continue

                    if key is None:
                        # 不在去重范围 (如 ls、analyze_docx_style_samples), 保留
                        kept_tc.append(tc)
                    elif key in seen:
                        # 同一 target 已经有更新的, 这个旧了, 标记跳过
                        skip_tc_ids.add(tc["id"])
                    else:
                        # 新的 target, 第一次出现 (从后往前看), 保留
                        seen[key] = tc["id"]
                        kept_tc.append(tc)

                if kept_tc:
                    # 有保留的 tool_call: 复制消息 + 替换 tool_calls 列表
                    entry_copy = dict(entry)
                    entry_copy["tool_calls"] = kept_tc
                    result_rev.append(entry_copy)
                elif entry.get("content"):
                    # 兜底补丁: kept_tc 空但有 content 时 (典型: 断网导致所有
                    # tool_calls 的 tool result 都没保存)
                    # → 保留纯文本, 清空 tool_calls 字段
                    # → 用户能看到 LLM 至少"开口说了句话" ("我将使用工具查询...")
                    # → 同时避免 OpenAI 看到 tool_calls=[] + 无对应 tool result 又报错
                    entry_copy = dict(entry)
                    entry_copy.pop("tool_calls", None)
                    result_rev.append(entry_copy)
                # else: kept_tc 空 + 无 content → 整条丢弃 (罕见)
                continue

            # ── tool result 消息: 如果对应 tc 被去重则跳过, 否则保留 ──
            if role == "tool":
                if entry.get("tool_call_id") in skip_tc_ids:
                    continue
                result_rev.append(entry)
                continue

            # ── 其他 (system 等): 直接保留 ──
            result_rev.append(entry)

        # ── 拼接 system 消息 ──
        combined = f"{self._system_prompt}\n\n{state_prompt}"
        return [{"role": "system", "content": combined}] + list(reversed(result_rev))

    # ─── 去重逻辑 ────────────────────────────────────────

    def _dedup_key(self, tool_name: str, args: dict) -> Optional[tuple]:
        """
        提取去重 key。仅 write_markdown_draft 和 read_markdown_draft 参与去重。

        Returns:
            (tool_name, target_file) 或 None（不参与去重）
        """
        if tool_name == "write_markdown_draft":
            target = args.get("output_path")
            return ("write_markdown_draft", target) if target else None
        if tool_name == "read_markdown_draft":
            target = args.get("markdown_path")
            return ("read_markdown_draft", target) if target else None
        return None

    def update_token_count(self, usage):
        """从 LLM 响应 usage 中更新 token 计数"""
        if usage is None:
            return
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        self._total_input_tokens += prompt_tokens
        self._last_prompt_tokens = prompt_tokens

    def should_compress(self) -> bool:
        """累计 input token 超过阈值时返回 True"""
        return self._total_input_tokens > self._token_threshold

    # ─── 调试 ────────────────────────────────────────────

    @property
    def message_count(self) -> int:
        return len(self._entries)

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def last_prompt_tokens(self) -> int:
        """最近一次请求的 prompt token 数，用于前端实际显示"""
        return self._last_prompt_tokens

    def debug_info(self) -> dict:
        return {
            "message_count": len(self._entries),
            "total_input_tokens": self._total_input_tokens,
        }