"""非流式路径单元测试 — 验证 agent.py 走 create_chat_completion_blocking() 时
   能正确填充 accumulated_content / tool_calls_map / finish_reason / accumulated_reasoning。

测什么:
- Case 0: set_stream_mode(True/False) 切换 _stream_mode, 并写日志
- Case 1: 阻塞响应 (content + finish_reason=stop) → 走非流式路径, content 进 messages
- Case 2: 阻塞响应 (SenseNova 风格 message.model_extra.reasoning) → reasoning 提取
- Case 3: 阻塞响应 (tool_calls) → tool_calls_map 填充
- Case 4: 阻塞响应失败 (除 _RETRYABLE_EXC 外) → yield error, 不污染 conversation
- Case 5: 流式路径(回归)— _stream_mode=True 仍走 create_chat_completion(stream=True)

设计:
- BlockingMockLLM 提供 create_chat_completion_blocking 返回预制 ChatCompletion 形状
- MockResponse/MockChoice/MockMessage/MockToolCall/MockUsage 五层 mock 匹配 OpenAI SDK 形状
- agent.step() 只用 getattr 访问, 简单类够用
"""
import sys
import asyncio
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent import Agent
from context_manager import MessageManager


# ─── Mock 5 层结构(匹配 OpenAI SDK ChatCompletion 形状) ──────

class MockUsage:
    def __init__(self, prompt_tokens=100, completion_tokens=50, total_tokens=150):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class MockFunction:
    def __init__(self, name="", arguments=""):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, id="", index=0, function=None):
        self.id = id
        self.index = index
        self.function = function or MockFunction()


class MockMessage:
    """模拟 response.choices[0].message — agent.py 用 getattr 访问"""
    def __init__(self, content=None, tool_calls=None, model_extra=None):
        self.content = content
        self.tool_calls = tool_calls
        # 商汤的非流式 reasoning 路径: message.model_extra.reasoning
        self.model_extra = model_extra or {}


class MockChoice:
    def __init__(self, message, finish_reason=None):
        self.message = message
        self.finish_reason = finish_reason


class MockResponse:
    """模拟 create_chat_completion_blocking() 返回的 ChatCompletion 对象"""
    def __init__(self, content=None, tool_calls=None, reasoning=None,
                 finish_reason="stop", usage=None):
        model_extra = {}
        if reasoning is not None:
            model_extra["reasoning"] = reasoning
        msg = MockMessage(content=content, tool_calls=tool_calls, model_extra=model_extra)
        self.choices = [MockChoice(msg, finish_reason=finish_reason)]
        self.usage = usage or MockUsage()


# ─── Mock LLM 适配器 ────────────────────────────────────────────

class BlockingMockLLM:
    """Mock LLM: 阻塞模式. 脚本序列: 每次 create_chat_completion_blocking 调用消费一个 MockResponse"""
    def __init__(self, scripted_responses):
        self.scripted = list(scripted_responses)
        self.call_count = 0
        self.provider = "sensenova"
        # 非流式下 reasoning 走 message.model_extra.reasoning, 但 agent.py Step 2 在
        # 非流式分支**手工**从 model_extra 提取, 不调 extract_reasoning, 所以这个字段
        # 对非流式行为没影响 — 留 default 即可
        self.reasoning_field = "delta.model_extra.reasoning"
        # 非流式不走流式循环, quirks 不触发
        self.quirks = ()

    def get_provider(self): return self.provider
    def get_model_name(self): return "sensenova-test"
    def get_thinking_type(self): return "disabled"
    def get_reasoning_effort(self): return "high"

    def create_chat_completion_blocking(self, messages, tools=None, **kwargs):
        if self.call_count >= len(self.scripted):
            raise RuntimeError(
                f"Mock LLM 阻塞调用次数超过脚本: 第 {self.call_count + 1} 次 > {len(self.scripted)}"
            )
        resp = self.scripted[self.call_count]
        self.call_count += 1
        return resp


class DualModeMockLLM(BlockingMockLLM):
    """同时实现 create_chat_completion (流式) 和 create_chat_completion_blocking (非流式)"""
    def __init__(self, *args, streaming_chunk_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.streaming_chunk_factory = streaming_chunk_factory or (lambda i: [])
        self.stream_call_count = 0

    def create_chat_completion(self, messages, tools=None, **kwargs):
        self.stream_call_count += 1
        return iter(self.streaming_chunk_factory(self.stream_call_count))


# ─── 测试工具 ────────────────────────────────────────────────

async def run_until_terminal(agent, max_events=200):
    """跑 agent.step() 直到 wait_approval/done/error 或事件超限"""
    events = []
    async for ev in agent.step():
        events.append(ev)
        if ev.get("type") in ("wait_approval", "done", "error"):
            break
        if len(events) >= max_events:
            break
    return events


def make_agent_md_draft(llm, log_path):
    """构造 MD_DRAFT 状态的 agent, draft_files_written 已含一项 (绕过 wait_approval 检查)"""
    msg_mgr = MessageManager("test-system")
    msg_mgr._entries = [{"role": "user", "content": "请生成 markdown 草稿"}]
    agent = Agent(
        system_prompt="test-system",
        llm_adapter=llm,
        msg_mgr=msg_mgr,
        log_path=log_path,
    )
    agent.workflow_state = "md_draft"
    agent.draft_files_written = ["fake_draft.md"]
    return agent


# ─── 测试用例 ─────────────────────────────────────────────────

def test_set_stream_mode_toggle():
    """Case 0: set_stream_mode(True/False) 切换 _stream_mode, 写日志"""
    class StubLLM:
        provider = "deepseek"
        reasoning_field = "delta.reasoning_content"
        quirks = ()
        def get_provider(self): return "deepseek"
        def get_model_name(self): return "stub"
        def get_thinking_type(self): return "disabled"
        def get_reasoning_effort(self): return None

    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_blocking_"))
    agent = Agent(
        system_prompt="test", llm_adapter=StubLLM(),
        msg_mgr=MessageManager("test"),
        log_path=tmpdir / "test.log",
    )
    # 默认 True
    assert agent._stream_mode is True, f"默认应 True, 实际 {agent._stream_mode}"
    # 切到 False
    agent.set_stream_mode(False)
    assert agent._stream_mode is False, "set_stream_mode(False) 后应为 False"
    # 切回 True
    agent.set_stream_mode(True)
    assert agent._stream_mode is True, "set_stream_mode(True) 后应为 True"
    # 日志记录 (用 _append_log 写在 log_path)
    log_content = (tmpdir / "test.log").read_text(encoding="utf-8")
    assert "stream_mode_changed" in log_content, "日志应记录 stream_mode_changed 事件"
    assert '"stream_mode": false' in log_content or '"stream_mode": false' in log_content.lower()
    print("[OK] Case 0: set_stream_mode 切换正确 + 写日志")


def test_agent_init_stream_mode_param():
    """Case 0b: Agent(stream_mode=False) __init__ 直接以非流式初始化 (新会话初始模式)
    这是用户"新对话直接以非流式启动"诉求的实现验证 — server.py 从 WS start 帧读
    stream_mode 字段, 构造 Agent 时传入, 避免触发 SSE stall 后再切的体验问题。
    """
    class StubLLM:
        provider = "sensenova"
        reasoning_field = "delta.model_extra.reasoning"
        quirks = ()
        def get_provider(self): return "sensenova"
        def get_model_name(self): return "sensenova-6.7-flash-lite"
        def get_thinking_type(self): return "disabled"
        def get_reasoning_effort(self): return "high"

    # 场景 1: stream_mode=False (商汤用户偏好非流式)
    agent_blocking = Agent(
        system_prompt="test", llm_adapter=StubLLM(),
        msg_mgr=MessageManager("test"),
        stream_mode=False,
    )
    assert agent_blocking._stream_mode is False, \
        f"Agent(stream_mode=False)._stream_mode 应为 False, 实际 {agent_blocking._stream_mode}"

    # 场景 2: stream_mode=True (默认, 流式)
    agent_streaming = Agent(
        system_prompt="test", llm_adapter=StubLLM(),
        msg_mgr=MessageManager("test"),
        stream_mode=True,
    )
    assert agent_streaming._stream_mode is True, \
        f"Agent(stream_mode=True)._stream_mode 应为 True, 实际 {agent_streaming._stream_mode}"

    # 场景 3: 不传参数 (默认 True, 保持向后兼容)
    agent_default = Agent(
        system_prompt="test", llm_adapter=StubLLM(),
        msg_mgr=MessageManager("test"),
    )
    assert agent_default._stream_mode is True, \
        f"Agent() 默认 _stream_mode 应为 True, 实际 {agent_default._stream_mode}"
    print("[OK] Case 0b: Agent(stream_mode=...) __init__ 参数正确")


def test_blocking_content_response():
    """Case 1: 阻塞响应 (content + finish_reason=stop) → content 进 messages"""
    response = MockResponse(
        content="这是非流式响应,内容足够长以避免空响应引导。",
        finish_reason="stop",
    )
    llm = BlockingMockLLM([response])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_blocking_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")
    agent.set_stream_mode(False)

    initial_entries = len(agent.msg_mgr._entries)
    events = asyncio.run(run_until_terminal(agent))

    assert llm.call_count == 1, f"应该只调 1 次 LLM, 实际 {llm.call_count}"
    # 关键: 阻塞响应进 conversation (assistant +1)
    added = len(agent.msg_mgr._entries) - initial_entries
    assert added == 1, f"阻塞响应应 +1 entry, 实际 +{added}"
    # 内容正确
    last_entry = agent.msg_mgr._entries[-1]
    assert last_entry["role"] == "assistant"
    assert "非流式响应" in last_entry.get("content", ""), f"内容缺失: {last_entry}"
    print("[OK] Case 1: 阻塞 content 响应 → 进 messages")


def test_blocking_reasoning_extraction():
    """Case 2: 阻塞响应 (SenseNova 风格 message.model_extra.reasoning) → reasoning 提取"""
    response = MockResponse(
        content="正式回答足够长。",
        reasoning="我在思考实验过程应该怎么组织。",
        finish_reason="stop",
    )
    llm = BlockingMockLLM([response])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_blocking_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")
    agent.set_stream_mode(False)

    events = asyncio.run(run_until_terminal(agent))

    # reasoning 事件应 yield 一次
    reasoning_events = [e for e in events if e.get("type") == "reasoning"]
    assert len(reasoning_events) == 1, f"应 yield 1 次 reasoning 事件, 实际 {len(reasoning_events)}"
    assert "实验过程" in reasoning_events[0]["delta"], f"reasoning 内容缺失: {reasoning_events[0]}"
    # content 也应 yield
    content_events = [e for e in events if e.get("type") == "content"]
    assert len(content_events) == 1, f"应 yield 1 次 content 事件, 实际 {len(content_events)}"
    print("[OK] Case 2: 阻塞 reasoning (SenseNova path) → 正确提取")


def test_blocking_tool_calls():
    """Case 3: 阻塞响应 (tool_calls) → tool_calls_map 填充 + 走工具执行"""
    from openai import APITimeoutError  # noqa: F401  (确保 import 顺序稳定)
    tool_call = MockToolCall(
        id="call_test_1",
        index=0,
        function=MockFunction(name="ls", arguments='{"path": "/tmp"}'),
    )
    response = MockResponse(
        content=None,
        tool_calls=[tool_call],
        finish_reason="tool_calls",
    )
    llm = BlockingMockLLM([response])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_blocking_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")
    agent.set_stream_mode(False)

    initial_entries = len(agent.msg_mgr._entries)
    events = asyncio.run(run_until_terminal(agent))

    # tool_calls 路径会: assistant(tool_calls) + tool(result) = +2 entries
    added = len(agent.msg_mgr._entries) - initial_entries
    assert added == 2, f"tool_calls 路径应 +2 entries (assistant + tool), 实际 +{added}"
    last_assistant = agent.msg_mgr._entries[-2]
    assert last_assistant["role"] == "assistant"
    assert last_assistant.get("tool_calls"), f"assistant 应有 tool_calls: {last_assistant}"
    assert last_assistant["tool_calls"][0]["function"]["name"] == "ls"
    print("[OK] Case 3: 阻塞 tool_calls 响应 → 正确填充并执行")


def test_blocking_non_retryable_error():
    """Case 4: 阻塞响应失败 (除 _RETRYABLE_EXC 外) → yield error, 不污染 conversation"""
    from openai import BadRequestError

    class FailingLLM(BlockingMockLLM):
        def create_chat_completion_blocking(self, messages, tools=None, **kwargs):
            # 用一个普通 Exception 模拟非 _RETRYABLE_EXC 错误 (BadRequestError
            # 构造复杂且 SDK 内部还访问 response.request 属性, 测试用通用异常更稳定)
            raise RuntimeError("engine is not available temporarily (code 400)")

    llm = FailingLLM([])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_blocking_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")
    agent.set_stream_mode(False)

    initial_entries = len(agent.msg_mgr._entries)
    events = asyncio.run(run_until_terminal(agent))

    # 应 yield error 事件
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) >= 1, f"应 yield error 事件, 实际 {len(error_events)}"
    # 不污染 conversation (没有 append_assistant 也没有 append_tool_result)
    added = len(agent.msg_mgr._entries) - initial_entries
    assert added == 0, f"失败响应不应污染 conversation, 实际 +{added}"
    print("[OK] Case 4: 阻塞调用失败 → yield error, 不污染")


def test_streaming_path_still_works_regression():
    """Case 5: 流式路径(回归)— _stream_mode=True 仍走 create_chat_completion(stream=True)"""
    # 构造一个流式 chunk 序列
    from test_stream_incomplete_retry import chunk, StreamingMockLLM
    llm = StreamingMockLLM([[
        chunk(content="回归测试: 流式响应,内容足够长以避免空响应引导。"),
        chunk(finish_reason="stop"),
    ]])
    llm.reasoning_field = "delta.reasoning_content"
    # 这里要小心: StreamingMockLLM.__init__ 接受 scripted_responses, 但 call_count 跟踪
    # 流式调用次数, 而 DualModeMockLLM 用 stream_call_count
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_blocking_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")
    # _stream_mode 默认 True — 不切换
    assert agent._stream_mode is True, "默认应 True"

    initial_entries = len(agent.msg_mgr._entries)
    events = asyncio.run(run_until_terminal(agent))

    assert llm.call_count == 1, f"流式应只调 1 次, 实际 {llm.call_count}"
    added = len(agent.msg_mgr._entries) - initial_entries
    assert added == 1, f"流式响应应 +1 entry, 实际 +{added}"
    last_entry = agent.msg_mgr._entries[-1]
    assert "回归测试" in last_entry.get("content", ""), f"流式内容缺失: {last_entry}"
    print("[OK] Case 5: 流式路径(回归)— 行为不变")


if __name__ == "__main__":
    test_set_stream_mode_toggle()
    test_agent_init_stream_mode_param()
    test_blocking_content_response()
    test_blocking_reasoning_extraction()
    test_blocking_tool_calls()
    test_blocking_non_retryable_error()
    test_streaming_path_still_works_regression()
    print()
    print("=" * 50)
    print("✓ 非流式路径 7 个单元测试全部通过")
    print("=" * 50)
