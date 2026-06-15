"""test_optimizer.py — docx_compiler/optimizer.py 纯函数测试 (PR-2.3)

optimizer 两个核心:
  - optimize_paragraph(paragraph) -> int  (返回变化数)
  - optimize_tree(root) -> int

做的事:
  1. _remove_empty_plain_runs: 删空 <w:t> 的 run
  2. _merge_adjacent_text_runs: 合并相邻同 rPr 的 text run

共 6 case.
"""
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docx_compiler.optimizer import optimize_paragraph, optimize_tree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
NS = {"w": W[1:-1]}


def _parse(xml_str: str):
    """解析 XML 字符串成 element."""
    return etree.fromstring(xml_str)


def _runs(p):
    return p.xpath("./w:r", namespaces=NS)


# =====================================================================
# 1. 删空 run
# =====================================================================

def test_remove_empty_text_runs():
    """<w:r><w:t/></w:r> (无文本) 应被删除.

    注意: 第一个和第三个 run 用不同的 rPr, 这样 _merge_adjacent_text_runs
    不会触发 (rpr_key 不同), 只测 _remove_empty_plain_runs 一条路径.
    """
    p = _parse(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:r><w:t>keep</w:t></w:r>'                                      # rPr = (none)
        '<w:r><w:t></w:t></w:r>'                                          # 空, 删
        '<w:r><w:rPr><w:b/></w:rPr><w:t>also_keep</w:t></w:r>'            # rPr = (b), 不会跟第 1 个合并
        '</w:p>'
    )
    changed = optimize_paragraph(p)
    assert changed == 1, f"应只触发 1 个变化 (删空 run), 实际 {changed}"
    runs = _runs(p)
    assert len(runs) == 2, f"应剩 2 个 run (空 run 被删), 实际 {len(runs)}"
    texts = [r.find(f"{W}t").text for r in runs]
    assert texts == ["keep", "also_keep"]


def test_keep_runs_with_tab_or_break():
    """<w:r> 含 <w:tab/> 或 <w:br/> 即使无 <w:t> 也不删 (有非文本内容)."""
    p = _parse(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:r><w:tab/></w:r>'  # 无 t 但有 tab, 保留
        '</w:p>'
    )
    changed = optimize_paragraph(p)
    assert changed == 0
    assert len(_runs(p)) == 1


# =====================================================================
# 2. 合并相邻同 rPr 的 run
# =====================================================================

def test_merge_adjacent_text_runs_with_same_rpr():
    """两个相邻 <w:r> rPr 完全相同 → 合并成 1 个, 文本拼接."""
    p = _parse(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>foo</w:t></w:r>'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>bar</w:t></w:r>'
        '</w:p>'
    )
    changed = optimize_paragraph(p)
    assert changed == 1
    runs = _runs(p)
    assert len(runs) == 1
    # 合并后文本应是 "foobar"
    assert runs[0].find(f"{W}t").text == "foobar"


def test_no_merge_when_rpr_differs():
    """相邻 run rPr 不同 (一个 bold 一个 italic) → 不合并."""
    p = _parse(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>foo</w:t></w:r>'
        '<w:r><w:rPr><w:i/></w:rPr><w:t>bar</w:t></w:r>'
        '</w:p>'
    )
    changed = optimize_paragraph(p)
    assert changed == 0
    assert len(_runs(p)) == 2


def test_optimize_tree_processes_all_paragraphs():
    """optimize_tree 递归处理 root 下所有 <w:p>."""
    root = _parse(
        '<root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:r><w:t></w:t></w:r></w:p>'  # 空 run
        '<w:p><w:r><w:t>ok</w:t></w:r></w:p>'  # 干净
        '<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>x</w:t></w:r>'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>y</w:t></w:r></w:p>'  # 可合并
        '</root>'
    )
    changed = optimize_tree(root)
    # 1 个空 run 删除 + 1 个 merge = 2
    assert changed == 2
    paras = root.xpath(".//w:p", namespaces=NS)
    assert len(paras) == 3
    # 第三个 paragraph 应只剩 1 个 run
    assert len(_runs(paras[2])) == 1
    assert paras[2].find(f"{W}r/{W}t").text == "xy"


def test_optimize_paragraph_idempotent_on_clean_input():
    """idempotent: 干净的 paragraph 再 optimize 一次变化数为 0."""
    p = _parse(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>once</w:t></w:r>'
        '</w:p>'
    )
    changed = optimize_paragraph(p)
    assert changed == 0
    # 再跑一次还是 0
    changed2 = optimize_paragraph(p)
    assert changed2 == 0
