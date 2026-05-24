import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.docx_tools.diff_docx import diff_docx

cases = [
    ("insert_text_001", "实验报告模板_v3_insert_text_001.docx", "实验报告模板_v3修改蓝色部分即可.docx"),
    ("edit_text_002", "实验报告模板_v3_edit_text_002.docx", "实验报告模板_v3修改蓝色部分即可.docx"),
    ("format_text_003", "实验报告模板_v3_format_text_003.docx", "实验报告模板_v3修改蓝色部分即可.docx"),
    ("table_edit_004", "实验报告10_table_edit_004.docx", "实验报告10.docx"),
    ("text_layout_005", "实验报告模板_v3_text_layout_005.docx", "实验报告模板_v3修改蓝色部分即可.docx"),
    ("create_table_006", "实验报告10_create_table_006.docx", "实验报告10.docx"),
    ("insert_image_007", "实验报告模板_v3_insert_image_007.docx", "实验报告模板_v3修改蓝色部分即可.docx")
]

for name, target, template in cases:
    print(f"\n==================== Case: {name} ====================")
    before_path = f"文档格式测试/{template}"
    if "实验报告10" in template:
        # Check if baseline unzipped was used
        before_path = f"文档格式测试/{template}"
    
    after_path = f"文档格式测试/cases/{name}/docx/{target}"
    
    res = diff_docx(before_path, after_path)
    import json
    data = json.loads(res)
    print("Paragraph changes:")
    for change in data.get("paragraph_changes", []):
        print(f"Para {change['paragraph_index']}:")
        print(f"  - Before: {change['before']}")
        print(f"  - After:  {change['after']}")
