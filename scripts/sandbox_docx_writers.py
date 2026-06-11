"""临时脚本: 批量给 19 个 docx 写入工具加 session_id + resolver 沙箱

按统一模式改:
- 函数签名加 session_id: str 作为第一个参数
- 函数体顶部加 resolve_docx_io(session_id, docx_path, output_path) 解析
- 把 load_document_xml(docx_path) 替换为 load_document_xml(str(input_path))
- 把 write_document_xml(docx_path, output_path, root) 替换为 write_document_xml(str(input_path), str(output_path_resolved), root)
- 把 json_result 中的 "docx_path": docx_path 替换为 "docx_path": str(input_path)
- 把 json_result 中的 "output_path": output_path 替换为 "output_path": str(output_path_resolved)
- tools_schema 描述里 docx_path/output_path 描述加 "(相对 workspace 根)"

不修改:
- 函数内部 helper (不以 docx_path/output_path 为参数的子函数)
- 已有 session_id 注入的工具 (apply_markdown_ir_*, markdown_to_word, 等)
- tools_schema 里 session_id 字段 (避坑 1)

运行: python scripts/sandbox_docx_writers.py
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


def sandbox_one(tool_name: str) -> bool:
    """给一个工具加 session_id + resolver 沙箱。返回是否修改了文件"""
    path = DOCX_TOOLS_DIR / f"{tool_name}.py"
    if not path.exists():
        print(f"  [skip] {tool_name}.py 不存在")
        return False

    src = path.read_text(encoding="utf-8")
    original = src

    # 1. 在 from .common import 块里加 resolve_docx_io
    #    找到第一行 `from .common import (` 然后加一个导入
    if "resolve_docx_io" not in src:
        # 找到 `from .common import (`
        m = re.search(r"from \.common import \(([^)]+)\)", src, re.DOTALL)
        if m:
            imports = m.group(1)
            # 在已有 import 后追加 resolve_docx_io
            new_imports = imports.rstrip() + "\n    resolve_docx_io,\n"
            src = src[: m.start()] + f"from .common import ({new_imports})" + src[m.end():]
        else:
            # 简单 import
            m2 = re.search(r"from \.common import (.+)", src)
            if m2:
                first_line = m2.group(1).split("\n")[0].rstrip(", ")
                rest = "\n".join(m2.group(1).split("\n")[1:])
                new_imp = f"from .common import {first_line}, resolve_docx_io{',' if rest.strip() else ''}\n{rest}"
                src = src[: m2.start()] + new_imp + src[m2.end():]

    # 2. 找到函数定义: def tool_name(...) -> str:
    #    在第一个参数前加 session_id: str,
    sig_re = re.compile(
        rf"^def {tool_name}\(\s*\n"
        rf"(\s+)(?!session_id)([a-z_]+:)",  # 第二个参数不是 session_id
        re.MULTILINE,
    )
    # 更宽松: 在 `def tool_name(\n    X:` 后插入 session_id
    fn_start_re = re.compile(
        rf"(def {tool_name}\(\s*\n)(\s+)(?!session_id)([a-z_]+:)",
        re.MULTILINE,
    )
    if fn_start_re.search(src):
        src = fn_start_re.sub(
            r"\1\2session_id: str,\n\2\3",
            src,
            count=1,
        )

    # 3. 在函数体顶部 (第一个非空白行前) 加 resolve 块
    #    模式: 找到 "def tool_name(\n    ...):\n\"\"\"...\"\"\"\n    <body_first_line>"
    #    简化为: 在 "    return" 或第一个非空行前插入
    body_open_re = re.compile(
        rf"(def {tool_name}\([^)]*\)[^:]*:\s*\n"
        rf"(?:    \"\"\".*?\"\"\"\s*\n)?)"
        rf"(\s*)([a-zA-Z_])",
        re.MULTILINE | re.DOTALL,
    )
    # 在第一个 body 字符前插入 resolve 调用
    # 用更简单的策略: 找 `    root = load_document_xml(docx_path)` 替换
    # 但很多工具没有这个变量名, 改成更通用:
    # 找 "    try:\n" 或 "    <first_body_line>" 在函数体内

    # 更可靠: 把 load_document_xml(docx_path) 调用替换为 resolve + load
    # 但要先确定 docx_path 在函数签名里
    # 用 ast 解析: 找到 def, 找参数, 找 body 第一个语句

    # 简化为: 在所有 `load_document_xml(docx_path)` 前插入解析
    # 实际上: 在函数体第一个语句前加 2 行 (resolve_docx_io + 解构)
    # 通过找到 "def ... -> ...:\n" 后第一个 "    <indent>" 开头的内容 (4 空格, 字母)

    # 找函数体起始: def 之后第一个 4 空格开头的非 docstring 行
    fn_def_re = re.compile(
        rf"def {tool_name}\([^)]*\)[^:]*:\s*\n"
        rf"(?:    \"\"\"[^\"]*\"\"\"\s*\n)?"
        rf"(\s+)([^\s])",
        re.MULTILINE | re.DOTALL,
    )
    m = fn_def_re.search(src)
    if m:
        indent = m.group(1)
        # 找到的 group(2) 是函数体第一个字符
        # 找整个 match 的结束位置 (group(0) 的末尾)
        insert_pos = m.end() - 1  # 最后一个字符的位置
        # 在这里插入 resolve 块
        resolve_block = (
            f"{indent}input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)\n"
        )
        src = src[:insert_pos] + resolve_block + src[insert_pos:]

    # 4. 替换 load_document_xml(docx_path) → load_document_xml(str(input_path))
    src = re.sub(
        r"load_document_xml\(docx_path\)",
        "load_document_xml(str(input_path))",
        src,
    )

    # 5. 替换 write_document_xml(docx_path, output_path, root) → write_document_xml(str(input_path), str(output_path_resolved), root)
    src = re.sub(
        r"write_document_xml\(docx_path, output_path,",
        "write_document_xml(str(input_path), str(output_path_resolved),",
        src,
    )
    # 有些工具用临时 output_path (中间步骤), 只替换第一参即可
    # 上面的替换已经处理了前两个参数, 第三个参数保持原样

    # 6. json_result 中 docx_path: docx_path → docx_path: str(input_path)
    #    只在 json_result( 调用内
    src = re.sub(
        r'"docx_path": docx_path,',
        '"docx_path": str(input_path),',
        src,
    )
    src = re.sub(
        r'"docx_path": docx_path\n',
        '"docx_path": str(input_path)\n',
        src,
    )
    # status not_found 的也替换
    src = re.sub(
        r'"docx_path": docx_path\}',
        '"docx_path": str(input_path)}',
        src,
    )
    # 单引号变体
    src = re.sub(
        r"'docx_path': docx_path",
        "'docx_path': str(input_path)",
        src,
    )

    # 7. output_path: output_path → output_path: str(output_path_resolved)
    src = re.sub(
        r'"output_path": output_path,',
        '"output_path": str(output_path_resolved),',
        src,
    )
    src = re.sub(
        r'"output_path": output_path\n',
        '"output_path": str(output_path_resolved)\n',
        src,
    )

    # 8. tools_schema 描述加 "(相对 workspace 根)"
    src = re.sub(
        r'"description": "输入 \.docx 文件路径"',
        '"description": "输入 .docx 文件路径 (相对 workspace 根)"',
        src,
    )
    src = re.sub(
        r'"description": "输出 \.docx 文件路径"',
        '"description": "输出 .docx 文件路径 (相对 workspace 根)"',
        src,
    )

    if src != original:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main():
    print(f"将处理 {len(DOCX_TOOLS)} 个 docx 写入工具")
    changed = 0
    for name in DOCX_TOOLS:
        if sandbox_one(name):
            print(f"  [ok] {name}")
            changed += 1
        else:
            print(f"  [--] {name} (无需修改)")
    print(f"\n完成: {changed}/{len(DOCX_TOOLS)} 个工具被修改")


if __name__ == "__main__":
    main()
