"""test_diagnostics.py — docx_compiler/diagnostics.py 4 case (PR-3.1)

diagnostics.py 包含 4 个工具:
  - Diagnostic dataclass
  - to_dict() 方法
  - diagnostics_to_dicts(list) 函数
  - has_errors(list) 是否有 error 级别
  - support_summary(blocks) 统计 native/degraded/rejected

全是纯函数/纯 dataclass, 无 I/O, 测试成本极低.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from docx_compiler.diagnostics import (
    Diagnostic,
    diagnostics_to_dicts,
    has_errors,
    support_summary,
)


# =====================================================================
# 1. Diagnostic.to_dict() 字段映射
# =====================================================================

def test_diagnostic_to_dict_includes_required_fields():
    """to_dict 必含 level / code / message."""
    d = Diagnostic(level="warning", code="W001", message="something wrong")
    out = d.to_dict()
    assert out["level"] == "warning"
    assert out["code"] == "W001"
    assert out["message"] == "something wrong"
    # block_id / line_start / line_end / support 不在 to_dict (空值时不输出)
    assert "block_id" not in out
    assert "support" not in out


def test_diagnostic_to_dict_includes_optional_when_set():
    """block_id / line_start / line_end / support 设置时出现在 to_dict."""
    d = Diagnostic(
        level="error", code="E001", message="bad",
        block_id="B003", line_start=5, line_end=7, support="degraded",
    )
    out = d.to_dict()
    assert out["block_id"] == "B003"
    assert out["line_start"] == 5
    assert out["line_end"] == 7
    assert out["support"] == "degraded"


# =====================================================================
# 2. diagnostics_to_dicts 批量
# =====================================================================

def test_diagnostics_to_dicts_returns_list_of_dicts():
    """list[Diagnostic] → list[dict]."""
    diags = [
        Diagnostic(level="info", code="I001", message="ok"),
        Diagnostic(level="error", code="E001", message="bad"),
    ]
    out = diagnostics_to_dicts(diags)
    assert len(out) == 2
    assert all(isinstance(d, dict) for d in out)
    assert out[0]["code"] == "I001"
    assert out[1]["code"] == "E001"


# =====================================================================
# 3. has_errors 短路判断
# =====================================================================

def test_has_errors_returns_true_when_any_error_level():
    """含 level='error' 的 Diagnostic 时返回 True."""
    diags = [
        Diagnostic(level="info", code="I", message="x"),
        Diagnostic(level="error", code="E", message="bad"),
    ]
    assert has_errors(diags) is True


def test_has_errors_returns_false_when_no_error():
    """全是 info / warning 时返回 False."""
    diags = [
        Diagnostic(level="info", code="I", message="x"),
        Diagnostic(level="warning", code="W", message="meh"),
    ]
    assert has_errors(diags) is False


# =====================================================================
# 4. support_summary 统计
# =====================================================================

def test_support_summary_counts_native_degraded_rejected():
    """按 block.support 字段统计, 缺省当 native, 未知当 rejected."""
    blocks = [
        {"support": "native"},
        {"support": "degraded"},
        {"support": "rejected"},
        {},  # 缺省 → native
        {"support": "unknown_value"},  # 未知 → rejected
    ]
    summary = support_summary(blocks)
    assert summary == {"native": 2, "degraded": 1, "rejected": 2}


def test_support_summary_empty_input():
    """空列表 → 全 0."""
    assert support_summary([]) == {"native": 0, "degraded": 0, "rejected": 0}
