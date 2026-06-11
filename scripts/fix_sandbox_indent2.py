"""第二轮修复: 找出 resolve_docx_io 后的 0 缩进 body 行, 改成 4 缩进

模式 (bug):
    "    input_path, output_path_resolved = resolve_docx_io(...)
root = load_document_xml(str(input_path))   <- 0 缩进, 错
style_sample = load_style_sample(...)       <- 0 缩进, 错
    try:

应该是:
    "    input_path, output_path_resolved = resolve_docx_io(...)
    root = load_document_xml(str(input_path))   <- 4 缩进, 对
    style_sample = load_style_sample(...)       <- 4 缩进, 对
    try:
"""
import re
from pathlib import Path

DOCX_TOOLS_DIR = Path("src/docx_tools")


def fix_one(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    original = src
    lines = src.split("\n")
    out = []
    in_resolve_block = False  # 在 resolve 调用之后
    fixed_count = 0

    for i, line in enumerate(lines):
        if re.match(r"^    input_path, output_path_resolved = resolve_docx_io", line):
            # 这行 OK, 标记 in_resolve_block = True
            in_resolve_block = True
            out.append(line)
            continue

        if in_resolve_block:
            # 0 缩进的 body 行, 需要 4 缩进
            # 排除特殊行: 空行, `"""`, `def`, `class`, `from`, `import`, `@`, `#`
            if (line and not line.startswith(" ") and not line.startswith("#")
                and not line.startswith("def ") and not line.startswith("class ")
                and not line.startswith("from ") and not line.startswith("import ")
                and not line.startswith("@") and not line.startswith("tools_schema")
                and not line.startswith("}")):
                # 是 body 0 缩进行, 加 4 空格
                out.append("    " + line)
                fixed_count += 1
                continue
            # 否则: 退出 resolve 块 (因为正常行有 4 缩进了)
            if line.startswith("    "):
                in_resolve_block = False

        out.append(line)

    if fixed_count:
        path.write_text("\n".join(out), encoding="utf-8")
        print(f"  [ok] {path.name}: 修复 {fixed_count} 行")
        return True
    return False


def main():
    changed = 0
    for p in sorted(DOCX_TOOLS_DIR.glob("*.py")):
        if p.name in ("common.py", "registry.py", "__init__.py"):
            continue
        if fix_one(p):
            changed += 1
    print(f"\n完成: {changed} 个文件被修复")


if __name__ == "__main__":
    main()
