"""B 方案单元测试: finish_reason=None 流不完整时 API 重试 + 兜底降级

测什么:
- Case 0: 初始化字段 _stream_incomplete_retries 存在且为 0
- Case 1: 流正常结束 (finish_reason=stop + content) → 不重试, 日志无 retry 事件
- Case 2: 流不完整 (finish_reason=None + 无 tool_calls + reasoning 有内容) → 重试 1 次后正常
         conversation 不污染 (重试时不 append_assistant), 计数被清零
- Case 3: 连续 3 次不完整 → 重试耗尽 (_MAX=2) → 落到原"空响应自动引导"作为兜底

设计:
- StreamingMockLLM 按脚本序列返回不同 stream chunks
- MockChunk/MockChoice/MockDelta 三层结构, 匹配 OpenAI SDK 流式形状
- 测试在 wait_approval/done/error 时退出, 防止无限等待审批

注意:
- 不依赖真实 OpenAI SDK pydantic model_dump, 用最小化 mock
- agent.step() 只用 getattr 访问 delta 字段, 简单类够用
"""
import sys
import asyncio
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent import Agent
from context_manager import MessageManager


# ─── Mock 三层结构: MockChunk → MockChoice → MockDelta ─────────

class MockDelta:
    """模拟 chunk.choices[0].delta — agent.step 只用 getattr(...)"""
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls
        # 商汤的 reasoning 走 model_extra (agent.py:458)
        self.model_extra = {}


class MockChoice:
    def __init__(self, delta, finish_reason=None):
        self.delta = delta
        self.finish_reason = finish_reason


class MockChunk:
    def __init__(self, choices, usage=None):
        self.choices = choices
        self.usage = usage


def chunk(content=None, reasoning=None, tool_calls=None, finish_reason=None):
    """构造单个 chunk 的便捷函数"""
    delta = MockDelta(content=content, reasoning_content=reasoning, tool_calls=tool_calls)
    return MockChunk(choices=[MockChoice(delta=delta, finish_reason=finish_reason)])


# ─── Mock LLM 适配器 ─────────────────────────────────────────────

class StreamingMockLLM:
    """Mock LLM: 按预设序列返回不同的 stream chunks (每次 create_chat_completion 调用消费一个脚本)"""
    def __init__(self, scripted_responses):
        self.scripted = list(scripted_responses)
        self.call_count = 0
        self.provider = "sensenova"
        # Step 3 兼容:agent.py 改用 self.llm.reasoning_field + extract_reasoning。
        # 这里测试用 MockDelta 的 reasoning 数据放在 reasoning_content 字段
        # (见 MockDelta.__init__),故选 deepseek path 路径让 agent 能正确提取。
        self.reasoning_field = "delta.reasoning_content"

    def get_provider(self): return self.provider
    def get_model_name(self): return "sensenova-test"
    def get_thinking_type(self): return "disabled"
    def get_reasoning_effort(self): return "high"

    def create_chat_completion(self, messages, tools=None, **kwargs):
        if self.call_count >= len(self.scripted):
            raise RuntimeError(
                f"Mock LLM 调用次数超过脚本: 第 {self.call_count + 1} 次 > 准备的 {len(self.scripted)} 次"
            )
        chunks = self.scripted[self.call_count]
        self.call_count += 1
        return iter(chunks)


# ─── 测试工具函数 ──────────────────────────────────────────────

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
    """构造 MD_DRAFT 状态的 agent, draft_files_written 已含一项 (绕过审批阶段的检查)"""
    msg_mgr = MessageManager("test-system")
    msg_mgr._entries = [{"role": "user", "content": "请生成 markdown 草稿"}]
    agent = Agent(
        system_prompt="test-system",
        llm_adapter=llm,
        msg_mgr=msg_mgr,
        log_path=log_path,
    )
    agent.workflow_state = "md_draft"
    agent.draft_files_written = ["fake_draft.md"]   # 让 wait_approval 检查通过
    return agent


# ─── 测试用例 ─────────────────────────────────────────────────

def test_init_field_exists():
    """Case 0: __init__ 加的 _stream_incomplete_retries 字段存在且为 0"""
    class StubLLM:
        provider = "deepseek"
        reasoning_field = "delta.reasoning_content"   # Step 3 兼容:agent 流式循环用它
        def get_provider(self): return "deepseek"
        def get_model_name(self): return "stub"
        def get_thinking_type(self): return "disabled"
        def get_reasoning_effort(self): return None

    agent = Agent(
        system_prompt="test", llm_adapter=StubLLM(),
        msg_mgr=MessageManager("test"),
    )
    assert hasattr(agent, "_stream_incomplete_retries"), "Agent 应有 _stream_incomplete_retries 字段"
    assert agent._stream_incomplete_retries == 0, f"初始值应为 0, 实际 {agent._stream_incomplete_retries}"
    print("[OK] Case 0: 初始化字段存在且为 0")


def test_normal_stream_no_retry():
    """Case 1: 流正常结束 (finish_reason=stop + content) → 不重试, 日志无 retry 事件"""
    llm = StreamingMockLLM([[
        chunk(content="这是一段正常响应内容,足够长以避免空响应引导。"),
        chunk(finish_reason="stop"),
    ]])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_b_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")

    events = asyncio.run(run_until_terminal(agent))

    assert llm.call_count == 1, f"应该只调 1 次 LLM, 实际 {llm.call_count}"
    assert agent._stream_incomplete_retries == 0, "正常流不应改变计数"
    log_content = (tmpdir / "test.log").read_text(encoding="utf-8")
    assert "stream_incomplete_retry" not in log_content, "正常流日志不应有 retry 事件"
    print("[OK] Case 1: 正常流 → 不重试, 日志干净")


def test_incomplete_stream_one_retry():
    """Case 2: 流不完整 → 重试 1 次后正常 → conversation 干净 + 计数清零"""
    # 第 1 次: 流不完整 (无 finish_reason 无 content 无 tool_calls, 只有 reasoning)
    incomplete = [chunk(reasoning="我在想第四部分应该怎么写")]
    # 第 2 次: 正常响应
    normal = [
        chunk(content="重试后正常响应,内容足够长以避免空响应引导。"),
        chunk(finish_reason="stop"),
    ]
    llm = StreamingMockLLM([incomplete, normal])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_b_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")

    initial_entries = len(agent.msg_mgr._entries)
    events = asyncio.run(run_until_terminal(agent))

    assert llm.call_count == 2, f"应该调 2 次 LLM (1 原始 + 1 重试), 实际 {llm.call_count}"
    # 关键: 重试时不 append_assistant, conversation 不该被第一次 incomplete 响应污染
    # 只有第二次正常响应 append 一次 assistant (= +1 entry)
    added = len(agent.msg_mgr._entries) - initial_entries
    assert added == 1, f"重试不该污染 conversation, 应只 +1 entry (正常响应的 assistant), 实际 +{added}"
    assert agent._stream_incomplete_retries == 0, "成功后计数应清零"
    log_content = (tmpdir / "test.log").read_text(encoding="utf-8")
    assert "stream_incomplete_retry" in log_content, "日志应记录 retry 事件"
    print("[OK] Case 2: 流不完整 → 重试 1 次 → conversation 干净 + 计数清零")


def test_incomplete_stream_exhausts_retries():
    """Case 3: 连续 3 次不完整 (1 原始 + 2 重试) → 重试耗尽 → 落到原"空响应自动引导"兜底"""
    incomplete = [chunk(reasoning="一直在想但没产出")]
    fallback_normal = [
        chunk(content="兜底引导后正常响应,内容足够长以避免再次引导。"),
        chunk(finish_reason="stop"),
    ]
    # 1 原始 + 2 重试 = 3 次 incomplete (耗尽); 第 4 次是兜底引导后的下一轮
    llm = StreamingMockLLM([incomplete, incomplete, incomplete, fallback_normal])
    tmpdir = Path(tempfile.mkdtemp(prefix="docx_agent_test_b_"))
    agent = make_agent_md_draft(llm, tmpdir / "test.log")

    events = asyncio.run(run_until_terminal(agent))

    # 第 1 次 (incomplete, retry++=1) → 第 2 次 (incomplete, retry++=2) →
    # 第 3 次 (incomplete, retry 已达上限 2, 走 exhausted 分支, 走原引导路径 → 注入引导消息 + continue)
    # → 第 4 次 (fallback_normal, 进 wait_approval)
    assert llm.call_count == 4, f"应该调 4 次 LLM (1+2 retry + 1 兜底后), 实际 {llm.call_count}"
    log_content = (tmpdir / "test.log").read_text(encoding="utf-8")
    assert "stream_incomplete_retry" in log_content, "日志应有 stream_incomplete_retry 事件"
    assert "stream_incomplete_retry_exhausted" in log_content, "日志应有重试耗尽事件"
    assert "空响应自动引导" in log_content, "重试耗尽后应触发原'空响应自动引导'兜底"
    assert agent._stream_incomplete_retries == 0, "兜底后计数应清零"
    print("[OK] Case 3: 连续 3 次不完整 → 重试耗尽 → 落到空响应引导兜底")


if __name__ == "__main__":
    test_init_field_exists()
    test_normal_stream_no_retry()
    test_incomplete_stream_one_retry()
    test_incomplete_stream_exhausts_retries()
    print()
    print("=" * 50)
    print("✓ B 方案 4 个单元测试全部通过")
    print("=" * 50)
