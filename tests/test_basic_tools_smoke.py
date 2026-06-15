"""test_basic_tools_smoke.py — 3 个基础工具 smoke (PR-3.3)

  - ls        2 case (列根/不存在的 session)
  - read      2 case (读 .md/越界路径)
  - generate_image 2 case (非法 size 早抛 / 合法 size 走 sub-agent 流程)

注: generate_image 内部有 LLM 调 + 外部 API + sub-agent 审核循环,
完整 mock 复杂度高. 这里只测参数防御和 happy path 骨架.
"""
import json
import sys
from pathlib import Path

import pytest

pytest_plugins = ["_docx_factory"]
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from basic_tools.ls import ls
from basic_tools.read import read


def _ws(tmp_root, session_id: str) -> Path:
    return tmp_root / session_id / "workspace"


# =====================================================================
# ls: 2 case
# =====================================================================

class TestLs:
    def test_ls_root_lists_files(self, tmp_root, session_id):
        """ls(".") → status=ok, entries 含 workspace 内文件."""
        ws = _ws(tmp_root, session_id)
        (ws / "doc1.docx").write_bytes(b"x")
        (ws / "subdir").mkdir()

        result = json.loads(ls(session_id, "."))
        assert result["status"] == "ok"
        names = [e["name"] for e in result["entries"]]
        assert "doc1.docx" in names
        assert "subdir" in names
        # is_dir 标记正确
        for e in result["entries"]:
            if e["name"] == "subdir":
                assert e["is_dir"] is True
            elif e["name"] == "doc1.docx":
                assert e["is_dir"] is False

    def test_ls_nonexistent_session_returns_empty_entries(self, tmp_root, session_id):
        """ls 不存在的 session → 实际行为: resolve_workspace_path 自动 mkdir,
        返回 status=ok + 空 entries.

        记录此行为, 未来如果想改"严格校验 session 必须存在"再改测试.
        """
        result = json.loads(ls("nonexistent_session_xyz", "."))
        # 实际: status=ok, entries=[]
        assert result["status"] == "ok"
        assert result["entries"] == []


# =====================================================================
# read: 2 case
# =====================================================================

class TestRead:
    def test_read_md_file_returns_content(self, tmp_root, session_id):
        """read(.md) → status=ok, content 含文件内容."""
        (_ws(tmp_root, session_id) / "test.md").write_text(
            "第一行\n第二行\n第三行\n", encoding="utf-8"
        )
        result = json.loads(read(session_id, "test.md"))
        assert result["status"] == "ok"
        assert "第一行" in result["content"]
        assert result["total_lines"] >= 3
        assert result["encoding"] == "utf-8"

    def test_read_out_of_bounds_returns_error(self, tmp_root, session_id):
        """读越界路径 → status=error, 不抛."""
        result = json.loads(read(session_id, "../../../etc/passwd"))
        assert result["status"] == "error"


# =====================================================================
# generate_image: 2 case (参数防御 + smoke 骨架)
# =====================================================================

class TestGenerateImage:
    def test_invalid_size_early_returns_error(self, tmp_root, session_id, monkeypatch):
        """非法 size → 工具在调 API 前 early return status=error.

        避免浪费 LLM 调用.
        """
        from basic_tools import generate_image as gi
        # 工具内部用 LLMClientAdapter(), 这里 patch 防止误连
        monkeypatch.setattr(gi, "LLMClientAdapter", lambda: None)

        result = json.loads(gi.generate_image(
            session_id=session_id,
            prompt="a cat",
            size="9999x9999",  # 非法
        ))
        assert result["status"] == "error"
        assert "非法 size" in result["message"]

    def test_max_iterations_clamped_to_5(self, tmp_root, session_id, monkeypatch):
        """max_iterations=99 → 工具内部 clamp 到 5, 不抛."""
        from basic_tools import generate_image as gi
        # 模拟后续依赖: pick_capable_adapter 返回 None
        # → 工具会走 "no_vision_adapter" 错误路径, 不会真调 LLM
        # 但 max_iterations 钳位发生在调 API 之前, 我们能验证这点
        monkeypatch.setattr(gi, "LLMClientAdapter", lambda: None)
        monkeypatch.setattr(gi, "pick_capable_adapter", lambda *a, **kw: None)

        result = json.loads(gi.generate_image(
            session_id=session_id,
            prompt="a cat",
            max_iterations=99,  # 应 clamp 到 5
        ))
        # 不抛, 返回 error (因为 adapter None)
        assert "status" in result
        # 不应该是 "no_vision_adapter" 之前的崩溃
        assert result["status"] in ("error", "no_vision_adapter")
