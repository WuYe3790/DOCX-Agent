import shutil
import zipfile
from pathlib import Path

from .common import json_result


def unzip_docx(docx_path: str, output_dir: str, overwrite: bool = False) -> str:
    """解包 docx，方便查看 OpenXML 源码。"""
    target = Path(output_dir)
    if target.exists():
        if not overwrite:
            return json_result({"status": "error", "message": "output_dir already exists", "output_dir": output_dir})
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(docx_path, "r") as docx:
        docx.extractall(target)

    file_count = sum(1 for p in target.rglob("*") if p.is_file())
    return json_result({"status": "ok", "docx_path": docx_path, "output_dir": output_dir, "file_count": file_count})


tools_schema = {
    "type": "function",
    "function": {
        "name": "unzip_docx",
        "description": "把 .docx 解包到目录，便于查看 OpenXML 源码。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_dir": {"type": "string", "description": "解包目标目录"},
                "overwrite": {"type": "boolean", "description": "目标目录存在时是否删除重建，默认 false"},
            },
            "required": ["docx_path", "output_dir"],
        },
    },
}
