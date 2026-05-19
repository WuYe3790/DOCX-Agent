# DOCX 文本编辑工具测试记录

## Case

edit_text_002

## 目标

为后续新增的三个工具准备测试样本和源码对比记录：

- `replace_text`
- `delete_text`
- `insert_paragraph_after`

本 case 先准备测试文档区，后续每实现一个工具，就在这里记录工具输出和 `word/document.xml` 变化。

## 测试文档区

基线文档副本：

- `cases/edit_text_002/docx/实验报告模板_v3_edit_text_002.docx`
- `cases/edit_text_002/docx/实验报告10_edit_text_002.docx`

before 解包目录：

- `cases/edit_text_002/unzipped/实验报告模板_v3_before`
- `cases/edit_text_002/unzipped/实验报告10_before`

工具输出目录：

- `cases/edit_text_002/outputs`

## 测试 1：替换蓝色占位文本

目标工具：

- `replace_text`

输入文档：

- `cases/edit_text_002/docx/实验报告模板_v3_edit_text_002.docx`

操作：

把蓝色段落：

```text
依据实验指导书
```

替换为：

```text
本实验旨在验证 DOCX 文本替换工具。
```

输出文档：

- `cases/edit_text_002/outputs/replace_template_blue.docx`

预期观察：

- 主要变化在 `word/document.xml`。
- 目标段落文本整体替换。
- 新文本应继承原蓝色 run 格式，至少保留 `<w:color w:val="0000FF"/>`。
- 如果原文本被多个 `<w:r>` 拆分，工具也应能按逻辑文本替换。

## 测试 2：删除标题中的占位星号

目标工具：

- `delete_text`

输入文档：

- `cases/edit_text_002/docx/实验报告模板_v3_edit_text_002.docx`

操作：

删除标题中的：

```text
*****
```

输出文档：

- `cases/edit_text_002/outputs/delete_template_stars.docx`

预期观察：

- 主要变化在 `word/document.xml`。
- 标题从 `实验1*****` 变为 `实验1`。
- 删除后如果产生空 `<w:t>` 或空 `<w:r>`，工具应尽量清理。
- 不应删除标题段落、段落样式或其他蓝色文本。

## 测试 3：在实验心得标题后新增段落

目标工具：

- `insert_paragraph_after`

输入文档：

- `cases/edit_text_002/docx/实验报告模板_v3_edit_text_002.docx`

操作：

在段落：

```text
【实验心得】
```

后面新增段落：

```text
这是由 insert_paragraph_after 工具新增的实验心得内容。
```

输出文档：

- `cases/edit_text_002/outputs/insert_paragraph_template.docx`

预期观察：

- `word/document.xml` 中新增一个 `<w:p>`。
- 新段落应插入在 `【实验心得】` 后、原蓝色提示段落前。
- 新段落可复制锚点段落或下一段的段落属性，第一版只要求 docx 能正常打开且文本位置正确。

## 测试 4：替换表格单元格文本

目标工具：

- `replace_text`

输入文档：

- `cases/edit_text_002/docx/实验报告10_edit_text_002.docx`

操作：

把表格中的：

```text
RESTful API应用实践
```

替换为：

```text
DOCX 精细编辑工具实践
```

输出文档：

- `cases/edit_text_002/outputs/replace_report_table_title.docx`

预期观察：

- 主要变化在 `word/document.xml`。
- 目标位置在第二个正文表格的第 1 行第 2 个单元格。
- 替换文本应继承原单元格标题的加粗和字号。

