"""端到端测试: markdown 相对图片路径 → DOCX zip 内图片字节注入

修复前 → 测试必然失败:
  lower 把 "media/foo.png" 原样写入 ImageIR.src_path
  → render_image 用 Path(src_path).resolve() 基于 CWD 拼错绝对路径
  → write_document_xml 的 open() 读不到, if local_path.exists() 静默跳过
  → 输出 zip 里没有 word/media/imageN.png

修复后 → 测试必然通过:
  lower 在 _resolve_image_path 里用 resolve_workspace_path 转成 workspace 绝对路径
  → render_image 用 .resolve() 是 idempotent 操作, sentinel 内塞的就是真绝对路径
  → write_document_xml 的 open() 能读到字节, 注入 word/media/imageN.png
"""
import sys
import zipfile
from pathlib import Path

import pytest

# tests/ 是子目录, src/ 在仓库根
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_compiler.lower import lower_markdown_blocks  # noqa: E402
from docx_compiler.markdown_parser import parse_markdown_blocks  # noqa: E402
from docx_compiler.ir import ImageIR  # noqa: E402
from docx_compiler.render import render_image  # noqa: E402
from docx_tools.common import load_document_xml, write_document_xml  # noqa: E402


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# 最小合法 PNG (8 字节 magic + 占位)
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_FAKE_PNG = _PNG_MAGIC + b"\x00" * 64


@pytest.fixture
def tmp_root(monkeypatch, tmp_path):
    """重定向 WORKSPACE_ROOT 到 tmp_path/sessions, 沿用 test_render_diagram.py 的模式。"""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    import workspace.guard as guard
    monkeypatch.setattr(guard, "WORKSPACE_ROOT", sessions)
    return sessions


@pytest.fixture
def session_id(tmp_root):
    sid = "sess-md2docx-image-e2e"
    from workspace.guard import workspace_dir
    workspace_dir(sid)  # 触发 mkdir
    return sid


@pytest.fixture
def baseline_docx() -> Path:
    """仓库内现成的最干净 docx 模板, 用作 write_document_xml 的输入容器。"""
    repo_root = Path(__file__).parent.parent
    candidate = repo_root / "文档格式测试" / "cases" / "baseline" / "docx" / "实验报告模板_v3修改蓝色部分即可.docx"
    if not candidate.exists():
        pytest.skip(f"baseline docx 缺失: {candidate}")
    return candidate


def test_markdown_image_relative_path_writes_into_docx(session_id, tmp_root, baseline_docx):
    """完整链路: md ![](media/foo.png) → lower → render → write_document_xml → 校验 zip 字节"""
    from workspace.guard import workspace_dir
    workspace = workspace_dir(session_id)

    # 1) 在 workspace 内放一张 PNG, 模拟 generate_image / render_diagram 的产物落地位置
    media_dir = workspace / "media"
    media_dir.mkdir()
    png_path = media_dir / "test.png"
    png_path.write_bytes(_FAKE_PNG)

    # 2) markdown 写相对路径 (跟 LLM 实际行为一致)
    md_text = "![alt](media/test.png)\n"
    blocks = parse_markdown_blocks(md_text)
    lowering = lower_markdown_blocks(
        blocks,
        style_mapping={"image": "S001", "paragraph": "S001"},
        session_id=session_id,
    )
    image_irs = [b for b in lowering.layout_blocks if isinstance(b, ImageIR)]
    assert len(image_irs) == 1, "应有 1 个 ImageIR"
    image_ir = image_irs[0]

    # 断言 A: lower 已把相对路径转成 workspace 内的绝对路径
    assert Path(image_ir.src_path).is_absolute()
    assert Path(image_ir.src_path) == png_path.resolve()

    # 3) render image paragraph, 插入到 baseline docx body 内
    document_root = load_document_xml(str(baseline_docx))
    body = document_root.find(f"{{{W_NS}}}body")
    paragraph = render_image(image_ir)
    # 放到 sectPr 之前 (sectPr 必须是 body 最后一个元素, 否则 Word 打开报错)
    sectPr = body.find(f"{{{W_NS}}}sectPr")
    if sectPr is not None:
        sectPr.addprevious(paragraph)
    else:
        body.append(paragraph)

    # 断言 B: render 产出的 r:embed sentinel 内就是绝对路径
    blips = paragraph.xpath(".//*[@r:embed]", namespaces={"r": R_NS})
    assert len(blips) == 1
    embed_val = blips[0].get(f"{{{R_NS}}}embed")
    assert embed_val.startswith("TEMP_IMG_REL:")
    embedded_path = embed_val[len("TEMP_IMG_REL:"):]
    assert Path(embedded_path).is_absolute()
    assert Path(embedded_path).exists(), "sentinel 内的路径应该指向真实存在的 PNG"

    # 4) write_document_xml: 把 sentinel 替换成真 rId, 把图片字节塞入 zip
    output_path = tmp_root / "output.docx"
    write_document_xml(str(baseline_docx), str(output_path), document_root)
    assert output_path.exists()

    # 5) 校验输出 zip
    with zipfile.ZipFile(output_path, "r") as zout:
        names = zout.namelist()

        # 断言 C (核心): 至少有一个新增图片字节匹配原 PNG
        media_pngs = [n for n in names if n.startswith("word/media/") and n.endswith(".png")]
        assert media_pngs, f"输出 zip 没有 word/media/*.png, names={names[:20]}"
        matched_bytes = any(zout.read(name) == _FAKE_PNG for name in media_pngs)
        assert matched_bytes, "新增图片字节应等于原 PNG"

        # 断言 D: document.xml 内 sentinel 已被替换成真 rId, 不再有 TEMP_IMG_REL: 残留
        doc_xml = zout.read("word/document.xml").decode("utf-8")
        assert "TEMP_IMG_REL:" not in doc_xml, "sentinel 应被 write_document_xml 替换成真 rId"

        # 断言 E: rels 内含新增 Image relationship
        rels_xml = zout.read("word/_rels/document.xml.rels").decode("utf-8")
        assert "image" in rels_xml.lower(), "rels 应含新增 image relationship"
