import json
from pathlib import Path


def ls(path: str = ".") -> str:
    """列出指定目录下的文件和子目录，便于在大模型找不到文件时查找正确路径。"""
    p = Path(path)
    if not p.exists():
        return json.dumps(
            {"status": "error", "message": f"Path not found: {path}"},
            ensure_ascii=False,
            indent=2,
        )
    if not p.is_dir():
        return json.dumps(
            {"status": "error", "message": f"Path is not a directory: {path}"},
            ensure_ascii=False,
            indent=2,
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
        # 按照 目录在前，文件在后，并按名称排序
        entries.sort(key=lambda x: (not x["is_dir"], x["name"]))
        return json.dumps(
            {"status": "ok", "path": str(p.absolute()), "entries": entries},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": str(e)},
            ensure_ascii=False,
            indent=2,
        )


tools_schema = {
    "type": "function",
    "function": {
        "name": "ls",
        "description": "列出指定目录下的文件和子目录，便于在找不到文件时，定位正确的文件路径。",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要列出的目录路径，默认为当前工作目录 '.'",
                },
            },
            "required": [],
        },
    },
}
