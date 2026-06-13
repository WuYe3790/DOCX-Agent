"""image_refiner — 生成图后的内部审核-重画子 agent

项目里第一个 sub-agent 实现,由 src/basic_tools/generate_image.py 内部调用。

职责:
    1. 接收用户初始 prompt 和已生成的初始图
    2. 启动内部 LLM 循环 (用商汤 vision 模型当审核员)
    3. 子 agent 每轮审视当前图,决定:
       - 调用 regenerate_image (修改 prompt 重画) — 阅后即焚清理历史图后注入新图
       - 调用 finish_image      (审核通过, 结束循环)
    4. 返回最终图路径给主 agent (隐藏内部 reasoning)

主 agent 看不到这个模块,只看到 generate_image 工具。

关键设计:
    - 阅后即焚 (_strip_old_images): 每次重生图前清空 history 中历史 base64,
      防止 payload 累积到 10-25MB 触发商汤 max_tokens 错误
    - 进度 logging (log_subagent_progress): 写到 module logger,
      供 session log 收集,前端可订阅缓解 WS 假死感知
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# === 模块日志 ===
# 输出格式简洁,便于 session log 收集与前端订阅
logger = logging.getLogger(__name__)

# === 依赖 ===
sys.path.append(str(Path(__file__).parent.parent))
from llm_adapter import LLMClientAdapter  # noqa: E402
from llm_adapter.registry import pick_capable_adapter  # noqa: E402
from basic_tools._media import (  # noqa: E402
    download_to_workspace,
    encode_image_as_data_url,
)


# === 阅后即焚占位符 ===
# 替换 history 中所有历史 base64 图片,节约 ~3MB/张 的 token 成本
PLACEHOLDER_HISTORY_IMAGE = "[历史图片已从上下文中移除, 请参考最新注入的图片]"


# === 子 agent 的 system prompt ===
# 关键纪律: 调用 finish_image 前必须先用文字描述图片元素,
# 避免 LLM 偷懒直接 PASS。
REFINE_SYSTEM_PROMPT = """你是图像质量审核员, 任务是把 AI 生成的图片改到完美。

【用户原始需求】
{user_prompt}

【你的能力】
- 图片每轮都自动注入到你的视野, 你看得见当前图。
- 你有两个工具: regenerate_image (重画)、finish_image (通过)。
- 你不需要额外的"看图"工具, 直接用自然语言描述你看到什么。

【可用工具】
1. regenerate_image(new_prompt, reason)
   - 重生图。new_prompt 必须是完整的、修改后的生图 prompt, 要显式解决当前图的问题
   - reason 用一句话说明你看到了什么问题
2. finish_image(reason)
   - 审核通过, 结束流程

【判断标准】遇到以下任一情况必须 regenerate:
- 文字模糊/缺失/乱码
- 元素缺失或错位
- 布局混乱、元素重叠
- 风格不符合需求

【行为准则】
- 不要勉强通过。如果有疑虑, 继续 regenerate。
- new_prompt 要比原 prompt 更具体、更结构化 (显式列出所有需要的元素)。
- 最多 {max_iterations} 轮。

【关键纪律】调用 finish_image 之前, 你必须先用文字明确回答:
1. 当前图片中有哪些元素 (节点、文字、连接线等)?
2. 每个元素是否清晰可读、位置是否正确?
3. 是否满足用户原始需求的所有要点?

只有当上述描述都确认无误时, 才能调用 finish_image。否则必须 regenerate。"""


# === 子 agent 的 2 个工具 schema ===
# 仅子 agent 可见, 主 agent 通过 tool scope 隔离看不到这些
SUB_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "regenerate_image",
            "description": "基于修改后的 prompt 重新生成图片, 新图会在下一轮注入到你的视野",
            "parameters": {
                "type": "object",
                "properties": {
                    "new_prompt": {
                        "type": "string",
                        "description": "修改后的生图 prompt, 要求更明确更结构化",
                    },
                    "reason": {
                        "type": "string",
                        "description": "一句话说明当前图的问题",
                    },
                },
                "required": ["new_prompt", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_image",
            "description": "审核通过, 结束流程",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "一句话说明为什么通过",
                    },
                },
                "required": ["reason"],
            },
        },
    },
]


# === 上下文容器 (主循环内部维护) ===
class _RefineContext:
    """子 agent 循环的运行时上下文。

    比 dict 优势: 类型提示清晰、IDE 跳转友好、单元测试可构造。
    """
    def __init__(
        self,
        session_id: str,
        filename: str,
        initial_image_path: str,
        size: str,
    ):
        self.session_id = session_id
        self.filename = filename
        self.current_image_path = initial_image_path
        self.size = size
        self.iteration_count = 1  # 初始图算第 1 次
        self.finished = False
        self.finish_reason: str | None = None


# === 工具 handler: regenerate_image ===
def _exec_regenerate_image(args: dict, ctx: _RefineContext) -> dict:
    """重生图: 调生图 API → 下载到 workspace → 更新 ctx.current_image_path。

    handler 不操作 history, 由主循环负责 base64 注入。
    """
    new_prompt = args["new_prompt"]
    reason = args.get("reason", "")
    logger.info("subagent_regenerate iteration=%d reason=%s", ctx.iteration_count + 1, reason[:80])

    adapter = LLMClientAdapter()
    resp = adapter.create_image_generation(prompt=new_prompt, size=ctx.size)
    img_url = resp.data[0].url

    # 覆盖写回 workspace (filename 不变, 实现"原地替换")
    new_path = download_to_workspace(ctx.session_id, img_url, ctx.filename)
    ctx.current_image_path = new_path
    ctx.iteration_count += 1

    return {
        "status": "regenerated",
        "new_image_path": new_path,
        "iteration": ctx.iteration_count,
    }


# === 工具 handler: finish_image ===
def _exec_finish_image(args: dict, ctx: _RefineContext) -> dict:
    """审核通过: 设置 finished=True, 主循环下次迭代检测到即退出。"""
    reason = args.get("reason", "")
    logger.info("subagent_finish iteration=%d reason=%s", ctx.iteration_count, reason[:80])
    ctx.finished = True
    ctx.finish_reason = reason
    return {"status": "finished"}


# === handler dispatch 表 ===
TOOL_DISPATCH: dict[str, callable] = {
    "regenerate_image": _exec_regenerate_image,
    "finish_image": _exec_finish_image,
}


# === 阅后即焚 (防止 Context Explosion) ===
def _strip_old_images(history: list[dict]) -> None:
    """就地修改 history: 把所有历史 base64 图片替换为占位符文本。

    必要性: 一张 2K 图 base64 后 ~2-5MB。若不清理, 5 轮迭代后 history payload
    累积到 10-25MB, 极大概率触发商汤 400 错误 (超出 max_tokens)。

    替换规则: 任何 role=user 消息里的 image_url content 块都换成 text 占位符。
    其他消息 (system / assistant / tool) 不变。
    """
    for msg in history:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            new_content = []
            for item in msg["content"]:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    new_content.append({"type": "text", "text": PLACEHOLDER_HISTORY_IMAGE})
                else:
                    new_content.append(item)
            msg["content"] = new_content


# === 主循环入口 ===
def run_image_refinement_loop(
    session_id: str,
    initial_prompt: str,
    initial_image_path: str,
    filename: str,
    size: str,
    max_iterations: int,
) -> dict:
    """运行子 agent 审核循环, 返回 {status, final_path, iterations}。

    Args:
        session_id:         workspace 所属 session
        initial_prompt:     用户原始 prompt (子 agent system prompt 注入)
        initial_image_path: 初始图绝对路径 (调用方已生成并保存到 workspace)
        filename:           输出文件名 (例如 "rag.png"), 重生时覆盖写回
        size:               sensenova-u1-fast 的 11 种合法尺寸之一
        max_iterations:     最大重画次数 (默认 3, 上限 5)

    Returns:
        {
            "status":     "ok" | "max_iterations_reached",
            "path":       最终图绝对路径,
            "iterations": 总迭代次数 (含初始图),
        }
    """
    ctx = _RefineContext(
        session_id=session_id,
        filename=filename,
        initial_image_path=initial_image_path,
        size=size,
    )

    # 选 vision adapter (与 analyze_image_content 共用选 provider 逻辑)
    main_adapter = LLMClientAdapter()
    vision_adapter = pick_capable_adapter(main_adapter, "vision")
    if vision_adapter is None:
        logger.warning("subagent_no_vision_adapter")
        return {
            "status": "no_vision_adapter",
            "path": ctx.current_image_path,
            "iterations": 1,
        }

    system_prompt = REFINE_SYSTEM_PROMPT.format(
        user_prompt=initial_prompt,
        max_iterations=max_iterations,
    )

    # 第 1 轮: 注入初始图
    history: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"用户需求:\n{initial_prompt}\n\n当前图片 (第 1 次生成):"},
                {"type": "image_url", "image_url": {"url": encode_image_as_data_url(ctx.current_image_path)}},
            ],
        },
    ]
    logger.info("subagent_start iteration=1 max_iterations=%d", max_iterations)

    for iteration in range(max_iterations):
        response = vision_adapter.create_chat_completion(
            messages=history,
            tools=SUB_TOOL_SCHEMAS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # 边界 1: LLM 不调工具只回文本 → 注入引导消息, 继续下一轮
        if not msg.tool_calls:
            logger.info("subagent_text_only iteration=%d", iteration + 1)
            history.append({"role": "assistant", "content": msg.content or ""})
            history.append({
                "role": "user",
                "content": "请调用工具: regenerate_image 重画, 或 finish_image 通过。不要只回复文本。",
            })
            continue

        history.append(msg)  # assistant 消息 (含 tool_calls)

        for tc in msg.tool_calls:
            handler = TOOL_DISPATCH.get(tc.function.name)
            if handler is None:
                # LLM 幻觉工具名 → 注入错误引导
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": f"未知工具: {tc.function.name}"}, ensure_ascii=False),
                })
                continue

            # 解析参数 (vision 模型偶有 JSON 解析失败)
            try:
                tool_args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
            except json.JSONDecodeError as exc:
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": f"参数 JSON 解析失败: {exc}"}, ensure_ascii=False),
                })
                continue

            # 执行 handler
            try:
                result = handler(tool_args, ctx)
            except Exception as exc:
                # handler 异常 (生图失败 / 下载失败) → 注入错误给 LLM 决策
                logger.exception("subagent_handler_error tool=%s", tc.function.name)
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": f"{tc.function.name} 执行失败: {exc}"}, ensure_ascii=False),
                })
                continue

            history.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

            # 关键两步: (1) 阅后即焚 (2) 注入新图
            if tc.function.name == "regenerate_image":
                _strip_old_images(history)  # 清空历史图
                history.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"第 {ctx.iteration_count} 次生成的新图, 请仔细审视:"},
                        {"type": "image_url", "image_url": {
                            "url": encode_image_as_data_url(ctx.current_image_path)
                        }},
                    ],
                })

        # 循环终止条件: 子 agent 调了 finish_image
        if ctx.finished:
            return {
                "status": "ok",
                "path": ctx.current_image_path,
                "iterations": ctx.iteration_count,
            }

    # max_iterations 用尽仍未 finish → 返回当前图路径, 主 agent 决定
    logger.info("subagent_max_iterations iterations=%d", ctx.iteration_count)
    return {
        "status": "max_iterations_reached",
        "path": ctx.current_image_path,
        "iterations": ctx.iteration_count,
    }