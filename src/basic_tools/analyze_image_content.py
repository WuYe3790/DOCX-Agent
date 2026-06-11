import json
import os
import sys
import base64
from pathlib import Path

# v2: 沙箱化
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError  # noqa: E402

try:
    from llm_adapter import LLMClientAdapter
    from llm_adapter.registry import pick_capable_adapter
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from llm_adapter import LLMClientAdapter
    from llm_adapter.registry import pick_capable_adapter


# 10MB cap 与 read.py 对齐
MAX_IMAGE_BYTES = 10 * 1024 * 1024


def analyze_image_content(session_id: str, image_path: str, query: str = "分析图片内容") -> str:
    """v2: 多模态图像内容识别 — 路径走沙箱校验, 限制 10MB"""
    try:
        img_file = resolve_workspace_path(session_id, image_path, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        return json.dumps({
            "status": "error",
            "code": e.code,
            "message": e.user_message,
        }, ensure_ascii=False, indent=2)

    # 10MB 上限 (与 read 一致)
    if img_file.stat().st_size > MAX_IMAGE_BYTES:
        return json.dumps({
            "status": "error",
            "message": f"图片过大 ({img_file.stat().st_size} > {MAX_IMAGE_BYTES})",
        }, ensure_ascii=False, indent=2)

    try:
        with open(img_file, "rb") as f:
            base64_str = base64.b64encode(f.read()).decode("utf-8")
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": f"Failed to read/encode image file '{image_path}': {exc}"
        }, ensure_ascii=False, indent=2)

    ext = img_file.suffix.lower()
    if ext in {".jpg", ".jpeg"}:
        mime_type = "image/jpeg"
    elif ext == ".png":
        mime_type = "image/png"
    elif ext in {".gif"}:
        mime_type = "image/gif"
    elif ext in {".webp"}:
        mime_type = "image/webp"
    else:
        mime_type = "image/png"

    try:
        adapter = LLMClientAdapter()
        vision_adapter = pick_capable_adapter(adapter, "vision")
        if vision_adapter is None:
            return json.dumps({
                "status": "error",
                "message": (
                    f"当前模型提供商 '{adapter.get_provider()}' 不支持图像理解,"
                    "且 config.json 的 providers 中未配置任何具备 vision capability 的模型。"
                )
            }, ensure_ascii=False, indent=2)

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_str}"}}
            ]
        }]

        response = vision_adapter.create_chat_completion(
            messages=messages,
            reasoning_effort="none"
        )
        content = response.choices[0].message.content

        return json.dumps({
            "status": "ok",
            "image_path": str(img_file),
            "query": query,
            "provider": vision_adapter.get_provider(),
            "model": vision_adapter.get_model_name(),
            "analysis": content
        }, ensure_ascii=False, indent=2)

    except Exception as exc:
        return json.dumps({
            "status": "error",
            "message": f"Multimodal API call failed: {exc}"
        }, ensure_ascii=False, indent=2)


tools_schema = {
    "type": "function",
    "function": {
        "name": "analyze_image_content",
        "description": "多模态图像识别与理解工具。传入 session workspace 内的图片路径和相关查询, 返回模型对该图片视觉内容的分析。",
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "待分析图片路径 (相对 workspace 根)"
                },
                "query": {
                    "type": "string",
                    "description": "对图片内容的具体提问或分析指令, 默认为 '分析图片内容'"
                }
            },
            "required": ["image_path"]
        }
    }
}
