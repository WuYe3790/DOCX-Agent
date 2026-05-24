import random
from pathlib import Path
from lxml import etree
from PIL import Image

from .common import (
    json_result,
    load_document_xml,
    paragraph_location,
    paragraph_text,
    paragraphs,
    write_document_xml,
)


def insert_image_after_paragraph(
    docx_path: str,
    output_path: str,
    image_path: str,
    paragraph_index: int,
    anchor_text: str,
    width_cm: float | None = None,
    height_cm: float | None = None,
) -> str:
    """在指定的锚点段落（通过索引和文本双重校验定位）下方插入本地图片。"""
    # 1. 校验本地图片文件是否存在
    img_file_path = Path(image_path)
    if not img_file_path.exists():
        return json_result(
            {
                "status": "error",
                "message": f"image_path not found: '{image_path}'"
            }
        )

    # 2. 读取图片宽高，计算纵横比
    try:
        with Image.open(img_file_path) as img:
            img_w, img_h = img.size
    except Exception as exc:
        return json_result(
            {
                "status": "error",
                "message": f"Failed to load image file '{image_path}': {exc}"
            }
        )

    aspect_ratio = img_w / img_h

    # 3. 计算 EMU 显示尺寸
    # Word 中尺寸使用 EMU (1 英寸 = 914400 EMU, 1 厘米 = 360000 EMU)
    # 默认宽度设定为 10cm
    width_emu = 3810000
    height_emu = int(width_emu / aspect_ratio)

    if width_cm is not None:
        width_emu = int(width_cm * 360000)
        if height_cm is None:
            height_emu = int(width_emu / aspect_ratio)
    if height_cm is not None:
        height_emu = int(height_cm * 360000)
        if width_cm is None:
            width_emu = int(height_emu * aspect_ratio)

    # 4. 解析并定位 Word XML 正文
    root = load_document_xml(docx_path)
    paragraph_list = list(paragraphs(root))

    index = int(paragraph_index)
    if index < 1 or index > len(paragraph_list):
        return json_result(
            {
                "status": "error",
                "message": f"paragraph_index out of range: {index}, paragraph_count={len(paragraph_list)}"
            }
        )

    anchor = paragraph_list[index - 1]
    para_text = paragraph_text(anchor)
    if anchor_text not in para_text:
        return json_result(
            {
                "status": "error",
                "message": (
                    f"Anchor text verification failed. Paragraph at index {index} "
                    f"does not contain the expected anchor text '{anchor_text}'. "
                    f"Actual text: '{para_text}'"
                )
            }
        )

    # 5. 构建插入段落中的 <w:drawing> 树，使用临时占位符
    unique_id = str(random.randint(100000, 999999999))
    resolved_image_path = str(img_file_path.resolve())
    temp_rId = f"TEMP_IMG_REL:{resolved_image_path}"

    drawing_xml = f"""<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
         xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
         xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
         xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
         xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
      <w:pPr>
        <w:jc w:val="center"/>
      </w:pPr>
      <w:r>
        <w:rPr>
          <w:noProof/>
        </w:rPr>
        <w:drawing>
          <wp:inline distT="0" distB="0" distL="0" distR="0">
            <wp:extent cx="{width_emu}" cy="{height_emu}"/>
            <wp:effectExtent l="0" t="0" r="0" b="0"/>
            <wp:docPr id="{unique_id}" name="图片 {unique_id}"/>
            <wp:cNvGraphicFramePr>
              <a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>
            </wp:cNvGraphicFramePr>
            <a:graphic>
              <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
                <pic:pic>
                  <pic:nvPicPr>
                    <pic:cNvPr id="{unique_id}" name="图片 {unique_id}"/>
                    <pic:cNvPicPr/>
                  </pic:nvPicPr>
                  <pic:blipFill>
                    <a:blip r:embed="{temp_rId}"/>
                    <a:stretch>
                      <a:fillRect/>
                    </a:stretch>
                  </pic:blipFill>
                  <pic:spPr>
                    <a:xfrm>
                      <a:off x="0" y="0"/>
                      <a:ext cx="{width_emu}" cy="{height_emu}"/>
                    </a:xfrm>
                    <a:prstGeom prst="rect">
                      <a:avLst/>
                    </a:prstGeom>
                  </pic:spPr>
                </pic:pic>
              </a:graphicData>
            </a:graphic>
          </wp:inline>
        </w:drawing>
      </w:r>
    </w:p>"""
    new_para = etree.fromstring(drawing_xml.encode("utf-8"))

    # 插入到锚点段落之后
    anchor.addnext(new_para)

    # 6. 使用 write_document_xml 处理所有关系并写回 ZIP
    try:
        write_document_xml(docx_path, output_path, root)
    except Exception as exc:
        return json_result(
            {
                "status": "error",
                "message": f"Failed to repackage and write document XML: {exc}"
            }
        )

    return json_result(
        {
            "status": "ok",
            "docx_path": docx_path,
            "output_path": output_path,
            "image_path": image_path,
            "paragraph_index": index,
            "anchor_text": anchor_text,
            "location": paragraph_location(anchor),
            "width_emu": width_emu,
            "height_emu": height_emu,
        }
    )


tools_schema = {
    "type": "function",
    "function": {
        "name": "insert_image_after_paragraph",
        "description": "在指定的锚点段落后插入本地图片，并更新关系链、文件类型映射与图片二进制资源。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径"},
                "output_path": {"type": "string", "description": "输出 .docx 文件路径"},
                "image_path": {"type": "string", "description": "待插入的本地图片文件路径，如 out/media/chart.png"},
                "paragraph_index": {"type": "integer", "description": "锚点段落的 1-based 索引"},
                "anchor_text": {"type": "string", "description": "锚点段落预期包含的文本，用于双重校验"},
                "width_cm": {"type": "number", "description": "可选，插入图片的显示宽度（厘米）"},
                "height_cm": {"type": "number", "description": "可选，插入图片的显示高度（厘米）"},
            },
            "required": [
                "docx_path",
                "output_path",
                "image_path",
                "paragraph_index",
                "anchor_text",
            ],
        },
    },
}
