"""v3 测试: docx_preview_diff.py 的 2 个纯函数

覆盖:
  - build_paragraph_diff: 6 个 case
    - identical files (无变化)
    - paragraph added
    - paragraph modified
    - paragraph removed
    - zip 损坏 (graceful empty result)
    - Path 对象入参
  - extract_preview_event: 4 个 case
    - 正常 markdown_to_word result → dict
    - status=error → None
    - 非 JSON 字符串 → None
    - 缺字段 → None

设计:
  - 用 tmp_path fixture 隔离文件系统
  - 用 _build_minimal_docx 工厂函数生成测试用 docx (避开 python-docx 依赖)
  - 纯函数测试, 不依赖 session_id
"""
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from docx_tools.docx_preview_diff import (  # noqa: E402
    build_paragraph_diff,
    extract_preview_event,
)


# === 测试工具: 构造最小合法 docx ===

WORD_XML_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
{paragraphs}
  </w:body>
</w:document>
'''


def _para(text: str) -> str:
    """生成 <w:p> 节点, 文本走 XML 转义防注入."""
    safe = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    return f'    <w:p><w:r><w:t xml:space="preserve">{safe}</w:t></w:r></w:p>'


def _build_minimal_docx(path: Path, paragraphs: list[str]) -> None:
    """用 zipfile 写一个最小 docx, 只含 word/document.xml.

    Notes:
      - 不写 [Content_Types].xml / rels, 因为 build_paragraph_diff 只读 document.xml
      - 真实 docx 用 Office 打开会报 "文件损坏", 但我们的 diff 不需要, 只读 XML
    """
    body = "\n".join(_para(t) for t in paragraphs)
    xml_bytes = WORD_XML_TEMPLATE.format(paragraphs=body).encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml_bytes)


# === build_paragraph_diff 测试 ===

class TestBuildParagraphDiff:
    """build_paragraph_diff: 6 个 case."""

    def test_identical_files_no_paragraph_changes(self, tmp_path: Path):
        """两个完全相同的 docx → paragraph_changes 为空列表."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["第一段", "第二段", "第三段"])
        _build_minimal_docx(after, ["第一段", "第二段", "第三段"])

        result = build_paragraph_diff(before, after)

        assert "changed_files" in result
        assert "paragraph_changes" in result
        assert result["paragraph_changes"] == [], (
            f"identical files 应无段落变化, 实际: {result['paragraph_changes']}"
        )

    def test_paragraph_modified_detected(self, tmp_path: Path):
        """某段文本被修改 → paragraph_changes 含该段(before/after 不同)."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["第一段", "原文内容", "第三段"])
        _build_minimal_docx(after, ["第一段", "修改后内容", "第三段"])

        result = build_paragraph_diff(before, after)

        # 只应有 1 个变化 (paragraph_index=2)
        assert len(result["paragraph_changes"]) == 1
        change = result["paragraph_changes"][0]
        assert change["paragraph_index"] == 2
        assert change["before"] == "原文内容"
        assert change["after"] == "修改后内容"

    def test_paragraph_added_detected(self, tmp_path: Path):
        """新段被添加 → before 短, after 长, 多出来的段在 result 中."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["第一段", "第二段"])
        _build_minimal_docx(after, ["第一段", "第二段", "新插入的第三段"])

        result = build_paragraph_diff(before, after)

        # paragraph_index=3 是新增的
        indices = [c["paragraph_index"] for c in result["paragraph_changes"]]
        assert 3 in indices
        added = next(c for c in result["paragraph_changes"] if c["paragraph_index"] == 3)
        assert added["before"] == ""  # before 不存在
        assert added["after"] == "新插入的第三段"

    def test_paragraph_removed_detected(self, tmp_path: Path):
        """某段被删除 → 因位置 diff 的 shift 现象, '要删除的段' 会作为某条 change 的 before 出现.

        Notes:
          - 这是 position-based diff 的已知限制 (plan 风险 #1)
          - PoC 阶段接受: 不会精确标记"删除", 而是标记为 position 处的修改
          - 测试验证: "要删除的段" 必须出现在某条 change 的 before 字段
        """
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["第一段", "要删除的段", "第三段"])
        _build_minimal_docx(after, ["第一段", "第三段"])

        result = build_paragraph_diff(before, after)

        # "要删除的段" 应作为某条 change 的 before 出现
        all_befores = [c["before"] for c in result["paragraph_changes"]]
        assert "要删除的段" in all_befores, (
            f"被删段应作为 before 出现, 实际 changes: {result['paragraph_changes']}"
        )
        # 至少有一条 change 涉及 index=2 或 index=3 (shift 位置)
        indices = [c["paragraph_index"] for c in result["paragraph_changes"]]
        assert any(i in (2, 3) for i in indices)

    def test_zip_corrupted_returns_empty(self, tmp_path: Path):
        """zip 损坏 → graceful 降级, 返回空 dict (不抛异常)."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"

        # 写一个不是合法 zip 的文件
        before.write_bytes(b"not a real zip file at all")
        _build_minimal_docx(after, ["第一段"])

        result = build_paragraph_diff(before, after)

        # 不应抛异常, 应返回空 dict
        assert result == {"changed_files": [], "paragraph_changes": []}

    def test_accepts_path_objects(self, tmp_path: Path):
        """参数是 Path 对象, 不是字符串 (sanity check)."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["A"])
        _build_minimal_docx(after, ["A 修改"])

        # Path 对象
        result = build_paragraph_diff(Path(before), Path(after))
        assert len(result["paragraph_changes"]) == 1
        assert result["paragraph_changes"][0]["after"] == "A 修改"

    def test_changed_files_populated(self, tmp_path: Path):
        """changed_files 至少应含 word/document.xml (业务核心变化)."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["A"])
        _build_minimal_docx(after, ["B"])

        result = build_paragraph_diff(before, after)

        # 最小 docx 只含 word/document.xml, 所以 changed_files 至少应有它
        paths = {f["path"] for f in result["changed_files"]}
        assert "word/document.xml" in paths


# === extract_preview_event 测试 ===

class TestExtractPreviewEvent:
    """extract_preview_event: 4 个 case."""

    def test_valid_ok_result_returns_dict(self):
        """正常的 markdown_to_word result (status=ok, 全字段) → 返回 dict."""
        result_json = json.dumps({
            "status": "ok",
            "docx_path": "input.docx",
            "output_path": "output.docx",
            "action_count": 2,
            "diagnostics": [{"level": "warning", "code": "X", "message": "test"}],
            "support_summary": {"native": 1, "degraded": 1, "rejected": 0},
        })

        event = extract_preview_event(result_json)

        assert event is not None
        assert event["docx_path"] == "input.docx"
        assert event["output_path"] == "output.docx"
        assert event["action_count"] == 2
        assert len(event["diagnostics"]) == 1
        assert event["support_summary"]["degraded"] == 1

    def test_error_status_returns_none(self):
        """result.status=error → 返回 None, 不触发预览."""
        result_json = json.dumps({
            "status": "error",
            "message": "action 1 failed",
        })

        assert extract_preview_event(result_json) is None

    def test_rejected_markdown_returns_none(self):
        """rejected_markdown 也是非 ok 状态 → None."""
        result_json = json.dumps({
            "status": "rejected_markdown",
            "message": "Markdown 语义检查失败",
        })

        assert extract_preview_event(result_json) is None

    def test_invalid_json_returns_none(self):
        """非 JSON 字符串 → None, 不抛异常."""
        assert extract_preview_event("not json at all {{{") is None
        assert extract_preview_event("") is None
        assert extract_preview_event("null") is None  # null 是有效 JSON 但不是 dict

    def test_missing_required_fields_returns_none(self):
        """缺 docx_path 或 output_path → None (不是 markdown_to_word result)."""
        # 缺 output_path
        result_json = json.dumps({"status": "ok", "docx_path": "a.docx"})
        assert extract_preview_event(result_json) is None

        # 缺 docx_path
        result_json = json.dumps({"status": "ok", "output_path": "b.docx"})
        assert extract_preview_event(result_json) is None

        # 空字段
        result_json = json.dumps({"status": "ok", "docx_path": "", "output_path": ""})
        assert extract_preview_event(result_json) is None

    def test_empty_diagnostics_ok(self):
        """diagnostics 为空列表也 OK, 不应抛异常."""
        result_json = json.dumps({
            "status": "ok",
            "docx_path": "in.docx",
            "output_path": "out.docx",
            "action_count": 0,
            "diagnostics": [],
            "support_summary": {"native": 0, "degraded": 0, "rejected": 0},
        })

        event = extract_preview_event(result_json)
        assert event is not None
        assert event["diagnostics"] == []
        assert event["action_count"] == 0
