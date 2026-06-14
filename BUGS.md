# BUGS — 项目已知 bug 记录

本文档记录回归测试在补齐过程中**发现**的预存 bug。**回归测试本身不修 bug**，只暴露——bug 的修复应该走单独的 commit。

每条 bug 包含: 复现命令、根本原因、影响范围、建议修法、相关测试。

---

## Bug #1: `delete_text` 工具 json_result 无法序列化 lxml `_Element`

**发现时间**: 2026-06-14
**发现途径**: `tests/test_text_ops.py` PR-1.1 — 22 个 case 中 4 个 delete_text 测试触发
**严重程度**: 高 — 工具调用直接抛 TypeError, 调用方拿不到任何结果
**影响范围**: 所有走 `delete_text` 工具的代码路径

### 复现

```python
import sys
sys.path.insert(0, "src")
from docx_tools.delete_text import delete_text

# 任何成功的 delete_text 调用都会抛 TypeError
result = delete_text(
    session_id="any", docx_path="in.docx", output_path="out.docx",
    target_text=" world",
)
# 抛: TypeError: Object of type _Element is not JSON serializable
```

### 根本原因

`src/docx_tools/common.py:21` 的 `json_result` 函数没有为 lxml `_Element` 注册 `default=` 处理器:

```python
def json_result(data) -> str:
    def _clean(val):
        if isinstance(val, str): ...
        elif isinstance(val, dict): return {k: _clean(v) for k, v in val.items()}
        elif isinstance(val, list): return [_clean(x) for x in val]
        return val  # ← _Element 走到这里, 原样返回, json.dumps 不知道怎么处理
    return json.dumps(cleaned_data, ensure_ascii=False, indent=2)
```

`delete_text` (src/docx_tools/delete_text.py:60) 把完整 `change` dict 塞进 result:

```python
"change": change,  # ← change 字段含 lxml 节点 (e.g. "<class 'lxml.etree._Element'>")
```

而 `replace_text` (line 73) 和 `insert_text_at` (line 90) **显式过滤了 `"run"` key**:

```python
change_for_result = {key: value for key, value in change.items() if key != "run"}
```

这就是为什么只有 `delete_text` 触发, 另两个不触发。

### 建议修法 (二选一)

**方案 A (最小改动)**: 在 `delete_text` 里加同样的过滤:
```python
# src/docx_tools/delete_text.py:60
"change": {k: v for k, v in change.items() if k != "run"},
```

**方案 B (治本)**: 让 `json_result` 注册 lxml 默认处理器:
```python
# src/docx_tools/common.py:21
def _etree_default(obj):
    if hasattr(obj, 'tag') and hasattr(obj, 'text'):  # lxml Element
        return f"<{obj.tag}>{obj.text or ''}</{obj.tag}>"
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def json_result(data) -> str:
    ...
    return json.dumps(cleaned_data, ensure_ascii=False, indent=2, default=_etree_default)
```

**推荐方案 A**: 改动面小, 跟 `replace_text` / `insert_text_at` 现有风格一致; 方案 B 风险较大 (lxml Element 含很多状态, 字符串化会丢信息)。

### 验证

修完后, 跑 `tests/test_text_ops.py` 的 `TestDeleteText` 5 个 case, JSON 字段断言 (`result["status"] == "ok"`) 会从 `if result is not None` 保护后自动激活。

### 相关测试

- `tests/test_text_ops.py::TestDeleteText` — 5 个 case
  - `test_basic_delete`
  - `test_cross_run_delete`
  - `test_trim_surrounding_spaces`
  - `test_text_not_found_returns_not_found` (not_found 路径不触发, 已 PASS)
  - `test_occurrence_selects_nth_match`

测试用 `_safe_call` helper (test_text_ops.py:42) 捕 TypeError 返回 None, JSON 断言条件激活, 文件 side effect 永远锁住核心行为。

---

## Bug #2: `set_paragraph_indent` 工具不解析 workspace 路径就传给底层 op

**发现时间**: 2026-06-14
**发现途径**: `tests/test_paragraph_format_ops.py` PR-1.2 — 准备测试时直接调工具触发
**严重程度**: 高 — 工具**根本无法工作**, 调一次 FileNotFoundError
**影响范围**: 所有走 `set_paragraph_indent` 工具的代码路径

### 复现

```python
import sys
sys.path.insert(0, "src")
from docx_tools.set_paragraph_indent import set_paragraph_indent

# 任何调用都抛 FileNotFoundError
result = set_paragraph_indent(
    session_id="any", docx_path="in.docx", output_path="out.docx",
    paragraph_index=1, left_twips=720,
)
# 抛: FileNotFoundError: [Errno 2] No such file or directory: 'in.docx'
```

### 根本原因

`src/docx_tools/set_paragraph_indent.py:19-26` 的 wrapper 调了 `resolve_docx_io` (line 17),
但**解析后的绝对路径没传给 op**, op 仍收到原始相对路径:

```python
# src/docx_tools/set_paragraph_indent.py:17-26
input_path, output_path_resolved = resolve_docx_io(session_id, docx_path, output_path)
# ↑ input_path 是绝对路径, 但下面传的还是 docx_path (相对)
try:
    result = set_paragraph_indent_op(
        docx_path=docx_path,          # ← BUG: 相对路径
        output_path=output_path,      # ← BUG: 相对路径
        paragraph_index=paragraph_index,
        left_twips=left_twips, ...
    )
```

而 `set_paragraph_indent_op` (src/docx_compiler/table_ops.py:9, 29) 用这两个相对路径做 I/O:

```python
# src/docx_compiler/table_ops.py:9
root = load_document_xml(docx_path)  # ← 打开 "in.docx", 找不到
# ...
# src/docx_compiler/table_ops.py:29
write_document_xml(docx_path, output_path, root)  # ← 写到 "out.docx", 写到 cwd 而非 workspace
```

对比正常工具 (`insert_paragraph_after`, `set_text_format` 等), wrapper 都用 `resolve_docx_io`
解析后再 `load_document_xml(str(input_path))` 和 `write_document_xml(str(input_path), str(output_path_resolved), root)`.

### 建议修法

修改 `src/docx_tools/set_paragraph_indent.py:19-26`, 传 `str(input_path)` / `str(output_path_resolved)`:

```python
result = set_paragraph_indent_op(
    docx_path=str(input_path),        # FIX: 用解析后的绝对路径
    output_path=str(output_path_resolved),  # FIX: 同上
    paragraph_index=paragraph_index,
    left_twips=left_twips, ...
)
```

### 验证

修完后, 跑 `tests/test_paragraph_format_ops.py` 的 `TestSetParagraphIndent` 5 个 case (它们当前都 `@pytest.mark.xfail`), 去掉 xfail 标记后应全过。

### 相关测试

- `tests/test_paragraph_format_ops.py::TestSetParagraphIndent` — 5 个 case, 全部 xfail
  - `test_left_indent_sets_w_ind_left`
  - `test_first_line_indent_sets_w_ind_first_line`
  - `test_hanging_indent_sets_w_ind_hanging`
  - `test_all_none_omits_w_ind`
  - `test_out_of_range_paragraph_index`

---

## 添加新 bug 条目的模板

```markdown
## Bug #N: <一句话描述>

**发现时间**: YYYY-MM-DD
**发现途径**: <哪个测试 / 哪个 PR>
**严重程度**: <高 / 中 / 低>
**影响范围**: <哪些代码路径 / 哪些用户场景>

### 复现
<code>

### 根本原因
<分析 + 文件:行 引用>

### 建议修法
<具体 patch>

### 验证
<修完跑哪个测试>

### 相关测试
<测试文件 + case 名>
```
