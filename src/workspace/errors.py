"""v2: Workspace 沙箱相关异常类

所有异常携带:
- code: 机器可读错误码 (LLM / 前端可编程处理)
- user_message: 人类可读消息 (UI 直接展示)
"""


class WorkspacePathError(ValueError):
    """路径解析失败 — 路径越界 / 绝对路径 / symlink 等"""

    def __init__(self, code: str, user_message: str):
        self.code = code
        self.user_message = user_message
        super().__init__(f"[{code}] {user_message}")


class BadUpload(ValueError):
    """上传文件不合法 — 坏文件名 / 坏 magic bytes / 扩展名不支持"""

    def __init__(self, code: str, user_message: str):
        self.code = code
        self.user_message = user_message
        super().__init__(f"[{code}] {user_message}")


class ZipBombError(BadUpload):
    """压缩炸弹 — 解压后总大小超 quota 或单 entry 压缩比异常"""

    def __init__(self, user_message: str = "解压后大小超过 session quota"):
        super().__init__(code="zip_bomb", user_message=user_message)
