"""修复 sandbox_docx_writers.py 留下的缩进 bug

bug 模式 (resolve 调用错位到 docstring 内, load 调用缩进 0):
    '\"\"\"'
        input_path, output_path_resolved = resolve_docx_io(...)
root = load_document_xml(str(input_path))
    try:

应该是:
    '\"\"\"'
    input_path, output_path_resolved = resolve_docx_io(...)
    root = load_document_xml(str(input_path))
    try:
"""
import re
from pathlib import Path

DOCX_TOOLS = [
    "insert_text_at",
    "insert_text_in_table_cell",
    "insert_table_row_after",
    "set_paragraph_indent",
    "insert_table_after_paragraph",
    "insert_table_in_cell",
    "insert_table_column_after",
    "merge_table_cells_horizontal",
    "clear_table_cell",
    "delete_table_row",
    "replace_table_cell_text",
    "replace_text",
    "delete_text",
    "insert_paragraph_after",
    "set_text_format",
    "replace_text_like_sample",
    "insert_paragraph_after_like_sample",
    "replace_table_cell_like_sample",
    "insert_image_after_paragraph",
]

DOCX_TOOLS_DIR = Path("src/docx_tools")


def fix_one(tool_name: str) -> bool:
    path = DOCX_TOOLS_DIR / f"{tool_name}.py"
    if not path.exists():
        return False
    src = path.read_text(encoding="utf-8")
    original = src

    # 1. 修复 `        input_path, output_path_resolved = ...` (8 空格) -> 4 空格
    src = re.sub(
        r"^        input_path, output_path_resolved = resolve_docx_io",
        "    input_path, output_path_resolved = resolve_docx_io",
        src,
        flags=re.MULTILINE,
    )

    # 2. 修复 `root = load_document_xml(str(input_path))` (0 空格) -> 4 空格
    src = re.sub(
        r"^root = load_document_xml\(str\(input_path\)\)",
        "    root = load_document_xml(str(input_path))",
        src,
        flags=re.MULTILINE,
    )

    if src != original:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main():
    print(f"将修复 {len(DOCX_TOOLS)} 个 docx 写入工具的缩进 bug")
    changed = 0
    for name in DOCX_TOOLS:
        if fix_one(name):
            print(f"  [ok] {name}")
            changed += 1
        else:
            print(f"  [--] {name} (无需修复)")
    print(f"\n完成: {changed}/{len(DOCX_TOOLS)} 个工具被修复")


if __name__ == "__main__":
    main()
