"""v2: Per-session workspace 沙箱 — 路径解析 / 文件名清洗 / 配额管理

公开 API:
- resolve_workspace_path(): 唯一路径解析入口,所有 docx / md / basic 工具都走它
- workspace_dir(): 拿 session 的 workspace 绝对路径(自动建)
- validate_session_id(): HTTP endpoint 早期校验
- safe_workspace_filename(): 上传文件名清洗
- unique_workspace_target(): 重名时返回 __1/__2 后缀路径
- build_workspace_tree(): 给 LLM 看的文件树(限制 max_depth / max_files)
- 常量: QUOTA_BYTES, MAX_FILE_BYTES, ALLOWED_EXTENSIONS
"""

from .errors import WorkspacePathError, BadUpload, ZipBombError
from .guard import (
    WORKSPACE_ROOT,
    QUOTA_BYTES,
    MAX_FILE_BYTES,
    ALLOWED_EXTENSIONS,
    workspace_dir,
    validate_session_id,
    resolve_workspace_path,
    to_relative_path,
    safe_workspace_filename,
    unique_workspace_target,
    build_workspace_tree,
)

__all__ = [
    "WorkspacePathError",
    "BadUpload",
    "ZipBombError",
    "WORKSPACE_ROOT",
    "QUOTA_BYTES",
    "MAX_FILE_BYTES",
    "ALLOWED_EXTENSIONS",
    "workspace_dir",
    "validate_session_id",
    "resolve_workspace_path",
    "to_relative_path",
    "safe_workspace_filename",
    "unique_workspace_target",
    "build_workspace_tree",
]
