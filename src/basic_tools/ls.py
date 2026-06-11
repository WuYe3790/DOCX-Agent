import json
import sys
from pathlib import Path

# v2: 沙箱化 — 所有路径走 resolve_workspace_path 强制在 session workspace 内
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError, to_relative_path  # noqa: E402


def ls(session_id: str, path: str = ".") -> str:
    """v2: 列出 session workspace 内的文件和子目录, 默认 workspace 根

    session_id 由 dispatcher 隐式注入, LLM 看不到也不需要传
    """
    try:
        p = resolve_workspace_path(session_id, path, must_exist=True, must_be_dir=True)
    except WorkspacePathError as e:
        return json.dumps(
            {"status": "error", "code": e.code, "message": e.user_message},
            ensure_ascii=False, indent=2,
        )

    try:
        entries = []
        for item in p.iterdir():
            entries.append(
                {
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )
        # 按照 目录在前, 文件在后, 并按名称排序
        entries.sort(key=lambda x: (not x["is_dir"], x["name"]))
        return json.dumps(
            {"status": "ok", "path": to_relative_path(session_id, p), "entries": entries},
            ensure_ascii=False, indent=2,
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": str(e)},
            ensure_ascii=False, indent=2,
        )


tools_schema = {
    "type": "function",
    "function": {
        "name": "ls",
        "description": "列出 session workspace 内的文件和子目录, 路径相对 workspace 根。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录路径 (相对 workspace), 默认为 '.' (workspace 根)",
                },
            },
            "required": [],
        },
    },
}
