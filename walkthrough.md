# Workspace Sandbox + File Upload 实施 Walkthrough

> 实施分支: `feature/workspace-sandbox`
> 计划文件: `C:\Users\z1950\.claude\plans\agent-rosy-lighthouse.md`

---

## 阶段 0: 切分支 + 项目约定

- 切到 `feature/workspace-sandbox` (不在 master 直接动)
- 工作纪律: 每步独立 commit,中文 subject,`feat(scope): 中文动词` 风格;每步 `pytest tests/` 验证零回归;不顺手优化无关代码
- 测试: 真实联调用商汤 (sensenova-6.7-flash-lite, 免费),不用 DeepSeek

---

## 阶段 1: 路径解析层 `src/workspace/guard.py` + 单元测试 (commit `df1b658`)

**做了什么**: 新建 `src/workspace/{__init__,errors,guard}.py` 作为所有 docx/md/basic 工具的唯一路径解析入口。零行为变更(没有任何现有工具被修改),纯加法。

**关键文件**:
- `src/workspace/errors.py`: `WorkspacePathError` / `BadUpload` / `ZipBombError` 异常类,带 `code` 字段(机器可读) + `user_message` 字段(UI 友好)
- `src/workspace/guard.py`: 5 层防御路径解析

**5 层防御 (resolve_workspace_path)**:
1. `validate_session_id` (字符黑名单: `\` `/` `..` `\0` 控制字符,长度 ≤ 100)
2. 拒绝空 raw_path
3. 拒绝绝对路径 (Windows + POSIX)
4. 拒绝 parts 含 `..` 或 NUL
5. `(workspace_dir / raw_path).resolve().is_relative_to(workspace_dir.resolve())`
6. must_exist / must_be_file / must_be_dir 校验
7. allow_symlinks=False 时拒绝 symlink

**其他 API**:
- `workspace_dir(session_id)`: 自动 mkdir session_dir + workspace
- `safe_workspace_filename(original)`: basename 化, 拒绝隐藏文件 / 控制字符, 截断 200 字符(保留扩展名)
- `unique_workspace_target(workspace, desired_name)`: 重名返回 `__1` / `__2` / ...
- `build_workspace_tree(session_id, max_depth=2, max_files=20)`: 给 LLM 看的文件树, 隐藏文件/__pycache__/node_modules 过滤, 超 max_files 截断 + 提示

**测试**: `tests/test_workspace_guard.py` 37 个 case
- validate_session_id 黑名单 (空 / 路径分隔符 / .. / 过长 / NUL / 控制字符)
- resolve_workspace_path 5 层防御 (相对合法 / .. 拒绝 / 绝对拒绝 / 存在性 / 类型 / .. in basename 允许 / 子目录允许 / symlink 拒绝 / 跨 session 隔离)
- safe_workspace_filename (plain / path 前缀 / 隐藏 / 空 / 控制 / 截断)
- unique_workspace_target (无冲突 / 单冲突 / 双冲突 / 无扩展名)
- build_workspace_tree (空 / 平面 / max_depth / max_files 截断 / 隐藏排除)

**回归**: 138 现有 + 37 新增 = 全过

---

## 阶段 2a: Upload HTTP endpoints (commit `a522adb`)

**做了什么**: 新建 `src/workspace/api.py` 4 个 HTTP endpoints,挂载到 `server.py` 的 `/api/sessions` 路径下。

**4 个 endpoints**:
| Method | Path | 行为 |
|---|---|---|
| POST | `/{id}/upload` | multipart upload, 流式读 64KB chunks, magic bytes 校验, quota 检查 |
| GET | `/{id}/workspace` | 列出文件 (含子目录, sorted by mtime+name tuple) |
| DELETE | `/{id}/workspace/{fn}` | 删除单文件 |
| POST | `/{id}/workspace/clear` | 清空 workspace (只删文件, 留目录) |

**核心设计**:
- env flag `WORKSPACE_UPLOAD_ENABLED=false` → 所有写端点 503,GET 不受影响
- **流式读 + 写到系统 temp dir** (`tempfile.mkstemp()` 不指定 dir),不用 workspace 内 tmp — 避免 quota 检查把"自己"算进去
- **magic bytes 校验仅对 `.docx` `.zip` `.xlsx` `.pptx` 强制** `PK\x03\x04`,普通文件跳过(防误伤)
- 文件名走 `safe_workspace_filename` 清洗
- 重名走 `unique_workspace_target` 追加 `__1` / `__2` / ...
- 临时文件用 `shutil.move` 跨盘兼容(不是 `os.replace`,因为 Windows 跨盘会失败)
- `api.py` 不复制 `WORKSPACE_ROOT` 到本地变量,每次访问用 `guard.WORKSPACE_ROOT` — 测试可 monkeypatch 实时生效

**实施中发现的关键 bug**:
- 原本 `tempfile.mkstemp(dir=workspace)` 把 tmp 写到 workspace 内
- quota 检查时 `_workspace_size_bytes(workspace)` 把"正在写入的 tmp"也算进去 → 重复计数
- **修法**: tmp 写到系统 temp dir,`shutil.move` 跨盘移动

**测试**: `tests/test_workspace_api.py` 28 个 case
- 上传成功 (`.docx` PK 头 / `.md` 无魔数 / 多文件)
- 错误处理 (坏扩展名 / 坏魔数 / 超大 / quota 超 / 不存在 session / 坏文件名 / 路径分隔符 / 隐藏文件)
- 列表 / 删除 / 清空
- env flag 控制
- 子目录文件 `path` 字段

**回归**: 138 + 37 + 28 = 203 passed, 1 skipped

---

## 阶段 2b: zip 流式解压 + zip slip + zip bomb 防御 (commit `720d130`)

**做了什么**: upload endpoint 加 `.zip` 分支,自动解压到 `workspace/<zip_stem>/` 子目录。zip 文件本身不保留,只留解压后的内容。

**三重防御**:

| 威胁 | 防御 | 实现 |
|---|---|---|
| **zip slip** (路径穿越) | 拒绝 `..` 段 / 绝对路径 / UNC 路径 entry | 遍历 `infolist()` 逐个检查 `Path(entry.filename).parts` |
| **zip bomb (单 entry)** | 拒绝压缩比 > 100:1 | `entry.file_size / entry.compress_size > 100` 即拒 |
| **zip bomb (累加)** | 累加解压后字节数,超 `QUOTA_BYTES` 回滚 | 流式写时累加 `decompressed_so_far`,超限 `raise + rmtree(target_dir)` |
| **DOS via 大量 entry** | 拒绝 entry 数 > 10000 | 进入循环前 check |

**为什么不用 `extractall`**:
- 它无法在解压前准确预估解压后大小(zip header 里的 size 可被篡改)
- 不能流式,容易 OOM
- 不能逐 entry 拦截 zip slip

**为什么流式**:
- `zipfile.open(entry)` + `shutil.copyfileobj` 边读边写,内存只占一个 chunk
- `decompressed_so_far` 累加基于 `entry.file_size` (zip 中央目录声明,可能篡改 — 但我们还有单 entry 比例检查兜底)

**响应字段**: 每个解压出的 entry 加 `extracted_from` 标记来源 zip 文件名,前端可追溯。

**测试**: `tests/test_workspace_api.py::TestZipExtract` 9 个 case
- 正常 zip 解压 (2 个 entry 到子目录)
- zip 内子目录 entry (`subdir/inner.txt`)
- zip slip `..` 段拒绝
- zip slip 绝对路径 (`/etc/passwd`) 拒绝
- zip bomb 高压缩比拒绝
- 解压后超 quota 拒绝 + 回滚验证(列出为空)
- 同名 zip 重名 → 子目录 `__1`
- 损坏 zip 拒绝
- 解压后 GET /workspace 列出所有 entry

**回归**: 203 + 9 = 212 passed, 1 skipped

---

## 阶段 3a: basic_tools 沙箱化 (commit `f4e87f2`)

**做了什么**: 3 个 basic_tools 工具加 `session_id` 隐式注入 + 走 `resolve_workspace_path`。

**修改**:
- `src/basic_tools/ls.py`: 默认 `path` 改 workspace 根, 走 resolver `must_exist=True, must_be_dir=True`
- `src/basic_tools/read.py`: `file_path` 走 resolver `must_exist=True, must_be_file=True`, 保留原 10MB / 编码检测 / 行号逻辑
- `src/basic_tools/analyze_image_content.py`: `image_path` 走 resolver + 加 10MB cap (与 read 对齐)
- `src/agent.py`: SESSION_TOOLS 从 6 扩展到 9 (+ls/read/analyze_image_content)

**关键设计点**:
- `session_id` **不**出现在 `tools_schema` 里 (避坑 1: LLM 不可见, dispatcher 隐式注入)
- 本想加 session_id 到 schema, 老测试 `test_llm_sees_no_session_id_in_tools_schema` 立即拒绝 — 修正保持与 `write_markdown_draft` 等老 session tool 一致
- `test_dispatcher_skips_non_session_tools` 改用 `set_text_format` (未沙箱化的 docx 写入工具) 做"非 session tool"测试样本

**回归**: 212 passed, 1 skipped

---

## 阶段 3b: md_tools 沙箱化 + draft_path 重构 (commit `c122b6b`)

**做了什么**: 6 个 md_tools 工具 (`read/write/parse_markdown_draft` / `markdown_to_word` / `apply_markdown_ir_after_paragraph` / `apply_markdown_ir_to_table_cell`) 走 `resolve_workspace_path`,并把 `draft_path` 改成 resolver 薄包装。

**关键改动**:

| 文件 | 改动 |
|---|---|
| `src/md_tools/common.py` | `draft_path` 改用 `resolve_workspace_path(session_id, "drafts/" + basename, must_exist=False)`; 保留 .. 段 / 绝对路径 显式守卫 (在 basename 之前, 符合老 test 期望的"越界"消息); `read_markdown_text` 走 resolver must_exist=True, must_be_file=True |
| `read_markdown_draft.py` | 删 `session_dir = Path("out") / "sessions" / session_id` 局部拼接, 用 `read_markdown_text(session_id, markdown_path)` |
| `write_markdown_draft.py` | 同上, `draft_path(session_id, output_path)` |
| `parse_markdown_draft.py` | 同 read |
| `apply_markdown_ir_after_paragraph.py` | 同 read |
| `apply_markdown_ir_to_table_cell.py` | 同 read |

**新签名**: `draft_path(session_id, raw_path)` 替代旧 `(path, session_dir)`, `read_markdown_text(session_id, raw_path)` 同样。

**测试适配**:
- `tests/test_step4.py` 路径断言从 `session_dir/drafts/` 改为 `session_workspace/drafts/` (新结构: workspace 是 session 下的子目录)
- 显式 mock `workspace.guard.WORKSPACE_ROOT` → `TMP_DIR`
- `draft_path` 调用改用新签名

**回归**: 212 passed, 1 skipped

---

## 阶段 3c: docx_tools 读类沙箱化 (待 commit)

**做了什么**: 4 个 docx 读类工具加 `session_id` 注入 + resolver 沙箱化。

**修改**:

| 工具 | 路径参数 | resolver 行为 |
|---|---|---|
| `read_docx_structure` | `docx_path` | `must_exist=True, must_be_file=True` |
| `find_text` | `docx_path` | 同上 |
| `analyze_docx_style_samples` | `docx_path` + `output_profile_path` | docx 读; profile 走 `workspace/style_profiles/` 子目录 (保留旧 `_resolve_profile_path` 强制重定向) |
| `diff_docx` | `before_docx` + `after_docx` | 两个都走 resolver `must_exist=True, must_be_file=True` |

**SESSION_TOOLS 扩展**: 9 → 12 (+ read_docx_structure / find_text / diff_docx)
- `analyze_docx_style_samples` 已在 SESSION_TOOLS (老)

**关键设计**:
- 4 个工具的 `tools_schema` 描述里 `docx_path` 注明"相对 workspace 根",提示 LLM 用相对路径
- `analyze_docx_style_samples` 的 `_resolve_profile_path` 改用 `workspace_dir(session_id) / "style_profiles"`,profile 文件名仍用 `Path(output_profile_path).name` (basename 化防越界)

**测试适配**:
- `test_analyze_style_samples_writes_profile_to_session_sandbox` 把 test docx 移到 `TMP_DIR / out / sessions / sess-style-1 / workspace / test_template.docx`,传相对路径 `"test_template.docx"`
- profile 路径断言从 `session_dir/style_profiles/` 改为 `session_workspace/style_profiles/`

**回归**: 212 passed, 1 skipped

---

## 阶段 3d: docx_tools 写入类沙箱化 (commit `edca4b1`, 19 工具)

**做了什么**: 19 个 docx 写入工具加 `session_id` 注入 + resolver 沙箱化。

**修改工具清单**:
insert_text_at / insert_text_in_table_cell / insert_table_row_after /
set_paragraph_indent / insert_table_after_paragraph /
insert_table_in_cell / insert_table_column_after /
merge_table_cells_horizontal / clear_table_cell / delete_table_row /
replace_table_cell_text / replace_text / delete_text /
insert_paragraph_after / set_text_format / replace_text_like_sample /
insert_paragraph_after_like_sample / replace_table_cell_like_sample /
insert_image_after_paragraph

**实现方式**: 写了一个 batch 脚本 `scripts/sandbox_docx_writers.py` 用 regex 批量给每个工具加:
1. `from .common` 导入 `resolve_docx_io`
2. 函数签名加 `session_id: str` 作为第一参数
3. 函数体顶部加 `input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)`
4. 替换 `load_document_xml(docx_path)` → `load_document_xml(str(input_path))`
5. 替换 `write_document_xml(docx_path, output_path, ...)` → `write_document_xml(str(input_path), str(output_path_resolved), ...)`
6. json_result 中 `"docx_path": docx_path` → `"docx_path": str(input_path)`
7. json_result 中 `"output_path": output_path` → `"output_path": str(output_path_resolved)`
8. tools_schema 描述加 "(相对 workspace 根)"

**SESSION_TOOLS 扩展**: 12 → 31 (19 写入类)

**新公共 helper** (`src/docx_tools/common.py`):
```python
def resolve_docx_io(session_id: str, docx_path: str, output_path: str):
    """v2: docx 工具统一解析输入/输出路径 (沙箱化)"""
    input_path = resolve_workspace_path(session_id, docx_path, must_exist=True, must_be_file=True)
    output_path_resolved = resolve_workspace_path(session_id, output_path, must_exist=False)
    return input_path, output_path_resolved
```

**实施中遇到的 bug 与修复**:
- batch 脚本 regex 错位: `input_path = ...` 插入到 docstring 内 (8 缩进), `load_document_xml` 行缩进变 0
- 写了 `scripts/fix_sandbox_indent.py` 第一轮修复 (修 8 缩进 → 4 缩进, root 行 0 → 4)
- 发现 `style_sample = load_style_sample(...)` 这类 0 缩进行没被处理, 再写 `scripts/fix_sandbox_indent2.py` 第二轮修复 (修复其他 0 缩进的 body 行)
- 最终 19 个文件全部修复

**测试适配**:
- `test_dispatcher_skips_non_session_tools` 改用 `bind_styles_to_roles` (style profile 工具, 未沙箱化) 做"非 session tool"测试样本 (Phase 3a 用 `set_text_format`, Phase 3c 改过, 这次再改)

**回归**: 212 passed, 1 skipped

---

## 阶段 3e: unzip_docx 沙箱化 (最高风险, 待 commit)

**做了什么**: `unzip_docx.py` 全重写, 路径沙箱化 + 多重防御。

**关键改动**:
- 函数签名加 `session_id: str` 作为第一参数
- `docx_path` 走 resolver `must_exist=True, must_be_file=True`
- `output_dir` 走 resolver `must_exist=False` **+ 强制父目录为 `workspace/unzipped/`** (LLM 只能传 `unzipped/run1`, 不能写到 workspace 根)
- **不用 `extractall`**, 改用 `zipfile.open()` + `shutil.copyfileobj` 流式写
- `overwrite=True` 策略: 把旧 `output_dir` 改名为 `output_dir_<timestamp>` 备份 (保 Agent 心流, 不断裂)
- `overwrite=False` 旧行为: 已存在则 400

**四重防御** (与 Phase 2b zip 流式解压同款):

| 防御 | 实现 |
|---|---|
| zip slip | 拒绝 `..` 段 / 绝对路径 / UNC 路径 entry |
| zip bomb (单 entry) | 拒绝压缩比 > 100:1 |
| zip bomb (累加) | 累加解压后字节数, 超 `guard.QUOTA_BYTES` 拒绝 + rmtree 回滚 |
| DOS | entry 数 > 10000 拒绝 |

**关键修复**: 用 `sys.modules["workspace.guard"].QUOTA_BYTES` qualified 访问 (不是 import-time 复制), 让测试 `monkeypatch.setattr(guard, "QUOTA_BYTES", ...)` 实时生效

**SESSION_TOOLS 扩展**: 31 → 32 (+ unzip_docx)

**测试**: `tests/test_unzip_docx_sandbox.py` 10 个 case
- 正常解压
- zip slip `..` 段 / 绝对路径拒绝
- output_dir 不在 unzipped/ 下拒绝
- output_dir `..` 越界拒绝
- output_dir 已存在 + overwrite=false 拒绝
- overwrite=true 创建时间戳备份
- 损坏 zip 拒绝
- quota 超限回滚无残骸
- 单 entry 高压缩比拒绝

**回归**: 222 passed, 1 skipped

---

## 阶段 4: 前端 WorkspacePanel + ChatHeader + page.tsx (待 commit)

**做了什么**: 前端加 WorkspacePanel 文件工作区 UI(镜像 PreviewPanel 的 slide-over 模式),允许用户上传 .docx / .zip / .png 等文件,选择 active docx,删除文件。

**新增/修改**:

| 文件 | 改动 |
|---|---|
| `frontend/components/workspace-panel.tsx` (新) | 镜像 `preview-panel.tsx` 风格, AnimatePresence + motion.div width 0↔50%; 空态显示 dashed drop zone (拖拽 + 点击); 非空显示文件列表 (radio 选 active + trash 删); 二次点击 trash 才真删 (5s 自动取消 confirm) |
| `frontend/components/chat-header.tsx` | 加 "文件 (N)" 按钮 (仅 currentSessionId 非空时显示), 接收 `showWorkspace` / `workspaceFileCount` / `onToggleWorkspace` props |
| `frontend/app/page.tsx` | 新增 `showWorkspace` / `workspaceFiles` / `activeDocxName` / `isUploading` state; 新增 `fetchWorkspace` / `uploadToWorkspace` / `deleteFromWorkspace` / `setActiveDocx` handlers; 集成 WorkspacePanel 在右侧 (与 PreviewPanel 同 slot 互斥) |

**关键设计**:

- **slide-over 模式**: WorkspacePanel 和 PreviewPanel 共用右侧 slot,互斥显示 (两个 show 状态独立 toggle)
- **active docx 选择**: 选 radio 只能选 .docx 文件 (其他文件类型 disabled, 提示"非 .docx 文件, 不可设为主文档")
- **上传 UI**: 顶部固定 "上传文件" 按钮 + 空态时大块 drop zone (拖拽 / 点击); `.zip` 上传提示"自动解压到子目录"
- **删除二次确认**: 第一次点 trash 变红, 5s 内第二次才真删 (避免误删)
- **后端 API 端点**:
  - `GET /api/sessions/{id}/workspace` 拉文件列表
  - `POST /api/sessions/{id}/upload` multipart 上传
  - `DELETE /api/sessions/{id}/workspace/{filename}` 删除单文件

**未在本 phase 实现** (按 plan 留 future):
- 在新建会话时主动用 workspace 中的 .docx 作为 start 消息的 `workspaceDocxName` (Phase 5 / 后续 phase)
- WS `set_active_docx` 消息 (用户提的 "active 中途切换" 也是 Phase 1 decision 中留 future)
- `use-agent-session.ts` 暂未改 (start 签名 + workspaceDocxName 在下个 phase 加)

**TypeScript 验证**: `npx tsc --noEmit` 通过 (EXIT 0)

**回归**: TypeScript 0 错误 (前端测试由 Phase 5 覆盖)

---

## 阶段 3c 修复 (commit 待合): read_docx_structure 函数体未沙箱化

**问题发现**: Phase 3c 当时只改了 `tools_schema` 描述 (commit `9b419e1` 实际 diff 只动 schema 4 行), 函数体本身没改。`read_docx_structure(docx_path, max_items=80)` 仍直接 `load_document_xml(docx_path)`,没有 session_id 注入 + resolver。

**修复**: 重写 `src/docx_tools/read_docx_structure.py`, 加 `session_id` 第一参 + `resolve_workspace_path(session_id, docx_path, must_exist=True, must_be_file=True)` + 用 `str(docx_path_resolved)` 调用 `load_document_xml`。错误返回 `json_result({"status":"error","code":e.code,"message":e.user_message})`。

**回归**: 234 passed, 1 skipped

---

## 阶段 5: 端到端 WS 测试 + 手动 smoke (待 commit)

**做了什么**: 写 `tests/test_workspace_e2e.py` 12 个 e2e case, 覆盖 4 个场景。不依赖真实 LLM, 走 HTTP endpoint + 工具直接调用, 验证沙箱链路 + 工具横切。

**4 个场景**:

| 场景 | case | 验证 |
|---|---|---|
| 沙箱链路 (4) | `test_upload_then_read_docx` | 上传 docx → read_docx_structure 读成功 |
| | `test_tool_blocks_absolute_path` | 工具拒绝 `C:\Windows\...` 绝对路径 |
| | `test_tool_blocks_traversal` | 工具拒绝 `../../etc/passwd` |
| | `test_delete_session_cascades_workspace` | 删 session → workspace 物理消失 |
| zip 链路 (3) | `test_malicious_zip_rejected` | 含 `../` 恶意 zip → 拒绝 + workspace 仍空 |
| | `test_normal_zip_extracts_and_md_readable` | 正常 zip 解压到子目录 |
| | `test_md_in_zip_subdir_readable_by_md_tool` | 验证 zip 解压内容可访问 |
| 工具链横切 (2) | `test_upload_analyze_read` | 上传 docx → analyze_docx_style_samples 沙箱成功 |
| | `test_write_then_read_md_draft` | write_markdown_draft → read_markdown_draft 走沙箱 |
| quota 链路 (3) | `test_quota_exhausted_upload_507` | 累计超 quota → 507 |
| | `test_delete_frees_quota` | 删除后 quota 释放 |
| | `test_max_file_size_enforced` | 单文件 > MAX_FILE_BYTES → 413 |

**手动 smoke 测试** (用户本地跑):
```bash
# 终端 1: 启动 backend
cd J:\学习\项目\文档agent
python src/server.py

# 终端 2: 启动 frontend
cd J:\学习\项目\文档agent\frontend
npm run dev

# 浏览器: http://localhost:3000
# 1. 新建会话
# 2. 点 "文件" 按钮
# 3. 拖入 test.docx
# 4. 选为 active docx
# 5. 在输入框发 "分析这个文档"
# 6. 观察 LLM 调工具 (read_docx_structure) 拿正确数据
# 7. 上传第二个 docx → 切 active → 再发 prompt
# 8. 重启 server → 该 session 的 workspace 还在 (持久化)
# 9. 故意在 prompt 写绝对路径 → LLM 工具应被 server 拒绝
```

**未在 Phase 5 实现** (按 plan 留 future):
- WS `set_active_docx` 消息 (用户提的"active 中途切换"也是 Phase 1 decision 中留 future)
- 启动时主动用 workspace 中的 .docx 作为 start 消息的 `workspaceDocxName` (前端 `use-agent-session.ts` 暂未改)

**回归**: 234 passed, 1 skipped

---
