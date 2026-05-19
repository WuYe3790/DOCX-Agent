# DOCX 文字格式编辑源码变化记录

## Case

format_text_003

## 待编辑文件

- `cases/format_text_003/docx/实验报告10_format_text_003.docx`
- `cases/format_text_003/docx/实验报告模板_v3_format_text_003.docx`

## 手动编辑步骤

### 1. 实验报告模板_v3_format_text_003.docx

打开：

`cases/format_text_003/docx/实验报告模板_v3_format_text_003.docx`

执行以下格式编辑：

1. 找到蓝色段落 `依据实验指导书`。
2. 选中整段 `依据实验指导书`。
3. 替换为：

```text
[FMT-003-BODY-FROM-BLUE]
```

4. 将这段新文本设置为正式正文格式：
   - 字体颜色：黑色。
   - 取消加粗。
   - 保持正文大小，不使用蓝色占位符效果。

预期用途：

- 观察“蓝色占位符替换成正式正文”时，Word/WPS 如何移除 `<w:color w:val="0000FF"/>`。
- 观察正文格式是直接删除 run 级颜色，还是写入黑色 `<w:color w:val="000000"/>`。

5. 找到蓝色标题行 `实验1*****`。
6. 选中 `*****`。
7. 替换为：

```text
[FMT-003-TITLE-KEEP]
```

8. 保持它的标题格式：
   - 仍然蓝色。
   - 仍然加粗。
   - 仍然保持标题字号。

预期用途：

- 观察“标题占位符替换但保留格式”时，是否只是替换 `<w:t>`。
- 对比正式正文替换和标题占位替换的格式策略差异。

9. 找到黑色字段 `姓名`。
10. 在 `姓名` 后输入：

```text
[FMT-003-BOLD]
```

11. 只选中 `[FMT-003-BOLD]`，设置为加粗。

预期用途：

- 观察普通文本局部加粗时，Word/WPS 是新增 `<w:b/>`，还是拆分 run。
- 后续可用于设计 `set_text_format(bold=true)`。

12. 找到 `【实验心得】` 后面的蓝色提示段落 `出现问题、解决方法、体会等，一般不超过200字。`。
13. 在该提示段落后按 Enter 新增一段。
14. 输入：

```text
[FMT-003-CUSTOM-COLOR-SIZE]
```

15. 只选中这段新文本，设置：
   - 字体颜色：红色。
   - 字号：小四或 12 磅。
   - 不加粗。

预期用途：

- 观察明确指定颜色和字号时，`<w:color>`、`<w:sz>`、`<w:szCs>` 如何变化。
- 后续可用于设计自定义格式参数。

### 2. 实验报告10_format_text_003.docx

打开：

`cases/format_text_003/docx/实验报告10_format_text_003.docx`

执行以下格式编辑：

1. 找到第二页表格中的 `RESTful API应用实践`。
2. 选中整句 `RESTful API应用实践`。
3. 替换为：

```text
[FMT-003-TABLE-BODY]
```

4. 将这句新文本设置为普通正文格式：
   - 字体颜色：黑色。
   - 取消加粗。
   - 字号调整为正文大小。

预期用途：

- 观察表格单元格中“标题格式替换为正文格式”时，run 属性如何变化。
- 对比表格内格式清理和普通段落格式清理是否一致。

5. 找到 `四、给出实验过程、结果和讨论，并注明实现过程中遇到的问题。`。
6. 在这句话后面按 Enter 新增一段。
7. 输入：

```text
[FMT-003-REPORT-NEW-BODY]
```

8. 将新增段落设置为普通正文格式：
   - 黑色。
   - 不加粗。
   - 正文字号。

预期用途：

- 观察报告大表格单元格中新增正文段落的格式来源。
- 后续可用于决定 `insert_paragraph_after` 的 `format_policy` 默认值。

## 保存要求

编辑完成后：

1. 保存两个 `.docx`。
2. 关闭 Word/WPS。
3. 告诉我你已经保存完成。

关闭文档后再解包，避免文件还被编辑器占用或尚未完整写回磁盘。

## 建议插入标记

- `[FMT-003-BODY-FROM-BLUE]`
- `[FMT-003-TITLE-KEEP]`
- `[FMT-003-BOLD]`
- `[FMT-003-CUSTOM-COLOR-SIZE]`
- `[FMT-003-TABLE-BODY]`
- `[FMT-003-REPORT-NEW-BODY]`

## 编辑操作记录

### 实验报告10

- 将 `RESTful API应用实践` 替换为 `[FMT-003-TABLE-BODY]`，并设置为普通正文格式。
- 在 `四、给出实验过程、结果和讨论，并注明实现过程中遇到的问题。` 后新增一段 `[FMT-003-REPORT-NEW-BODY]`，并设置为普通正文格式。

### 实验报告模板_v3

- 将蓝色段落 `依据实验指导书` 替换为 `[FMT-003-BODY-FROM-BLUE]`，并设置为黑色普通正文格式。
- 将标题中的 `*****` 替换为 `[FMT-003-TITLE-KEEP]`，并保留标题蓝色加粗格式。
- 在 `姓名` 后输入 `[FMT-003-BOLD]`，并只将该标记设置为加粗。
- 在实验心得提示段落后新增 `[FMT-003-CUSTOM-COLOR-SIZE]`，并设置为红色、小四或 12 磅、不加粗。

## 源码变化分析

待解包并对比：

- `word/document.xml`
- `word/_rels/document.xml.rels`
- `docProps/core.xml`
- `docProps/app.xml`

