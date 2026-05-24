import json
import os
import base64
from pathlib import Path

try:
    from llm_adapter import LLMClientAdapter
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from llm_adapter import LLMClientAdapter


def analyze_image_content(image_path: str, query: str = "分析图片内容") -> str:
    """多模态图像内容识别工具：读取本地图片转为 base64，自适应切换至具备多模态识图能力的模型服务（如 SenseNova）进行视觉分析。"""
    img_file = Path(image_path)
    if not img_file.exists():
        return json.dumps({
            "status": "error",
            "message": f"image_path not found: '{image_path}'"
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
        vision_adapter = adapter

        if adapter.get_provider() not in {"sensenova", "openai", "gemini"}:
            has_sensenova = "sensenova" in adapter.config.get("providers", {})
            if has_sensenova:
                old_provider = os.environ.get("LLM_PROVIDER")
                os.environ["LLM_PROVIDER"] = "sensenova"
                try:
                    vision_adapter = LLMClientAdapter()
                finally:
                    if old_provider is not None:
                        os.environ["LLM_PROVIDER"] = old_provider
                    else:
                        os.environ.pop("LLM_PROVIDER", None)
            else:
                return json.dumps({
                    "status": "error",
                    "message": f"当前模型提供商 '{adapter.get_provider()}' 不支持图像理解，且 config.json 的 providers 中未配置 sensenova 等视觉大模型支持。"
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
        "description": "多模态图像识别与理解基础工具。传入本地图片路径和相关查询问题，返回模型对该图片视觉内容的分析和理解文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "待分析的本地图片文件路径（如：文档格式测试/cases/insert_image_007/test_chart.png）"
                },
                "query": {
                    "type": "string",
                    "description": "对图片内容的具体提问或分析指令，例如：'分析图片中的图表曲线走势与数值'，默认为：'分析图片内容'"
                }
            },
            "required": ["image_path"]
        }
    }
}
