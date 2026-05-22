import json
from pathlib import Path


DRAFT_ROOT = Path("out") / "drafts"


def json_result(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def draft_path(path: str) -> Path:
    raw = Path(path)
    if not raw.suffix:
        raw = raw.with_suffix(".md")
    if not raw.parent or str(raw.parent) == ".":
        raw = DRAFT_ROOT / raw

    resolved_root = DRAFT_ROOT.resolve()
    resolved_path = raw.resolve()
    if resolved_root != resolved_path and resolved_root not in resolved_path.parents:
        raise ValueError("Markdown 草稿只能写入或读取 out/drafts 目录")
    if resolved_path.suffix.lower() != ".md":
        raise ValueError("Markdown 草稿路径必须以 .md 结尾")
    return raw


def read_markdown_text(path: str) -> tuple[Path, str]:
    target = draft_path(path)
    if not target.exists():
        raise FileNotFoundError(f"Markdown 草稿不存在: {target}")
    return target, target.read_text(encoding="utf-8")
