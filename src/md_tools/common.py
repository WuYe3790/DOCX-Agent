import json
from pathlib import Path


def json_result(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def draft_path(path: str, session_dir: Path) -> Path:
    """v2: 草稿路径强制在 session_dir/drafts/ 下 (沙箱化, 避免越界到其他 session 或全局目录)

    Args:
        path: LLM 传的路径 (可只传 filename, 也可传 drafts/foo.md)
        session_dir: Agent 隐式注入的 session 目录 (out/sessions/<id>/)

    Returns:
        解析后绝对路径 (未存在)

    Raises:
        ValueError: 路径含 '..' / 绝对路径 / 非 .md 后缀 / 解析后越出 drafts_dir
    """
    drafts_dir = (session_dir / "drafts").resolve()
    drafts_dir.mkdir(parents=True, exist_ok=True)  # 草稿目录自动建

    raw = Path(path)
    if not raw.suffix:
        raw = raw.with_suffix(".md")

    # === v2 显式守卫: 检测越界意图 (在 basename 化之前) ===
    # 1) 路径任何段含 '..' → 显式拒绝
    if any(part == ".." for part in raw.parts):
        raise ValueError(f"Markdown 草稿路径不允许 '..' 越界: {path}")
    # 2) 绝对路径 (跨平台: Windows Path.is_absolute 对 '/etc/passwd' 返回 False, 需额外检测字符串前缀)
    if raw.is_absolute() or path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"Markdown 草稿路径不允许绝对路径: {path}")

    # 强制在 session_dir/drafts/ 下
    if not raw.parent or str(raw.parent) == ".":
        target = drafts_dir / raw
    else:
        # LLM 传了子路径 (e.g. "drafts/cover.md") — 只取文件名, 强制放进 drafts/
        target = drafts_dir / raw.name

    resolved_target = target.resolve()
    if drafts_dir != resolved_target and drafts_dir not in resolved_target.parents:
        raise ValueError(f"Markdown 草稿只能在 {drafts_dir} 目录下 (拒绝越界: {resolved_target})")
    if resolved_target.suffix.lower() != ".md":
        raise ValueError("Markdown 草稿路径必须以 .md 结尾")
    return target


def read_markdown_text(path: str, session_dir: Path) -> tuple[Path, str]:
    """v2: 读草稿, 同样在 session_dir/drafts/ 沙箱下"""
    target = draft_path(path, session_dir)
    if not target.exists():
        raise FileNotFoundError(f"Markdown 草稿不存在: {target}")
    return target, target.read_text(encoding="utf-8")
