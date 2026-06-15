"""conftest.py — 让 test_docx_compiler/ 子目录的所有 test 文件
能用到 _docx_factory 的 fixture (tmp_root, session_id 等).

放在子目录里是因为 pytest_plugins 必须放在 conftest.py, 不能放 test_*.py
(否则 "fixture not found" 错误). 详见 PR-2.3 修复.
"""
pytest_plugins = ["_docx_factory"]
