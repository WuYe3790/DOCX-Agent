from docx_compiler.table_ops import set_paragraph_indent_op

from .common import json_result


def set_paragraph_indent(
    docx_path: str,
    output_path: str,
    paragraph_index: int,
    left_twips: int | None = None,
    first_line_twips: int | None = None,
    hanging_twips: int | None = None,
) -> str:
    """设置指定段落的左缩进、首行缩进或悬挂缩进。"""
    try:
        result = set_paragraph_indent_op(
            docx_path=docx_path,
            output_path=output_path,
            paragraph_index=paragraph_index,
            left_twips=left_twips,
            first_line_twips=first_line_twips,
            hanging_twips=hanging_twips,
        )
    except (IndexError, ValueError) as exc:
        return json_result({"status": "error", "message": str(exc)})
    return json_result({"status": "ok", **result})


tools_schema = {
    "type": "function",
    "function": {
        "name": "set_paragraph_indent",
        "description": "设置指定段落的 <w:ind> 缩进属性，支持左缩进、首行缩进和悬挂缩进，单位 twips。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "paragraph_index": {"type": "integer", "description": "第几个段落，按 //w:p 计数，1-based"},
                "left_twips": {"type": "integer", "description": "左缩进，单位 twips；720 表示 0.5 英寸"},
                "first_line_twips": {"type": "integer", "description": "首行缩进，单位 twips"},
                "hanging_twips": {"type": "integer", "description": "悬挂缩进，单位 twips"},
            },
            "required": ["docx_path", "output_path", "paragraph_index"],
        },
    },
}
