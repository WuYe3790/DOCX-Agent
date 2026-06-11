"""v2: unzip_docx — 流式解压 + 沙箱化 + 多重防御

按 plan Section 4.1 实现:
- 路径走 resolve_workspace_path (docx_path 读 / output_dir 写)
- output_dir 强制在 workspace/unzipped/ 子目录下
- 不使用 extractall (zip bomb 防御)
- 用 zipfile.open() 流式解压, 累加字节数
- 单 entry 压缩比 > 100:1 拒绝 (zip bomb 防御)
- overwrite=true 时把旧目录重命名为 <name>_<timestamp> 备份
"""
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import (  # noqa: E402
    QUOTA_BYTES,
    resolve_workspace_path,
    workspace_dir,
    WorkspacePathError,
    to_relative_path,
)

from .common import json_result


# 单 entry 压缩比上限: 防 zip bomb (典型 42.zip 比例数万倍)
_ZIP_ENTRY_MAX_RATIO = 100
# entry 数上限: 防 DOS
_ZIP_MAX_ENTRIES = 10000


def unzip_docx(
    session_id: str,
    docx_path: str,
    output_dir: str,
    overwrite: bool = False,
) -> str:
    """v2: 把 .docx 解压到 workspace/unzipped/<output_dir>, 流式 + 多重防御

    沙箱化:
    - docx_path 走 resolver must_exist=True, must_be_file=True
    - output_dir 走 resolver must_exist=False, 且必须在 workspace/unzipped/ 下
    - overwrite=True: 把旧 output_dir 改名为 output_dir_<timestamp> 备份
    - overwrite=False: output_dir 已存在则返回 error

    防御:
    - zip slip: 拒绝含 .. / 绝对路径 / UNC 路径的 entry
    - zip bomb (单 entry): 拒绝压缩比 > 100:1
    - zip bomb (累加): 累加解压后字节数, 超 guard.QUOTA_BYTES 拒绝 + 回滚
    - DOS: entry 数 > 10000 拒绝
    """
    try:
        docx_path_resolved = resolve_workspace_path(
            session_id, docx_path, must_exist=True, must_be_file=True
        )
        output_dir_resolved = resolve_workspace_path(
            session_id, output_dir, must_exist=False
        )
    except WorkspacePathError as e:
        return json_result({"status": "error", "code": e.code, "message": e.user_message})

    # 强制 output_dir 在 workspace/unzipped/ 子目录下
    unzipped_root = workspace_dir(session_id) / "unzipped"
    if not output_dir_resolved.is_relative_to(unzipped_root):
        return json_result({
            "status": "error",
            "code": "out_of_unzipped",
            "message": f"unzip_docx 目标必须在 workspace/unzipped/ 子目录下: {output_dir}",
        })

    # overwrite 处理
    if output_dir_resolved.exists():
        if not overwrite:
            return json_result({
                "status": "error",
                "code": "output_exists",
                "message": f"output_dir 已存在, 设 overwrite=true 覆盖 (旧目录会被改名为 <name>_<timestamp> 备份): {output_dir}",
            })
        # 自动备份旧目录 (保留历史, 不断 Agent 心流)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = output_dir_resolved.parent / f"{output_dir_resolved.name}_{timestamp}"
        output_dir_resolved.rename(backup)

    output_dir_resolved.mkdir(parents=True, exist_ok=False)

    # 流式解压 + 多重防御
    try:
        with zipfile.ZipFile(str(docx_path_resolved), "r") as zf:
            entries = zf.infolist()
            if len(entries) > _ZIP_MAX_ENTRIES:
                shutil.rmtree(output_dir_resolved, ignore_errors=True)
                return json_result({
                    "status": "error",
                    "code": "too_many_entries",
                    "message": f"zip 包含过多 entry ({len(entries)} > {_ZIP_MAX_ENTRIES})",
                })

            decompressed_so_far = 0
            for entry in entries:
                # 1) zip slip 检查
                entry_path = Path(entry.filename)
                if entry_path.is_absolute() or any(part == ".." for part in entry_path.parts):
                    shutil.rmtree(output_dir_resolved, ignore_errors=True)
                    return json_result({
                        "status": "error",
                        "code": "zip_slip",
                        "message": f"zip slip: 非法 entry {entry.filename!r}",
                    })
                if entry.filename.startswith("\\"):
                    shutil.rmtree(output_dir_resolved, ignore_errors=True)
                    return json_result({
                        "status": "error",
                        "code": "zip_slip",
                        "message": f"zip slip (UNC): 非法 entry {entry.filename!r}",
                    })

                # 2) zip bomb 检查 (单 entry 压缩比)
                if entry.compress_size > 0:
                    ratio = entry.file_size / entry.compress_size
                    if ratio > _ZIP_ENTRY_MAX_RATIO:
                        shutil.rmtree(output_dir_resolved, ignore_errors=True)
                        return json_result({
                            "status": "error",
                            "code": "zip_bomb",
                            "message": f"zip bomb: {entry.filename!r} 压缩比 {ratio:.0f}:1 超过 {_ZIP_ENTRY_MAX_RATIO}:1",
                        })

                # 3) 累加解压后字节数
                decompressed_so_far += entry.file_size
                # 用 guard.QUOTA_BYTES qualified 访问, 测试可 monkeypatch 实时生效
                if decompressed_so_far > sys.modules["workspace.guard"].QUOTA_BYTES:
                    shutil.rmtree(output_dir_resolved, ignore_errors=True)
                    return json_result({
                        "status": "error",
                        "code": "quota_exceeded",
                        "message": f"解压后超过 session quota ({decompressed_so_far} > {QUOTA_BYTES})",
                    })

                # 4) 流式解压 (不调 extractall!)
                out_path = (output_dir_resolved / entry.filename).resolve()
                if not out_path.is_relative_to(output_dir_resolved.resolve()):
                    shutil.rmtree(output_dir_resolved, ignore_errors=True)
                    return json_result({
                        "status": "error",
                        "code": "zip_slip",
                        "message": f"entry 解析后越界: {entry.filename!r}",
                    })

                if entry.is_dir():
                    out_path.mkdir(parents=True, exist_ok=True)
                    continue

                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(entry) as src, open(out_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

        return json_result({
            "status": "ok",
            "docx_path": to_relative_path(session_id, docx_path_resolved),
            "output_dir": to_relative_path(session_id, output_dir_resolved),
            "file_count": sum(1 for p in output_dir_resolved.rglob("*") if p.is_file()),
            "decompressed_bytes": decompressed_so_far,
        })
    except zipfile.BadZipFile as e:
        shutil.rmtree(output_dir_resolved, ignore_errors=True)
        return json_result({"status": "error", "code": "bad_zip", "message": f"zip 文件损坏: {e}"})
    except Exception as e:
        shutil.rmtree(output_dir_resolved, ignore_errors=True)
        return json_result({"status": "error", "code": "extract_failed", "message": f"解压失败: {e}"})


tools_schema = {
    "type": "function",
    "function": {
        "name": "unzip_docx",
        "description": "把 .docx 解压到 session workspace 的 unzipped/ 子目录下, 流式 + zip slip/zip bomb 防御。overwrite=true 时旧目录改名为 <name>_<timestamp> 备份。",
        "parameters": {
            "type": "object",
            "properties": {
                "docx_path": {"type": "string", "description": "输入 .docx 文件路径 (相对 workspace 根)"},
                "output_dir": {"type": "string", "description": "解包目标子目录名 (会在 workspace/unzipped/<name> 下创建)"},
                "overwrite": {"type": "boolean", "description": "目标存在时是否覆盖 (旧目录自动加时间戳后缀备份), 默认 false"},
            },
            "required": ["docx_path", "output_dir"],
        },
    },
}
