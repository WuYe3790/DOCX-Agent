import zipfile
from pathlib import Path
import random
from lxml import etree
from PIL import Image

from .common import (
    json_result,
    load_document_xml,
    paragraph_location,
    paragraph_text,
    paragraphs,
)

RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


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

    # 5. 从 docx ZIP 读取并解析关系链 (document.xml.rels) 和内容类型 ([Content_Types].xml)
    try:
        with zipfile.ZipFile(docx_path, "r") as z:
            rels_bytes = z.read("word/_rels/document.xml.rels")
            content_types_bytes = z.read("[Content_Types].xml")
    except Exception as exc:
        return json_result(
            {
                "status": "error",
                "message": f"Failed to read package manifest files from docx: {exc}"
            }
        )

    rels_root = etree.fromstring(rels_bytes)
    content_types_root = etree.fromstring(content_types_bytes)

    # 6. 计算新的 Relationship ID 和递增的图片资源文件名
    max_rId_num = 0
    max_img_num = 0

    for rel in rels_root.xpath("//*[local-name()='Relationship']"):
        r_id = rel.get("Id", "")
        if r_id.startswith("rId"):
            try:
                num = int(r_id[3:])
                if num > max_rId_num:
                    max_rId_num = num
            except ValueError:
                pass

        target = rel.get("Target", "")
        if target.startswith("media/image"):
            # Target 格式通常为: media/image1.png 或 media/image2.jpeg
            name_part = target[11:]
            parts = name_part.split(".")
            if parts:
                try:
                    num = int(parts[0])
                    if num > max_img_num:
                        max_img_num = num
                except ValueError:
                    pass

    new_rId = f"rId{max_rId_num + 1}"
    image_ext = img_file_path.suffix.lower().lstrip(".")
    if not image_ext:
        image_ext = "png"
    if image_ext == "jpg":
        image_ext = "jpeg"

    new_image_name = f"image{max_img_num + 1}.{image_ext}"
    new_target = f"media/{new_image_name}"

    # 7. 在关系链中注册新的 Relationship
    new_rel = etree.Element(
        f"{{{RELS_NS}}}Relationship",
        Id=new_rId,
        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
        Target=new_target
    )
    rels_root.append(new_rel)

    # 8. 在内容类型中注册图片格式 (如果原文档中未注册该扩展名)
    ext_declared = False
    for default in content_types_root.xpath("//*[local-name()='Default']"):
        if default.get("Extension", "").lower() == image_ext:
            ext_declared = True
            break

    if not ext_declared:
        mime_type = "image/png" if image_ext == "png" else "image/jpeg"
        new_default = etree.Element(
            f"{{{TYPES_NS}}}Default",
            Extension=image_ext,
            ContentType=mime_type
        )
        defaults = content_types_root.xpath("//*[local-name()='Default']")
        if defaults:
            defaults[-1].addnext(new_default)
        else:
            content_types_root.append(new_default)

    # 9. 构建插入段落中的 <w:drawing> 树
    unique_id = str(random.randint(100000, 999999999))
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
                    <a:blip r:embed="{new_rId}"/>
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

    # 10. 写回输出 ZIP 文件并注入媒体文件
    document_xml_bytes = etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )
    rels_xml_bytes = etree.tostring(
        rels_root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )
    content_types_xml_bytes = etree.tostring(
        content_types_root,
        encoding="UTF-8",
        xml_declaration=True,
        standalone=True,
    )

    output_file_path = Path(output_path)
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(docx_path, "r") as zin:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename == "word/document.xml":
                        zout.writestr(item, document_xml_bytes)
                    elif item.filename == "word/_rels/document.xml.rels":
                        zout.writestr(item, rels_xml_bytes)
                    elif item.filename == "[Content_Types].xml":
                        zout.writestr(item, content_types_xml_bytes)
                    else:
                        zout.writestr(item, zin.read(item.filename))

                # 拷贝新图片至 zip 包的 word/media 目录中
                with open(img_file_path, "rb") as f_img:
                    zout.writestr(f"word/{new_target}", f_img.read())
    except Exception as exc:
        return json_result(
            {
                "status": "error",
                "message": f"Failed to repackage docx output zip: {exc}"
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
            "new_rId": new_rId,
            "new_image_name": new_image_name,
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
