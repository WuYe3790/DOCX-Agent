"""test_insert_image_after_paragraph.py — 6 case (PR-2.2)

insert_image_after_paragraph 工具:
  - 用 PIL 读 image_path 的宽高算 aspect ratio
  - 默认 10cm 宽 (3810000 EMU)
  - 写 <w:drawing> 进新段落插在锚点段后
  - 用 anchor_text + paragraph_index 双重校验

关键: 工具用 PIL 读图, 测试要构造真 PNG (8x8 RGB) 喂进去.
"""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

pytest_plugins = ["_docx_factory"]
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_tools.insert_image_after_paragraph import insert_image_after_paragraph

from _docx_factory import (
    _build_full_docx,
    get_xml_elements,
)


def _ws(tmp_root, session_id: str) -> Path:
    return tmp_root / session_id / "workspace"


def _make_png(path: Path, width: int = 10, height: int = 10, color: str = "red") -> Path:
    """构造真 PNG (PIL 写出), 工具用 PIL 打开验证."""
    Image.new("RGB", (width, height), color=color).save(path)
    return path


# =====================================================================
# 6 case
# 注意: 工具要写 word/_rels/document.xml.rels, 必须用 _build_full_docx
# (含 rels), 不能用 _build_minimal_docx (只写 document.xml)
# =====================================================================

class TestInsertImageAfterParagraph:
    def test_basic_insert_creates_drawing(self, tmp_root, session_id):
        """基本插入: 输出 docx 含 <w:drawing> 元素, 锚点段后多 1 段."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx",
                         ["anchor text", "second"])
        img = _make_png(_ws(tmp_root, session_id) / "test.png")
        out = _ws(tmp_root, session_id) / "out.docx"

        result = json.loads(insert_image_after_paragraph(
            session_id, "in.docx", "out.docx",
            image_path=str(img),
            paragraph_index=1, anchor_text="anchor",
        ))

        assert result["status"] == "ok"
        # 输出 docx 应有 <w:drawing> 节点
        drawings = get_xml_elements(out, "//w:drawing")
        assert len(drawings) >= 1, "输出 docx 应含 <w:drawing> 节点"
        # 段数 +1
        paras = get_xml_elements(out, "//w:p")
        assert len(paras) == 3

    def test_default_size_is_10cm_width(self, tmp_root, session_id):
        """默认 width_emu = 3810000 (10 cm * 360000 EMU/cm)."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        img = _make_png(_ws(tmp_root, session_id) / "test.png", 10, 10)

        result = json.loads(insert_image_after_paragraph(
            session_id, "in.docx", "out.docx",
            image_path=str(img),
            paragraph_index=1, anchor_text="anchor",
        ))

        assert result["status"] == "ok"
        assert result["width_emu"] == 3810000, f"默认宽度应是 3810000 EMU (10cm), 实际 {result['width_emu']}"
        # 1:1 长宽比, height_emu 应也是 3810000
        assert result["height_emu"] == 3810000

    def test_explicit_width_cm_overrides_default(self, tmp_root, session_id):
        """width_cm=5 → width_emu = 5 * 360000 = 1800000."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        img = _make_png(_ws(tmp_root, session_id) / "test.png", 10, 10)

        result = json.loads(insert_image_after_paragraph(
            session_id, "in.docx", "out.docx",
            image_path=str(img),
            paragraph_index=1, anchor_text="anchor",
            width_cm=5.0,
        ))

        assert result["status"] == "ok"
        assert result["width_emu"] == 1800000, f"5cm 宽应是 1800000 EMU, 实际 {result['width_emu']}"

    def test_image_not_found_returns_error(self, tmp_root, session_id):
        """image_path 不存在 → status=error, 友好 message.

        工具在加载 docx 之前就检查 image_path, 所以 docx 是不是 full 都不影响.
        """
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        result = json.loads(insert_image_after_paragraph(
            session_id, "in.docx", "out.docx",
            image_path="nonexistent.png",
            paragraph_index=1, anchor_text="anchor",
        ))
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_anchor_text_mismatch_returns_error(self, tmp_root, session_id):
        """锚点段不含 anchor_text → status=error."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        img = _make_png(_ws(tmp_root, session_id) / "test.png")
        result = json.loads(insert_image_after_paragraph(
            session_id, "in.docx", "out.docx",
            image_path=str(img),
            paragraph_index=1, anchor_text="WRONG_TEXT",
        ))
        assert result["status"] == "error"
        assert "Anchor text verification failed" in result["message"]

    def test_paragraph_index_out_of_range(self, tmp_root, session_id):
        """paragraph_index 越界 → status=error."""
        _build_full_docx(_ws(tmp_root, session_id) / "in.docx", ["anchor"])
        img = _make_png(_ws(tmp_root, session_id) / "test.png")
        result = json.loads(insert_image_after_paragraph(
            session_id, "in.docx", "out.docx",
            image_path=str(img),
            paragraph_index=99, anchor_text="anchor",
        ))
        assert result["status"] == "error"
        assert "paragraph_index out of range" in result["message"]
