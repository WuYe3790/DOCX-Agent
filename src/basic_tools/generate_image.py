"""generate_image — 主 agent 看到的"造图"工具入口

内部委托给 src/agents/image_refiner.py 跑审核-重生循环,
主 agent 只看到这一个工具, 隐藏了 sub-agent 编排的复杂性。

工具调用流:
    主 agent → generate_image(prompt, ...) → 内部 1 次生图 + sub-agent 审核
                → 返回 JSON {status, path, iterations} 给主 agent
                → 主 agent 拿到 path 写到 markdown 草稿里

⚠️ 单次调用时长:
    - max_iterations=3 (默认): 通常 30-60 秒
    - max_iterations=5 (上限): 可达 1-2 分钟
    前端应展示"生图审核中"提示, 避免用户误以为卡死。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# === 依赖 ===
sys.path.append(str(Path(__file__).parent.parent))
from llm_adapter import LLMClientAdapter  # noqa: E402
from llm_adapter.constants import SENSENOVA_U1_VALID_SIZES  # noqa: E402
from llm_adapter.registry import pick_capable_adapter  # noqa: E402
from ._media import download_to_workspace  # noqa: E402
from agents.image_refiner import run_image_refinement_loop  # noqa: E402


# === 默认参数 ===
DEFAULT_OUTPUT_FILENAME = "generated.png"
DEFAULT_SIZE = "2752x1536"          # 16:9, 2K
DEFAULT_MAX_ITERATIONS = 3          # 默认 3 轮 (子 agent 初始图 + 2 次重画)


def generate_image(
    session_id: str,
    prompt: str,
    output_filename: str = DEFAULT_OUTPUT_FILENAME,
    size: str = DEFAULT_SIZE,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> str:
    """主 agent 工具: 生成流程图/信息图, 内部审核-重画迭代直到合格或达到上限。

    Args:
        session_id:      workspace 所属 session
        prompt:          图片需求描述 (中文/英文均可)
        output_filename: workspace 内 media/ 目录下的文件名
        size:            sensenova-u1-fast 的 11 种合法尺寸之一 (默认 16:9)
        max_iterations:  sub-agent 审核员最大重画次数 (默认 3, 上限 5)

    Returns:
        JSON 字符串, 例:
        {
            "status":     "ok" | "max_iterations_reached" | "no_vision_adapter",
            "path":       "media/generated.png" (相对 workspace 根, 直接用于 markdown),
            "iterations": 总迭代次数
        }
    """
    # 防御: max_iterations 不能超过上限 (LLM 可能误传大值导致长时间阻塞)
    if max_iterations > 5:
        max_iterations = 5
    elif max_iterations < 1:
        max_iterations = 1

    # 防御: size 必须合法 (create_image_generation 也会校验, 但早抛早好)
    if size not in SENSENOVA_U1_VALID_SIZES:
        return json.dumps({
            "status": "error",
            "message": (
                f"非法 size: {size!r}。"
                f"商汤 sensenova-u1-fast 仅支持 11 种 2K 尺寸, 请参考工具 schema。"
            ),
        }, ensure_ascii=False)

    logger.info(
        "generate_image start prompt=%r filename=%s size=%s max_iterations=%d",
        prompt[:80], output_filename, size, max_iterations,
    )

    # === Step 1: 调生图 API 生成初始图 ===
    try:
        # 用 pick_capable_adapter 自动路由到具备 text_to_image capability 的 provider
        # 例如当前 provider 是 deepseek (无生图能力),会自动切换到 sensenova
        main_adapter = LLMClientAdapter()
        img_adapter = pick_capable_adapter(main_adapter, "text_to_image")
        if img_adapter is None:
            return json.dumps({
                "status": "error",
                "message": (
                    f"当前激活的 provider '{main_adapter.get_provider()}' 不支持生图,"
                    "且 config.json 的 providers 中未配置任何具备 text_to_image capability 的模型。"
                ),
            }, ensure_ascii=False)

        resp = img_adapter.create_image_generation(prompt=prompt, size=size, n=1)
        img_url = resp.data[0].url
    except Exception as exc:
        logger.exception("generate_image initial failed")
        return json.dumps({
            "status": "error",
            "message": f"初始生图失败: {exc}",
        }, ensure_ascii=False)

    # === Step 2: 下载到 workspace ===
    try:
        initial_abs_path = download_to_workspace(session_id, img_url, output_filename)
    except Exception as exc:
        logger.exception("generate_image download failed")
        return json.dumps({
            "status": "error",
            "message": f"下载初始图失败: {exc}",
        }, ensure_ascii=False)

    # === Step 3: 启动 sub-agent 审核循环 ===
    try:
        result = run_image_refinement_loop(
            session_id=session_id,
            initial_prompt=prompt,
            initial_image_path=initial_abs_path,
            filename=output_filename,
            size=size,
            max_iterations=max_iterations,
        )
    except Exception as exc:
        logger.exception("generate_image subagent failed")
        # sub-agent 整体崩溃 (例如网络断开) → 返回初始图路径, 至少能用
        return json.dumps({
            "status": "subagent_crashed",
            "path": _abs_to_rel(initial_abs_path),
            "iterations": 1,
            "message": f"sub-agent 异常, 已返回初始图: {exc}",
        }, ensure_ascii=False)

    # === Step 4: 转换为相对路径返回 (markdown 语法可直接引用) ===
    final_abs_path = result["path"]
    final_rel_path = _abs_to_rel(final_abs_path)

    logger.info(
        "generate_image done status=%s iterations=%d",
        result["status"], result["iterations"],
    )

    return json.dumps({
        "status": result["status"],
        "path": final_rel_path,
        "iterations": result["iterations"],
    }, ensure_ascii=False)


def _abs_to_rel(abs_path: str) -> str:
    """绝对路径 → 相对 workspace 根的路径, 供 markdown 语法引用。"""
    # 形如 out/sessions/<id>/workspace/media/x.png → media/x.png
    parts = Path(abs_path).parts
    try:
        workspace_idx = parts.index("workspace")
        return "/".join(parts[workspace_idx + 1:])
    except ValueError:
        # 兜底: 不在标准 workspace 结构里时,返回原路径
        return abs_path


# === Tool schema (主 agent 看到的) ===
tools_schema = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "生成流程图/信息图。内部自动调用商汤 vision 模型审核,"
            "如果不完美会自动修改提示词重画,最多重画 max_iterations 次。"
            "单次调用通常耗时 30-90 秒,期间前端会显示'生图审核中'。"
            "返回的 path 是相对于 session workspace 的路径, 直接用于"
            " markdown 图片语法 ![描述|center](path) 或 docx 嵌入。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "图片需求描述 (中文/英文均可), 建议详细描述"
                        "布局、元素、文字内容、风格"
                    ),
                },
                "output_filename": {
                    "type": "string",
                    "default": DEFAULT_OUTPUT_FILENAME,
                    "description": "workspace 内 media/ 目录下的文件名, 默认 generated.png",
                },
                "size": {
                    "type": "string",
                    "enum": sorted(SENSENOVA_U1_VALID_SIZES),
                    "default": DEFAULT_SIZE,
                    "description": (
                        "图片尺寸, 商汤 sensenova-u1-fast 仅支持这 11 种 2K 尺寸"
                    ),
                },
                "max_iterations": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": DEFAULT_MAX_ITERATIONS,
                    "description": (
                        "审核员最大重画次数, 默认 3 (耗时约 30-60 秒),"
                        "最大 5 (可能 1-2 分钟)"
                    ),
                },
            },
            "required": ["prompt"],
        },
    },
}