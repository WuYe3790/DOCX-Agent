"""共享媒体工具 — workspace 沙箱 + 图片下载/编码/消息构造

Step 2 引入: 把 analyze_image_content 的图片处理逻辑抽出来,供 generate_image
工具及其 image_refiner sub-agent 复用。

模块依赖:
    - workspace.guard  (沙箱路径解析, 单点实现)
    - urllib.request   (远程图片下载, stdlib 无新增依赖)

公开 API:
    resolve_workspace_path  — re-export from workspace.guard, 工具调用方便
    WorkspacePathError       — re-export for error handling
    download_to_workspace    — 下载远程图片 (生成图 CDN URL → workspace/media/)
    encode_image_as_data_url — 本地图片 → base64 data URL (带正确 mime type)
    build_vision_user_message — OpenAI 多模态 chat message 构造 (text + image_url)
"""

from __future__ import annotations

import base64
import sys
import urllib.request
from pathlib import Path

# === Workspace 沙箱 (re-export from workspace.guard) ===
# 不重新实现 — workspace.guard 是项目唯一路径沙箱,违反这条会导致越权漏洞
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError  # noqa: E402

__all__ = [
    "resolve_workspace_path",
    "WorkspacePathError",
    "download_to_workspace",
    "encode_image_as_data_url",
    "build_vision_user_message",
]


# MIME 类型映射 (从 analyze_image_content.py:51-61 抽出)
_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_DEFAULT_MIME = "image/png"


def download_to_workspace(session_id: str, url: str, filename: str) -> str:
    """下载远程图片到 out/sessions/<id>/workspace/media/<filename>,返回**绝对路径**。

    用途:
        - generate_image 工具: 下载 sensenova-u1-fast 返回的 CDN URL
        - image_refiner sub-agent: 下载每次重生成的新图 (handler 内需要读文件字节)

    返回:
        绝对路径字符串,供 encode_image_as_data_url 等需要 open() 的下游使用。

    调用方负责在 markdown 嵌入时转换为相对路径:
        abs_path = download_to_workspace(...)
        rel_path = os.path.relpath(abs_path, workspace_dir)
        markdown_text = f"![图]({rel_path})"

    异常:
        urllib.error.URLError: 网络错误或 URL 不可达
        WorkspacePathError:   filename 含路径分隔符或越界
        ValueError:           filename 防御性校验失败
    """
    workspace = resolve_workspace_path(session_id, "")
    media_dir = workspace / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # 防御: filename 不允许含路径分隔符,防止越权写入 workspace 之外
    if "/" in filename or "\\" in filename or filename.startswith(".."):
        raise ValueError(
            f"非法 filename: {filename!r}。不允许包含路径分隔符或 .."
        )

    target = media_dir / filename
    # urllib.request.urlretrieve 直接写入磁盘,无需先读后写
    urllib.request.urlretrieve(url, target)

    # 返回绝对路径 — 下游 (image_refiner) 需要 open() 读文件字节
    return str(target.resolve())


def encode_image_as_data_url(absolute_path: str | Path) -> str:
    """读取本地图片 → base64 data URL (含正确 mime type),供 vision LLM 调用。

    与 download_to_workspace 不同,这是本地路径 → 内存字符串,不写磁盘。
    用途:
        - image_refiner sub-agent: 把当前图注入到 LLM messages (阅后即焚前)
        - analyze_image_content: 已重构为用 build_vision_user_message

    返回:
        完整 data URL 字符串,例如 "data:image/png;base64,iVBORw0KGgo..."
        (含 mime type 前缀,这是 OpenAI vision API 的标准格式)
    """
    path = Path(absolute_path)
    ext = path.suffix.lower()
    mime_type = _MIME_BY_EXT.get(ext, _DEFAULT_MIME)

    with open(path, "rb") as f:
        base64_str = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{base64_str}"


def build_vision_user_message(text: str, image_path: str | Path) -> dict:
    """构造 vision LLM 用的 user message: text + image_url content 块。

    这是 OpenAI 多模态 chat completions 的标准格式 (image_url 类型)。
    复用于:
      - analyze_image_content 工具 (主 agent 看图)
      - image_refiner sub-agent (内部审核循环看图,每次重生后注入新图)

    Args:
        text:       用户的文字查询 / 提问 / 任务说明
        image_path: 本地图片绝对路径 (workspace 内,已沙箱校验过)

    Returns:
        OpenAI chat completion messages 格式的单条 user message,例如:
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "..."},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
            ]
        }
    """
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": encode_image_as_data_url(image_path)},
            },
        ],
    }