import json
import sys
from pathlib import Path

# v2: 沙箱化
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError, to_relative_path  # noqa: E402

MAX_FILE_SIZE = 10 * 1024 * 1024
DEFAULT_LIMIT = 2000
BINARY_CHECK_BYTES = 1024

BOM_MAP = {
    b"\xef\xbb\xbf": "utf-8-sig",
    b"\xff\xfe": "utf-16-le",
    b"\xfe\xff": "utf-16-be",
}

FALLBACK_ENCODINGS = ["utf-8", "gbk"]


def _detect_encoding(raw: bytes) -> tuple:
    for bom_bytes, encoding in BOM_MAP.items():
        if raw.startswith(bom_bytes):
            return encoding, raw[len(bom_bytes):]
    return None, raw


def _decode_content(raw: bytes) -> tuple:
    encoding, payload = _detect_encoding(raw)
    if encoding:
        try:
            return payload.decode(encoding.replace("-sig", "")), encoding
        except UnicodeDecodeError:
            pass

    for enc in FALLBACK_ENCODINGS:
        try:
            return payload.decode(enc), enc
        except UnicodeDecodeError:
            continue

    return payload.decode("utf-8", errors="replace"), "utf-8(replace)"


def read(session_id: str, file_path: str, offset: int = 0, limit: int = -1) -> str:
    """v2: 读 session workspace 内的文件, 路径走沙箱校验"""
    try:
        p = resolve_workspace_path(session_id, file_path, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        return json.dumps(
            {"status": "error", "code": e.code, "message": e.user_message},
            ensure_ascii=False, indent=2,
        )

    file_size = p.stat().st_size
    if file_size > MAX_FILE_SIZE:
        return json.dumps(
            {
                "status": "error",
                "message": f"File too large ({file_size} bytes, max {MAX_FILE_SIZE}). Use offset/limit to read smaller segments.",
            },
            ensure_ascii=False, indent=2,
        )

    with open(p, "rb") as f:
        head = f.read(BINARY_CHECK_BYTES)

    if b"\x00" in head:
        return json.dumps(
            {"status": "error", "message": f"File appears to be binary: {file_path}"},
            ensure_ascii=False, indent=2,
        )

    text, encoding = _decode_content(open(p, "rb").read())

    lines = text.split("\n")
    total_lines = len(lines)

    line_offset = max(0, offset)
    if line_offset >= total_lines:
        return json.dumps(
            {
                "status": "ok",
                "file_path": to_relative_path(session_id, p),
                "encoding": encoding,
                "total_lines": total_lines,
                "offset": line_offset,
                "limit": 0,
                "truncated": False,
                "content": "",
            },
            ensure_ascii=False, indent=2,
        )

    if limit > 0:
        line_limit = limit
    else:
        line_limit = min(DEFAULT_LIMIT, total_lines - line_offset)

    end = min(line_offset + line_limit, total_lines)
    sliced = lines[line_offset:end]
    truncated = end < total_lines

    return json.dumps(
        {
            "status": "ok",
            "file_path": to_relative_path(session_id, p),
            "encoding": encoding,
            "total_lines": total_lines,
            "offset": line_offset,
            "limit": len(sliced),
            "truncated": truncated,
            "content": "\n".join(sliced),
        },
        ensure_ascii=False, indent=2,
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "read",
        "description": "读取 session workspace 内的文本/Markdown 文件。路径相对 workspace 根, 不允许越界。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径 (相对 workspace 根)",
                },
                "offset": {
                    "type": "integer",
                    "description": "从第几行开始读取 (0 表示第一行), 默认 0",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多读取行数, 默认 -1 表示自动截断 (上限 2000 行)",
                },
            },
            "required": ["file_path"],
        },
    },
}
