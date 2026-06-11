import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import resolve_workspace_path, WorkspacePathError

from .common import file_sha256, json_result, load_document_xml, paragraph_text, paragraphs


def diff_docx(session_id: str, before_docx: str, after_docx: str, marker_prefix: str = "") -> str:
    """v2: 对比 session workspace 内的两个 docx (沙箱化)"""
    try:
        before_path = resolve_workspace_path(session_id, before_docx, must_exist=True, must_be_file=True)
        after_path = resolve_workspace_path(session_id, after_docx, must_exist=True, must_be_file=True)
    except WorkspacePathError as e:
        return json_result({"status": "error", "code": e.code, "message": e.user_message})
    before_files = _zip_file_map(str(before_path))
    after_files = _zip_file_map(str(after_path))
    all_names = sorted(set(before_files) | set(after_files))

    changed_files = []
    for name in all_names:
        if name not in before_files:
            changed_files.append({"path": name, "status": "added", "before_size": 0, "after_size": after_files[name]})
        elif name not in after_files:
            changed_files.append({"path": name, "status": "removed", "before_size": before_files[name], "after_size": 0})
        else:
            before_hash = _zip_member_hash(str(before_path), name)
            after_hash = _zip_member_hash(str(after_path), name)
            if before_hash != after_hash:
                changed_files.append(
                    {
                        "path": name,
                        "status": "changed",
                        "before_size": before_files[name],
                        "after_size": after_files[name],
                        "delta": after_files[name] - before_files[name],
                    }
                )

    before_texts = _paragraph_texts(str(before_path))
    after_texts = _paragraph_texts(str(after_path))
    paragraph_changes = []
    for i in range(max(len(before_texts), len(after_texts))):
        before = before_texts[i] if i < len(before_texts) else ""
        after = after_texts[i] if i < len(after_texts) else ""
        if before != after:
            item = {"paragraph_index": i + 1, "before": before, "after": after}
            if marker_prefix and marker_prefix in after:
                item["contains_marker"] = True
            paragraph_changes.append(item)

    return json_result(
        {
            "before_docx": str(before_path),
            "after_docx": str(after_path),
            "changed_files": changed_files,
            "paragraph_changes": paragraph_changes[:100],
            "notes": [
                "纯文本编辑通常只有 word/document.xml 是业务核心变化。",
                "docProps、settings、styles、fontTable、footnotes、endnotes、footer 等文件可能因为 Office 保存而产生噪声变化。",
            ],
        }
    )


def _zip_file_map(docx_path: str):
    with zipfile.ZipFile(docx_path, "r") as docx:
        return {info.filename: info.file_size for info in docx.infolist() if not info.is_dir()}


def _zip_member_hash(docx_path: str, name: str):
    with zipfile.ZipFile(docx_path, "r") as docx:
        data = docx.read(name)
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        temp_path = Path(f.name)
    try:
        return file_sha256(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _paragraph_texts(docx_path: str):
    root = load_document_xml(docx_path)
    return [paragraph_text(p) for p in paragraphs(root)]


tools_schema = {
    "type": "function",
    "function": {
        "name": "diff_docx",
        "description": "对比 session workspace 内的两个 docx 包，返回变更文件列表和段落文本变化摘要。",
        "parameters": {
            "type": "object",
            "properties": {
                "before_docx": {"type": "string", "description": "编辑前 .docx 文件路径 (相对 workspace 根)"},
                "after_docx": {"type": "string", "description": "编辑后 .docx 文件路径 (相对 workspace 根)"},
                "marker_prefix": {"type": "string", "description": "可选，用于标记插入文本的前缀"},
            },
            "required": ["before_docx", "after_docx"],
        },
    },
}
