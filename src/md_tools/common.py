"""md_tools 公共工具: 草稿路径解析 / 统一 JSON 返回

v2 重构: draft_path / read_markdown_text 改用 workspace.guard.resolve_workspace_path
而非手写 4 层防御。所有 md_tools 工具的 markdown 文件强制在
<session_workspace>/drafts/ 子目录下。
"""

import json
import sys
from pathlib import Path

# 引入 workspace resolver
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError  # noqa: E402


def json_result(data) -> str:
    def _clean(val):
        if isinstance(val, str):
            val_normalized = val.replace('\\', '/')
            idx = val_normalized.find("out/sessions/")
            if idx != -1:
                remaining = val_normalized[idx + 13:]
                parts = remaining.split('/', 2)
                if len(parts) >= 3 and parts[1] == "workspace":
                    return parts[2]
                elif len(parts) >= 2 and parts[1] == "workspace":
                    return "."
            return val
        elif isinstance(val, dict):
            return {k: _clean(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [_clean(x) for x in val]
        return val

    cleaned_data = _clean(data)
    return json.dumps(cleaned_data, ensure_ascii=False, indent=2)


def _drafts_subpath(raw: str) -> str:
    """把 LLM 传入的路径重写为 workspace/drafts/<filename>

    行为兼容旧 draft_path:
    - 接受纯文件名 ("cover.md") 或 "drafts/cover.md"
    - 强制 basename 化以防越界到 drafts/ 之外
    - **保留对原始 raw 中的 .. / 绝对路径检测** (在 basename 之前)
      — 这样恶意路径 "../../../etc/passwd" 仍能被识别为越界意图
    """
    # 显式守卫: 原始 raw 路径有 .. 段 / 绝对路径 → 抛 (老 draft_path 行为)
    raw_p = Path(raw)
    if any(part == ".." for part in raw_p.parts):
        raise ValueError(f"Markdown 草稿路径不允许 '..' 越界: {raw}")
    if raw_p.is_absolute() or raw.startswith("/") or raw.startswith("\\"):
        raise ValueError(f"Markdown 草稿路径不允许绝对路径: {raw}")

    return "drafts/" + raw_p.name


def draft_path(session_id: str, raw_path: str) -> Path:
    """v2: 解析草稿写入路径, 强制在 session_workspace/drafts/ 下

    Args:
        session_id: Session ID (已校验, 这里再校验一次)
        raw_path: LLM 传的路径 (纯文件名 或 drafts/<filename>)

    Returns:
        解析后绝对 Path (workspace/drafts/<filename>, 已 resolve)

    Raises:
        WorkspacePathError: 越界 / 绝对路径 / 非 .md 后缀
    """
    subpath = _drafts_subpath(raw_path)
    # must_exist=False 因为是写入场景 (草稿可能还不存在)
    try:
        target = resolve_workspace_path(session_id, subpath, must_exist=False)
    except WorkspacePathError as e:
        # 保留旧的 "Markdown 草稿路径不允许..." 错误语义
        raise ValueError(f"Markdown 草稿路径不允许{e.user_message}: {raw_path}") from e

    # 强制 .md 后缀 (旧 draft_path 行为)
    if target.suffix.lower() != ".md":
        raise ValueError("Markdown 草稿路径必须以 .md 结尾")

    # 确保父目录存在
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_markdown_text(session_id: str, raw_path: str) -> tuple[Path, str]:
    """v2: 读草稿, 路径走 resolver 沙箱化

    Args:
        session_id: Session ID
        raw_path: LLM 传的路径

    Returns:
        (target_path, content)

    Raises:
        WorkspacePathError: 越界
        FileNotFoundError: 草稿不存在
    """
    subpath = _drafts_subpath(raw_path)
    try:
        target = resolve_workspace_path(session_id, subpath, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        # 转换为 FileNotFoundError 以保留旧 API 行为 (上层 catch FileNotFoundError)
        if e.code == "not_found":
            raise FileNotFoundError(f"Markdown 草稿不存在: {raw_path}") from e
        raise ValueError(f"Markdown 草稿路径不允许{e.user_message}: {raw_path}") from e

    return target, target.read_text(encoding="utf-8")
