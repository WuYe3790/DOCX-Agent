import json
from typing import Optional


class MessageManager:
    """
    消息管理模块：封装 messages 列表的累积、请求构建、token 追踪和去重压缩。

    消息结构：
    assistant: {role: "assistant", tool_calls: [{id: "call_xxx", function: {name: "...", arguments: "..."}}]}
    tool:      {role: "tool", tool_call_id: "call_xxx", content: "..."}

    去重单位是一对 (assistant tool_call + tool result)，通过 tool_call_id 配对。
    仅对 write_markdown_draft 和 parse_markdown_draft 按 target file 去重。
    """

    def __init__(self, system_prompt: str, token_threshold: int = 150_000):
        self._system_prompt = system_prompt
        self._token_threshold = token_threshold
        self._messages: list[dict] = []
        self._total_input_tokens: int = 0
        # {(tool_name, target): assistant 消息索引}
        self._seen: dict[tuple[str, str], int] = {}

    # ─── 消息操作 ────────────────────────────────────────

    def reset(self):
        """清空状态（新建会话时调用）"""
        self._messages = [{"role": "system", "content": self._system_prompt}]
        self._total_input_tokens = 0
        self._seen.clear()

    def append_user(self, content: str):
        self._messages.append({"role": "user", "content": content})

    def append_assistant(self, tool_calls: list, content: str = ""):
        msg: dict = {"role": "assistant", "tool_calls": tool_calls}
        if content:
            msg["content"] = content
        self._messages.append(msg)

    def append_tool_result(self, tool_call_id: str, content: str):
        self._messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content
        })

    def build_request_messages(self, state_prompt: str) -> list[dict]:
        """构建发给 LLM 的消息列表：[system + state_prompt] + messages[1:]"""
        combined = f"{self._system_prompt}\n\n{state_prompt}"
        return [{"role": "system", "content": combined}] + self._messages[1:]

    # ─── 去重逻辑 ────────────────────────────────────────

    def _dedup_key(self, tool_name: str, args: dict) -> Optional[str]:
        """提取 target file 作为去重 key，无视则返回 None"""
        if tool_name == "write_markdown_draft":
            return args.get("output_path")
        if tool_name == "parse_markdown_draft":
            return args.get("markdown_path")
        return None

    def update_token_count(self, usage):
        """从 LLM 响应 usage 中更新累计 input token 数"""
        if usage is None:
            return
        self._total_input_tokens += getattr(usage, "prompt_tokens", 0) or 0

    def should_compress(self) -> bool:
        """累计 input token 超过阈值时返回 True"""
        return self._total_input_tokens > self._token_threshold

    def compress(self):
        """
        原地压缩 self._messages，配对删除同一 (tool_name, target) 的旧 duo。
        同一文件的多次写入只保留最新的一对。
        """
        messages = self._messages

        # 1. 建立 tool_call_id -> assistant_index 映射（用于后续 tool 消息跳过）
        tc_to_asst: dict[str, int] = {}
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    tc_to_asst[tc["id"]] = i

        # 2. 遍历 assistant 消息，建立每个 (tool_name, target) 的最新索引
        seen_new: dict[tuple[str, str], int] = {}
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    key = (name, self._dedup_key(name, args))
                    if key[1] is None:
                        continue
                    seen_new[key] = i

        # 3. 找出要删除的旧 assistant 消息索引
        remove_asst_indices: set[int] = set()
        for key, new_idx in seen_new.items():
            if key in self._seen:
                remove_asst_indices.add(self._seen[key])
            self._seen[key] = new_idx

        # 4. 收集要删除的 tool_call_id
        remove_tc_ids: set[str] = set()
        for i in remove_asst_indices:
            for tc in messages[i].get("tool_calls", []):
                remove_tc_ids.add(tc["id"])

        # 5. 重建消息列表（跳过已删除 duo）
        self._messages = [
            msg for i, msg in enumerate(messages)
            if i not in remove_asst_indices
            and not (msg.get("role") == "tool" and msg.get("tool_call_id") in remove_tc_ids)
        ]

    # ─── 调试 ────────────────────────────────────────────

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    def debug_info(self) -> dict:
        return {
            "message_count": len(self._messages),
            "total_input_tokens": self._total_input_tokens,
            "seen_keys": [f"{k[0]}:{k[1]}" for k in self._seen.keys()],
        }