"""v2: Workspace 路径解析 — 所有 docx/md/basic 工具的唯一入口

5 层防御:
1. validate_session_id (字符黑名单)
2. 拒绝空 raw_path
3. 拒绝绝对路径
4. 拒绝 parts 含 '..' 或 NUL
5. (workspace_dir / raw_path).resolve().is_relative_to(workspace_dir.resolve())
6. must_exist / must_be_file / must_be_dir 校验
7. allow_symlinks=False 时拒绝 symlink 越界
"""

import os
from pathlib import Path
from typing import List, Optional

from .errors import WorkspacePathError

# === 常量 (env 可覆盖) ===
WORKSPACE_ROOT = Path("out/sessions")  # = SESSIONS_ROOT, 跟 server.py 一致
QUOTA_BYTES = 50 * 1024 * 1024        # 50 MB per session
MAX_FILE_BYTES = 25 * 1024 * 1024     # 25 MB per file
ALLOWED_EXTENSIONS = {
    ".docx", ".doc", ".md", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".json", ".xml",
    ".zip",  # v2.1+ 新增: 压缩包走流式解压通道
}
MAX_FILENAME_LEN = 200
TREE_DEFAULT_MAX_DEPTH = 2
TREE_DEFAULT_MAX_FILES = 20


def workspace_dir(session_id: str) -> Path:
    """返回 <WORKSPACE_ROOT>/<session_id>/workspace, 自动 mkdir

    副作用: 创建 session_dir 和 workspace_dir
    """
    session_root = (WORKSPACE_ROOT / session_id).resolve()
    workspace = session_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def validate_session_id(session_id: str) -> None:
    """session_id 黑名单 — \\ / .. \\0, 长度 ≤ 100, ASCII 安全

    Raises:
        WorkspacePathError(code="name_invalid")
    """
    if not session_id:
        raise WorkspacePathError("name_invalid", "session_id 不能为空")
    if len(session_id) > 100:
        raise WorkspacePathError("name_invalid", f"session_id 过长 (>{100} 字符)")
    # 路径分隔符 / 父目录 / NUL
    if "/" in session_id or "\\" in session_id or ".." in session_id or "\x00" in session_id:
        raise WorkspacePathError("name_invalid", f"session_id 含非法字符: {session_id!r}")
    # 控制字符
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in session_id):
        raise WorkspacePathError("name_invalid", "session_id 含控制字符")


def resolve_workspace_path(
    session_id: str,
    raw_path: str,
    *,
    must_exist: bool = True,
    must_be_file: Optional[bool] = None,
    must_be_dir: Optional[bool] = None,
    allow_symlinks: bool = False,
) -> Path:
    """Workspace 路径解析 — 所有工具的唯一入口

    Args:
        session_id: Session ID (已校验过, 这里再校验一次)
        raw_path: LLM 传入的路径 (相对 workspace 的路径)
        must_exist: 目标必须存在
        must_be_file: None=不检查, True=必须是文件, False=必须是目录
        allow_symlinks: 是否允许 symlink 越界

    Returns:
        解析后的绝对 Path (已 resolve, 已 bound 在 workspace 内)

    Raises:
        WorkspacePathError: 各种越界 / 不存在 / 类型不匹配
    """
    validate_session_id(session_id)

    # 1) 空 path
    if not raw_path or not raw_path.strip():
        raise WorkspacePathError("name_invalid", "路径不能为空")

    # 2) 绝对路径检测 (Path.is_absolute 在 Windows 上对 /etc/passwd 返回 False, 需额外查字符串前缀)
    raw = Path(raw_path)
    if raw.is_absolute() or raw_path.startswith("/") or raw_path.startswith("\\"):
        raise WorkspacePathError(
            "absolute", f"Workspace 路径不允许绝对路径: {raw_path!r}"
        )

    # 3) 段级 .. / NUL 防御
    if any(part == ".." for part in raw.parts):
        raise WorkspacePathError(
            "traversal", f"Workspace 路径不允许 '..' 越界: {raw_path!r}"
        )
    if "\x00" in raw_path:
        raise WorkspacePathError("name_invalid", "路径含 NUL 字符")

    # 4) 解析到 workspace 下的真实路径
    workspace = workspace_dir(session_id)
    target = (workspace / raw_path).resolve()
    workspace_resolved = workspace.resolve()

    # 5) 越界检测 (即便 raw 没 .. 段, resolve 之后也可能)
    if not target.is_relative_to(workspace_resolved):
        raise WorkspacePathError(
            "out_of_root", f"路径解析后越出 workspace: {raw_path!r}"
        )

    # 6) symlink 防御
    if not allow_symlinks and target.is_symlink():
        # 进一步: symlink 指向 workspace 内是 ok 的 (因为上面 is_relative_to 已通过)
        # 但保守起见, 沙箱默认拒绝 symlink 走工具, 防 symlink 链多次跳转逃出
        raise WorkspacePathError(
            "symlink", f"Workspace 路径不允许 symlink: {raw_path!r}"
        )

    # 7) 存在性 / 类型校验
    if must_exist and not target.exists():
        raise WorkspacePathError("not_found", f"路径不存在: {raw_path!r}")
    if must_be_file is True and not target.is_file():
        raise WorkspacePathError(
            "not_file", f"路径不是文件: {raw_path!r}"
        )
    if must_be_dir is True and not target.is_dir():
        raise WorkspacePathError(
            "not_dir", f"路径不是目录: {raw_path!r}"
        )

    return target


def to_relative_path(session_id: str, resolved_path: Path) -> str:
    """与 resolve_workspace_path 采用相同的沙箱逻辑，反向校验并返回相对路径字符串。

    Args:
        session_id: Session ID
        resolved_path: 绝对 Path 对象

    Returns:
        相对 workspace 根的 POSIX 路径字符串（使用正斜杠）
    """
    validate_session_id(session_id)
    workspace = workspace_dir(session_id).resolve()
    target = Path(resolved_path).resolve()

    # 越界检测（反向校验）
    if not target.is_relative_to(workspace):
        raise WorkspacePathError(
            "out_of_root", f"目标路径超出沙箱范围，无法输出相对路径: {resolved_path}"
        )

    # 返回相对 POSIX 路径 (例如 "style_profiles/abc.json")
    return target.relative_to(workspace).as_posix()



def safe_workspace_filename(original: str) -> str:
    """清洗上传文件名 — basename 化, 拒绝控制字符, 截断 200 字符

    规则:
    - 取 basename (去掉路径前缀)
    - 拒绝包含 NUL / 控制字符 / '..' / '/' / '\\'
    - 拒绝以 '.' 开头 (隐藏文件)
    - 截断到 MAX_FILENAME_LEN 字符 (保留扩展名)

    Raises:
        WorkspacePathError(code="name_invalid")
    """
    if not original:
        raise WorkspacePathError("name_invalid", "文件名不能为空")

    # basename
    name = os.path.basename(original)
    if not name or name in (".", ".."):
        raise WorkspacePathError("name_invalid", f"文件名不合法: {original!r}")

    # 隐藏文件
    if name.startswith("."):
        raise WorkspacePathError("name_invalid", f"不允许隐藏文件: {name!r}")

    # 控制字符 / 路径分隔符
    if any(c in name for c in ("/", "\\", "\x00")):
        raise WorkspacePathError("name_invalid", f"文件名含路径分隔符: {name!r}")
    if any(ord(c) < 0x20 or ord(c) == 0x7f for c in name):
        raise WorkspacePathError("name_invalid", "文件名含控制字符")

    # 长度截断 (保留扩展名)
    if len(name) > MAX_FILENAME_LEN:
        stem, dot, ext = name.rpartition(".")
        # 没有扩展名 或 扩展名太长 → 直接截断
        if not dot or len(ext) >= MAX_FILENAME_LEN:
            name = name[:MAX_FILENAME_LEN]
        else:
            keep = MAX_FILENAME_LEN - len(ext) - 1  # -1 for the dot
            name = stem[:keep] + "." + ext

    return name


def unique_workspace_target(workspace: Path, desired_name: str) -> Path:
    """重名时返回带 __1 / __2 / ... 后缀的路径

    Args:
        workspace: workspace 目录 (绝对路径)
        desired_name: 期望的文件名 (已 safe_workspace_filename 清洗过)

    Returns:
        不与现有文件冲突的目标路径
    """
    target = workspace / desired_name
    if not target.exists():
        return target

    stem, dot, ext = desired_name.rpartition(".")
    if not dot:
        stem, ext = desired_name, ""

    counter = 1
    while counter < 10000:  # 防止死循环
        if ext:
            candidate_name = f"{stem}__{counter}.{ext}"
        else:
            candidate_name = f"{stem}__{counter}"
        candidate = workspace / candidate_name
        if not candidate.exists():
            return candidate
        counter += 1

    # 极端情况: 10000 个重名都存在, 用时间戳兜底
    import time
    fallback = workspace / f"{stem}_{int(time.time())}{('.' + ext) if ext else ''}"
    return fallback


def build_workspace_tree(
    session_id: str,
    max_depth: int = TREE_DEFAULT_MAX_DEPTH,
    max_files: int = TREE_DEFAULT_MAX_FILES,
) -> List[str]:
    """给 LLM 看的 workspace 文件树 (限制 max_depth / max_files)

    Args:
        session_id: Session ID
        max_depth: 目录递归深度 (默认 2, 防止深目录输出爆炸)
        max_files: 文件总条数上限 (默认 20)

    Returns:
        相对 workspace 的路径列表 (不含绝对路径, 不暴露物理位置)
        空 workspace 返回 []

    Note:
        - 自动忽略隐藏文件 / __pycache__ / .DS_Store
        - 文件超过 max_files 时, 列表末尾追加 "...(还有 N 个文件, 可用 `ls` 查看完整列表)"
    """
    workspace = workspace_dir(session_id)
    if not workspace.exists():
        return []

    lines: List[str] = []
    total_count = 0
    truncated = False

    def _walk(path: Path, rel_parts: List[str], depth: int) -> None:
        nonlocal total_count, truncated
        if truncated:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except (PermissionError, FileNotFoundError):
            return

        for entry in entries:
            if truncated:
                break
            # 过滤隐藏文件 / 系统
            if entry.name.startswith("."):
                continue
            if entry.name == "__pycache__":
                continue
            if entry.name == "node_modules":
                continue

            current_rel = rel_parts + [entry.name]
            current_path = "/".join(current_rel)
            if entry.is_dir():
                lines.append(current_path + "/")
                if depth < max_depth:
                    _walk(entry, current_rel, depth + 1)
            else:
                total_count += 1
                if total_count > max_files:
                    truncated = True
                    break
                lines.append(current_path)

    _walk(workspace, [], 1)

    if truncated:
        remaining = _count_remaining(workspace, max_depth) - max_files
        if remaining > 0:
            lines.append(f"...(还有 {remaining} 个文件, 可用 `ls` 查看完整列表)")

    return lines


def _count_remaining(workspace: Path, max_depth: int) -> int:
    """统计 workspace 内文件总数 (忽略隐藏, 限 max_depth)"""
    count = 0
    base_depth = len(workspace.parts)

    def _walk(path: Path) -> None:
        nonlocal count
        try:
            for entry in path.iterdir():
                if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                    continue
                current_depth = len(entry.resolve().parts) - base_depth
                if current_depth > max_depth:
                    continue
                if entry.is_dir():
                    _walk(entry)
                else:
                    count += 1
        except (PermissionError, FileNotFoundError):
            return

    _walk(workspace)
    return count
