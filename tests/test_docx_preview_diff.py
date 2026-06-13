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
        """某段被删除 → LCS diff 精确标记: paragraph_index 锚到 after 中下一段, after="".

        v3.3 收紧: 改用 difflib.SequenceMatcher 后, 删除/新增/修改不再 cascade.
        被删段精确出现一条 change, before=原文, after="", 且不波及后续段.
        """
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["第一段", "要删除的段", "第三段"])
        _build_minimal_docx(after, ["第一段", "第三段"])

        result = build_paragraph_diff(before, after)

        # 应仅有一条 change: 被删段
        assert len(result["paragraph_changes"]) == 1, (
            f"删除一段应只产 1 条 change (LCS), 实际: {result['paragraph_changes']}"
        )
        change = result["paragraph_changes"][0]
        assert change["before"] == "要删除的段"
        assert change["after"] == ""
        # paragraph_index 锚到 after 中"它本该所在位置的下一段" (= 第三段所在位置 = 2, 1-based)
        assert change["paragraph_index"] == 2

    def test_insert_in_middle_no_cascade(self, tmp_path: Path):
        """v3.3 回归: 中间插入新段, 后续段不应被错标 modified/added.

        bug 历史: position-based diff 算法在第 1 段后插入 → 后续所有段都因为位置 shift
        被算成 "before[i] vs after[i] 不等", 最后一段甚至会被错标 added (绿色加在空行/邻段).
        LCS diff 后只产 1 条 insert change, 后续段保持 unchanged.
        """
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["标题", "正文A", "正文B"])
        _build_minimal_docx(after, ["标题", "新增段", "正文A", "正文B"])

        result = build_paragraph_diff(before, after)

        # 应仅有 1 条 change: 新增段 (paragraph_index=2, before="", after="新增段")
        assert len(result["paragraph_changes"]) == 1, (
            f"中间插入应只产 1 条 change (LCS), 实际: {result['paragraph_changes']}"
        )
        change = result["paragraph_changes"][0]
        assert change["paragraph_index"] == 2
        assert change["before"] == ""
        assert change["after"] == "新增段"

    def test_delete_in_middle_no_cascade(self, tmp_path: Path):
        """v3.3 回归: 中间删除一段, 后续未变段不应被错标.

        bug 历史同上 — 删除一段后, 后续所有段在 position-based 配对里都 shift, 全标错.
        """
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["标题", "要删除", "正文A", "正文B"])
        _build_minimal_docx(after, ["标题", "正文A", "正文B"])

        result = build_paragraph_diff(before, after)

        assert len(result["paragraph_changes"]) == 1
        change = result["paragraph_changes"][0]
        assert change["before"] == "要删除"
        assert change["after"] == ""

    def test_modify_does_not_affect_others(self, tmp_path: Path):
        """v3.3 回归: 修改一段, 其他段保持 unchanged."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["第一段", "原文", "第三段", "第四段"])
        _build_minimal_docx(after, ["第一段", "新内容", "第三段", "第四段"])

        result = build_paragraph_diff(before, after)

        assert len(result["paragraph_changes"]) == 1
        change = result["paragraph_changes"][0]
        assert change["paragraph_index"] == 2
        assert change["before"] == "原文"
        assert change["after"] == "新内容"

    def test_anchor_text_field_present_for_all_change_types(self, tmp_path: Path):
        """v3.4: 每条 change 必须含 anchor_text 字段, 取值规则 = (after || before).strip().

        anchor_text 是前端 docx-preview-panel 按内容匹配 <p> 的 key, 避免按 idx 取
        被表格/页眉/页脚段错位.

        构造说明: 必须让 LCS 把 modified / insert / delete 切成 3 个独立 opcode,
        所以在 modified 段和被删/新增段之间放一个"公共锚段"打断 region —
        否则 SequenceMatcher 会把相邻变更打包成一个 N:M replace.
        """
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        # 锚段: 标题, 公共段A, 公共段B (后两段把 modify/insert/delete 切开)
        _build_minimal_docx(before, ["标题", "原文 A", "公共段 A", "删除段", "公共段 B"])
        _build_minimal_docx(after,  ["标题", "修改后 A", "公共段 A", "公共段 B", "新增段"])

        result = build_paragraph_diff(before, after)
        changes = result["paragraph_changes"]

        # 每条都必须含 anchor_text 字段
        for c in changes:
            assert "anchor_text" in c, f"change 缺 anchor_text 字段: {c}"
            expected = (c["after"] or c["before"]).strip()
            assert c["anchor_text"] == expected, (
                f"anchor_text 不等于 (after || before).strip(): {c}"
            )

        # 新增段: anchor_text == after
        added = next((c for c in changes if c["before"] == "" and c["after"]), None)
        assert added is not None, f"应有 1 条 added change, 实际: {changes}"
        assert added["anchor_text"] == "新增段"

        # 删除段: anchor_text == before (after 空, 退回 before)
        deleted = next((c for c in changes if c["after"] == "" and c["before"]), None)
        assert deleted is not None, f"应有 1 条 deleted change, 实际: {changes}"
        assert deleted["anchor_text"] == "删除段"

        # 修改段: anchor_text == after (after 优先)
        modified = next(
            (c for c in changes if c["before"] and c["after"] and c["before"] != c["after"]),
            None,
        )
        assert modified is not None, f"应有 1 条 modified change, 实际: {changes}"
        assert modified["anchor_text"] == "修改后 A"

    def test_anchor_text_strips_whitespace(self, tmp_path: Path):
        """v3.4: anchor_text 必须 strip 前后空白, 容忍后端 paragraph_text 与
        前端 docx-preview 渲染 textContent 的空格/换行差异."""
        before = tmp_path / "before.docx"
        after = tmp_path / "after.docx"
        _build_minimal_docx(before, ["A"])
        _build_minimal_docx(after, ["  B 带前后空格  "])

        result = build_paragraph_diff(before, after)
        # 1 条 replace (modified): anchor_text 应是 strip 后的 "B 带前后空格"
        assert any(c.get("anchor_text") == "B 带前后空格" for c in result["paragraph_changes"]), (
            f"anchor_text 未 strip: {result['paragraph_changes']}"
        )

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
