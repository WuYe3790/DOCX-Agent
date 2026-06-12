"""v3 实时预览配套 — docx_preview_diff.py

定位: 旁路功能 (PoC), 隔离重于复用.
  - 不去重构 src/docx_tools/diff_docx.py, 而是把核心算法原样 copy 过来
  - 杜绝修改 diff_docx.py 把 LLM 工具搞挂的风险
  - 30 行代码换零改动风险, 符合 plan 第 2 节"直接复制"策略

设计原则:
  - 纯函数, 不依赖 session_id (input 是 Path 对象)
  - 失败静默返回空 dict 或 None (PoC 原则: 不堆 toast)
  - 解 JSON 时防御性处理, 不抛异常 (LLM 返回可能格式异常)
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from .common import file_sha256, load_document_xml, paragraph_text, paragraphs  # noqa: E402


def build_paragraph_diff(before_path: Path, after_path: Path) -> dict:
    """对比两个 docx 文件, 返回 {changed_files, paragraph_changes}.

    与 diff_docx 工具的区别:
      - 不依赖 session_id, 输入是 Path 对象 (in-process 调用)
      - 失败时返回空 dict (不抛 WorkspacePathError 等)
      - 没有 marker_prefix 参数 (LLM 流程不需要)

    采用"直接复制"策略:
      - _zip_file_map 和 _paragraph_texts 的实现从 diff_docx.py:69-88 复制
      - 不抽公共函数, 隔离重于复用
    """
    try:
        # === 直接复制自 src/docx_tools/diff_docx.py:69-88 ===
        def _zip_file_map(docx_path: str):
            with zipfile.ZipFile(docx_path, "r") as docx:
                return {info.filename: info.file_size for info in docx.infolist() if not info.is_dir()}

        def _zip_member_hash(docx_path: str, name: str):
            with zipfile.ZipFile(docx_path, "r") as docx:
                data = docx.read(name)
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(data)
                temp_path = Path(f.name)
            try:
                return file_sha256(temp_path)
            finally:
                temp_path.unlink(missing_ok=True)

        def _paragraph_texts(docx_path: str):
            root = load_document_xml(docx_path)
            return [paragraph_text(p) for p in paragraphs(root)]
        # === 复制结束 ===

        before_files = _zip_file_map(str(before_path))
        after_files = _zip_file_map(str(after_path))
        all_names = sorted(set(before_files) | set(after_files))

        changed_files: list[dict] = []
        for name in all_names:
            if name not in before_files:
                changed_files.append({
                    "path": name,
                    "status": "added",
                    "before_size": 0,
                    "after_size": after_files[name],
                })
            elif name not in after_files:
                changed_files.append({
                    "path": name,
                    "status": "removed",
                    "before_size": before_files[name],
                    "after_size": 0,
                })
            else:
                before_hash = _zip_member_hash(str(before_path), name)
                after_hash = _zip_member_hash(str(after_path), name)
                if before_hash != after_hash:
                    changed_files.append({
                        "path": name,
                        "status": "changed",
                        "before_size": before_files[name],
                        "after_size": after_files[name],
                        "delta": after_files[name] - before_files[name],
                    })

        before_texts = _paragraph_texts(str(before_path))
        after_texts = _paragraph_texts(str(after_path))
        paragraph_changes: list[dict] = []
        for i in range(max(len(before_texts), len(after_texts))):
            before = before_texts[i] if i < len(before_texts) else ""
            after = after_texts[i] if i < len(after_texts) else ""
            if before != after:
                paragraph_changes.append({
                    "paragraph_index": i + 1,
                    "before": before,
                    "after": after,
                })

        return {
            "changed_files": changed_files,
            "paragraph_changes": paragraph_changes,
        }
    except Exception as exc:
        # 失败静默: zip 损坏 / 解析异常 / 任何意外
        # 不向用户报错, PoC 原则, 预览失败不阻塞主流程
        # 调用方 (agent._maybe_emit_docx_preview) 会拿到 {} 然后跳过 yield
        print(f"[docx_preview_diff] build_paragraph_diff failed: {exc!r}")
        return {"changed_files": [], "paragraph_changes": []}


def extract_preview_event(tool_result_json: str) -> dict | None:
    """从 markdown_to_word 的 result JSON 抽出 preview 事件所需字段.

    返回:
      {
        "docx_path": str,        # 输入 docx (workspace 相对路径)
        "output_path": str,      # 输出 docx (workspace 相对路径, 这是预览要展示的)
        "action_count": int,
        "diagnostics": list[dict],
        "support_summary": {"native": int, "degraded": int, "rejected": int},
      }

    返回 None 的场景:
      - JSON 解析失败
      - 不是 markdown_to_word 的 result (缺少关键字段)
      - status != "ok" (apply 失败 / rejected_markdown 等)
    """
    try:
        result = json.loads(tool_result_json)
    except (json.JSONDecodeError, TypeError):
        return None

    # 必须是 ok 状态才触发预览
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None

    # 关键字段缺失说明不是 markdown_to_word 的 result
    docx_path = result.get("docx_path")
    output_path = result.get("output_path")
    if not docx_path or not output_path:
        return None

    return {
        "docx_path": docx_path,
        "output_path": output_path,
        "action_count": result.get("action_count", 0),
        "diagnostics": result.get("diagnostics", []) or [],
        "support_summary": result.get("support_summary", {"native": 0, "degraded": 0, "rejected": 0}),
    }
