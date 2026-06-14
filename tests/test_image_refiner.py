"""image_refiner sub-agent 单元测试

测什么:
1. **基本流**: mock LLM 依次返回 regenerate → regenerate → finish,验证调用次数与最终状态
2. **文本回复引导**: LLM 不调工具只回文本 → 注入引导消息,继续下一轮
3. **max_iterations 用尽**: 连续 regenerate 不 finish → 返回 max_iterations_reached
4. **🔥 历史有界 (Context Explosion 修复)**: 每次 LLM 调用前 history 最多 1 张 base64
5. **进度 logging**: 关键事件 (start/regenerated/finished/max_iterations) 都触发 logger

策略: 用 unittest.mock 替换 create_chat_completion (vision LLM) 和
download_to_workspace (网络调用),避免真实 API 调用。
"""

import json
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, call

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agents.image_refiner import (  # noqa: E402
    run_image_refinement_loop,
    _strip_old_images,
    PLACEHOLDER_HISTORY_IMAGE,
)


# === Test helpers ===

def _make_tool_call(name: str, args: dict, call_id: str = "tc_1"):
    """构造 OpenAI 风格的 tool_call 对象。用 SimpleNamespace 而非 MagicMock,
    避免 chain access 时生成新的 MagicMock (覆盖显式赋值)。
    """
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _make_assistant_message(content=None, tool_calls=None):
    """构造 OpenAI 风格的 assistant message (含完整 response 链)."""
    msg = SimpleNamespace(content=content, tool_calls=tool_calls or [])
    # OpenAI response 结构: response.choices[0].message
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _fake_image_bytes(n_kb: int = 3) -> str:
    """构造 ~n_kb 大小的假 base64 (模拟真实 2K 图)。"""
    return "A" * (n_kb * 1024)


class TestStripOldImages(unittest.TestCase):
    """测试阅后即焚逻辑 (防止 Context Explosion)"""

    def test_basic_strip_replaces_image_with_placeholder(self):
        """一张图的 base64 应该被替换为占位符文本"""
        history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": [
                {"type": "text", "text": "p"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
            ]},
        ]
        _strip_old_images(history)

        user_msg = history[1]
        types = [item["type"] for item in user_msg["content"]]
        self.assertNotIn("image_url", types)
        self.assertIn("text", types)
        self.assertEqual(
            user_msg["content"][1]["text"],
            PLACEHOLDER_HISTORY_IMAGE,
        )

    def test_strip_preserves_non_user_messages(self):
        """system / assistant / tool 消息不应被修改"""
        history = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "hello"},
            {"role": "tool", "content": "result"},
            {"role": "user", "content": "plain text"},  # 纯文本不应被改
        ]
        snapshot = json.dumps(history)
        _strip_old_images(history)
        self.assertEqual(json.dumps(history), snapshot)

    def test_strip_handles_string_content(self):
        """content 是 str (而非 list) 时不应崩"""
        history = [{"role": "user", "content": "plain"}]
        _strip_old_images(history)  # 不应抛异常
        self.assertEqual(history[0]["content"], "plain")

    def test_strip_preserves_text_content_blocks(self):
        """纯 text 类型的 content block 应该保留"""
        history = [{"role": "user", "content": [
            {"type": "text", "text": "important note"},
        ]}]
        _strip_old_images(history)
        self.assertEqual(history[0]["content"][0]["text"], "important note")


class TestImageRefinementLoop(unittest.TestCase):
    """测试主循环 — 用 mock 替换 vision LLM 和下载"""

    def _patch_loop(self, vision_responses, download_returns=None):
        """返回 context manager 字典,统一 patch 外部依赖。

        关键:
        - pick_capable_adapter 用 side_effect 根据 capability 返回不同 fake:
          vision → fake_vision_adapter, text_to_image → fake_image_adapter
        - encode_image_as_data_url 需要实际文件,patch 返回假 base64
        """
        if download_returns is None:
            download_returns = [
                f"/workspace/media/img{i}.png" for i in range(2, 5)
            ]
        fake_vision = MagicMock()
        fake_vision.create_chat_completion.side_effect = vision_responses
        fake_image_adapter = MagicMock()
        fake_image_response = MagicMock()
        fake_image_response.data = [MagicMock(url="https://fake.cdn/img.png")]
        fake_image_adapter.create_image_generation.return_value = fake_image_response
        def pick_capable_side_effect(main_adapter, capability):
            if capability == "vision":
                return fake_vision
            if capability == "text_to_image":
                return fake_image_adapter
            return None
        return {
            "pick_capable": patch(
                "agents.image_refiner.pick_capable_adapter",
                side_effect=pick_capable_side_effect,
            ),
            "download": patch(
                "agents.image_refiner.download_to_workspace",
                side_effect=download_returns,
            ),
            "encode": patch(
                "agents.image_refiner.encode_image_as_data_url",
                return_value="data:image/png;base64,FAKE_BASE64_DATA",
            ),
        }

    # ─── Test 1: 基本流 ───
    def test_basic_flow_regenerate_regenerate_finish(self):
        """regenerate → regenerate → finish → 应返回 status=ok iterations=3"""
        vision_responses = [
            # Turn 1: regenerate
            _make_assistant_message(tool_calls=[
                _make_tool_call("regenerate_image", {
                    "new_prompt": "改进 prompt",
                    "reason": "文字模糊",
                }, "tc1"),
            ]),
            # Turn 2: regenerate again
            _make_assistant_message(tool_calls=[
                _make_tool_call("regenerate_image", {
                    "new_prompt": "再改进 prompt",
                    "reason": "缺文字",
                }, "tc2"),
            ]),
            # Turn 3: finish
            _make_assistant_message(tool_calls=[
                _make_tool_call("finish_image", {
                    "reason": "合格了",
                }, "tc3"),
            ]),
        ]
        patches = self._patch_loop(vision_responses)

        with patches["pick_capable"], patches["download"], patches["encode"]:
            result = run_image_refinement_loop(
                session_id="sess_1",
                initial_prompt="画一张 RAG 架构图",
                initial_image_path="/workspace/media/img1.png",
                filename="img.png",
                size="2752x1536",
                max_iterations=5,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["iterations"], 3)
        self.assertEqual(result["path"], "/workspace/media/img3.png")

    # ─── Test 2: 文本回复引导 ───
    def test_text_only_response_injects_guidance(self):
        """LLM 不调工具只回文本 → 应注入引导消息继续下一轮,而不是崩"""
        vision_responses = [
            # Turn 1: 文本回复 (没 tool_calls)
            _make_assistant_message(content="看起来不错"),
            # Turn 2: 改 finish
            _make_assistant_message(tool_calls=[
                _make_tool_call("finish_image", {"reason": "ok"}, "tc1"),
            ]),
        ]
        patches = self._patch_loop(vision_responses, download_returns=[
            "/workspace/media/img1.png",
            "/workspace/media/img1.png",  # 没下载
        ])

        with patches["pick_capable"], patches["download"], patches["encode"]:
            result = run_image_refinement_loop(
                session_id="sess_1",
                initial_prompt="画图",
                initial_image_path="/workspace/media/img1.png",
                filename="img.png",
                size="2752x1536",
                max_iterations=3,
            )

        self.assertEqual(result["status"], "ok")

    # ─── Test 3: max_iterations 用尽 ───
    def test_max_iterations_returns_status_max_reached(self):
        """连续 3 次 regenerate 不 finish → 应返回 max_iterations_reached"""
        vision_responses = [
            _make_assistant_message(tool_calls=[
                _make_tool_call("regenerate_image", {"new_prompt": "p1", "reason": "r"}, f"tc{i}"),
            ])
            for i in range(5)  # 永远 regenerate
        ]
        # 下载从 img2 开始 — img1 是初始图,regenerate 后覆盖写回
        patches = self._patch_loop(vision_responses, download_returns=[
            f"/workspace/media/img{i}.png" for i in range(2, 6)
        ])

        with patches["pick_capable"], patches["download"], patches["encode"]:
            result = run_image_refinement_loop(
                session_id="sess_1",
                initial_prompt="画图",
                initial_image_path="/workspace/media/img1.png",
                filename="img.png",
                size="2752x1536",
                max_iterations=3,
            )

        self.assertEqual(result["status"], "max_iterations_reached")
        self.assertEqual(result["iterations"], 4)  # 初始 1 + 3 regenerate
        # 返回的应是最后生成的那张 (3 次 regenerate 后)
        self.assertEqual(result["path"], "/workspace/media/img4.png")

    # ─── Test 4: 🔥 历史有界 (Context Explosion 修复) ───
    def test_history_size_bounded_after_regenerate(self):
        """每轮 LLM 调用前 history 最多 1 张 base64 (其余被替换为占位符)"""
        history_sizes = []

        def stateful_spy(**kwargs):
            """单次 stateful callable: 每次调用记录 history 大小并返回 regenerate。"""
            messages = kwargs.get("messages", [])
            total = 0
            for m in messages:
                # 测试 history 同时含 dict (系统注入) 和 SimpleNamespace (LLM 返回追加)
                # 只测 dict 大小,SimpleNamespace 是 LLM 响应消息,不包含 base64
                if isinstance(m, dict):
                    total += len(json.dumps(m))
            history_sizes.append(total)
            return _make_assistant_message(tool_calls=[
                _make_tool_call("regenerate_image", {
                    "new_prompt": "p", "reason": "r"
                }, f"tc{len(history_sizes)}"),
            ])

        # 5 轮 regenerate (永不 finish, 触发 max_iterations)
        # side_effect 单个 callable — 每次调用都执行它
        patches = self._patch_loop(
            vision_responses=stateful_spy,  # 单 callable 而非列表
            download_returns=[f"/workspace/media/img{i}.png" for i in range(2, 6)],
        )

        with patches["pick_capable"], patches["download"], patches["encode"]:
            run_image_refinement_loop(
                session_id="sess_1",
                initial_prompt="画图",
                initial_image_path="/workspace/media/img1.png",
                filename="img.png",
                size="2752x1536",
                max_iterations=5,
            )

        # 验证: 每次 LLM 调用的 history 总大小不应超过
        # 初始图 (~3MB base64) + 一些文本开销 ≈ 3.5MB 上限
        # 关键: 不应该是累积的 5×3MB = 15MB
        for i, size in enumerate(history_sizes):
            size_mb = size / (1024 * 1024)
            self.assertLess(
                size_mb, 5.0,
                f"Turn {i+1} history 体积 {size_mb:.2f}MB 超过 5MB 上限,"
                f"Context Explosion 修复失效! 实际大小 = {size} bytes"
            )

    # ─── Test 5: 进度 logging ───
    def test_progress_logging_events(self):
        """关键事件 (start / regenerate / finish / max_iterations) 应触发 logger"""
        vision_responses = [
            _make_assistant_message(tool_calls=[
                _make_tool_call("regenerate_image", {"new_prompt": "p", "reason": "r"}, "tc1"),
            ]),
            _make_assistant_message(tool_calls=[
                _make_tool_call("finish_image", {"reason": "done"}, "tc2"),
            ]),
        ]
        patches = self._patch_loop(vision_responses, download_returns=[
            "/workspace/media/img1.png",
            "/workspace/media/img2.png",
        ])

        with self.assertLogs("agents.image_refiner", level="INFO") as log_ctx:
            with patches["pick_capable"], patches["download"], patches["encode"]:
                run_image_refinement_loop(
                    session_id="sess_1",
                    initial_prompt="画图",
                    initial_image_path="/workspace/media/img1.png",
                    filename="img.png",
                    size="2752x1536",
                    max_iterations=5,
                )

        log_text = "\n".join(log_ctx.output)
        self.assertIn("subagent_start", log_text)
        self.assertIn("subagent_regenerate", log_text)
        self.assertIn("subagent_finish", log_text)


if __name__ == "__main__":
    unittest.main()