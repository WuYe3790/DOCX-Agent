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
   - 保持正文大小，不使用蓝色占位符效果。

预期用途：

- 观察“蓝色占位符替换成正式正文”时，Word/WPS 如何移除 `<w:color w:val="0000FF"/>`。
- 观察正文格式是直接删除 run 级颜色，还是写入黑色 `<w:color w:val="000000"/>`。
注意：原段落本来不加粗，所以这里不测试加粗变化，只测试蓝色占位符转黑色正文。

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

9. 在 `[FMT-003-BODY-FROM-BLUE]` 后面继续输入：

```text
[FMT-003-BOLD]
```

10. 只选中 `[FMT-003-BOLD]`，设置为加粗。

预期用途：

- 观察同一普通正文段落中，局部加粗时 Word/WPS 是新增 `<w:b/>`，还是拆分 run。
- 后续可用于设计 `set_text_format(bold=true)`。

11. 找到 `【实验心得】` 后面的蓝色提示段落 `出现问题、解决方法、体会等，一般不超过200字。`。
12. 在该提示段落后按 Enter 新增一段。
13. 输入：

```text
[FMT-003-CUSTOM-COLOR-SIZE]
```

14. 只选中这段新文本，设置：
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
- 在 `[FMT-003-BODY-FROM-BLUE]` 后输入 `[FMT-003-BOLD]`，并只将该标记设置为加粗。
- 在实验心得提示段落后新增 `[FMT-003-CUSTOM-COLOR-SIZE]`，并设置为红色、小四或 12 磅、不加粗。

## 源码变化分析

已解包：

- `cases/format_text_003/unzipped/实验报告10_after`
- `cases/format_text_003/unzipped/实验报告模板_v3_after`

基线目录：

- `cases/format_text_003/unzipped/实验报告10_before`
- `cases/format_text_003/unzipped/实验报告模板_v3_before`

### 总体结论

本次是文字格式编辑，没有新增图片、超链接或关系项。

核心业务变化都在：

- `word/document.xml`

未变化：

- `word/_rels/document.xml.rels`
- `[Content_Types].xml`
- `word/media/image1.jpeg`

Word/WPS 保存时仍然会重写一些非业务文件。做文档编辑 agent 的 diff 工具时，这类文件应优先当作保存噪声处理：

- `docProps/app.xml`
- `docProps/core.xml`
- `word/settings.xml`
- `word/styles.xml`
- `word/fontTable.xml`
- `word/footnotes.xml`
- `word/endnotes.xml`
- `word/footer*.xml`
- `word/numbering.xml`
- `word/webSettings.xml`

### 变化文件清单

#### 实验报告模板_v3

有哈希变化的文件：

- `docProps/app.xml`
- `docProps/core.xml`
- `word/document.xml`
- `word/endnotes.xml`
- `word/fontTable.xml`
- `word/footer1.xml`
- `word/footer2.xml`
- `word/footnotes.xml`
- `word/settings.xml`
- `word/styles.xml`

核心变化：

- `word/document.xml`: 15961 字节 -> 17054 字节，增加 1093 字节。
- 段落数增加：22 -> 23。
- run 数增加：22 -> 26。
- 文本节点数增加：22 -> 26。
- 表格数不变：0 -> 0。
- `word/_rels/document.xml.rels` 未变化。

#### 实验报告10

有哈希变化的文件：

- `customXml/item1.xml`
- `customXml/item2.xml`
- `customXml/itemProps1.xml`
- `customXml/itemProps2.xml`
- `docProps/app.xml`
- `docProps/core.xml`
- `word/document.xml`
- `word/endnotes.xml`
- `word/fontTable.xml`
- `word/footer1.xml`
- `word/footnotes.xml`
- `word/numbering.xml`
- `word/settings.xml`
- `word/styles.xml`
- `word/webSettings.xml`

核心变化：

- `word/document.xml`: 66950 字节 -> 68012 字节，增加 1062 字节。
- 段落数增加：111 -> 112。
- run 数不变：138 -> 138。
- 文本节点数不变：136 -> 136。
- 表格数不变：3 -> 3。
- `word/_rels/document.xml.rels` 未变化。
- 图片文件 `word/media/image1.jpeg` 未变化。

## 格式编辑源码定位

### 实验报告模板_v3：蓝色占位转黑色正文

替换后内容：

```text
[FMT-003-BODY-FROM-BLUE]
```

定位：

- 全文第 8 个段落节点。
- 非表格段落。

替换后段落文本：

```text
[FMT-003-BODY-FROM-BLUE][FMT-003-BOLD]
```

run 分布：

- R1: `[FMT-003-BODY-FROM-BLUE]`，无显式颜色，字号 `szCs=21`。
- R2: 空文本 run，无 `rPr`。
- R3: `[FMT-003-BOLD]`，加粗 `w:b` 和 `w:bCs`，字号 `szCs=21`。

工具参考：

- 蓝色占位符变成黑色正文时，Word/WPS 不是写入 `<w:color w:val="000000"/>`，而是移除了 run 级颜色属性。
- 如果要实现 `format_policy="body"` 或 `format_policy="clear"`，可以删除 `<w:color>`，让文本继承默认黑色。
- 局部加粗会拆出单独 run，并添加 `<w:b/>` 和 `<w:bCs/>`。
- 手动编辑留下了一个空文本 run，工具层应继续清理空 `<w:t>` / 空 `<w:r>`。

### 实验报告模板_v3：标题占位保留标题格式

替换后内容：

```text
[FMT-003-TITLE-KEEP]
```

定位：

- 全文第 1 个段落节点。
- 非表格段落。

替换后段落文本：

```text
实验1[FMT-003-TITLE-KEEP]
```

run 分布：

- R1: `实验`，加粗，字号 `44/28`。
- R2: `1`，蓝色 `0000FF`，加粗，字号 `44/28`。
- R4: `[FMT-003-TITLE-KEEP]`，蓝色 `0000FF`，加粗，字号 `44/28`。

工具参考：

- 标题占位符替换且保留格式时，新文本继续使用原蓝色、加粗、标题字号。
- 这对应 `format_policy="preserve"`。

### 实验报告模板_v3：自定义红色和字号

新增内容：

```text
[FMT-003-CUSTOM-COLOR-SIZE]
```

定位：

- 全文第 23 个段落节点。
- 非表格段落。
- 插入在原实验心得蓝色提示段落之后。

run 分布：

- R1: `[FMT-003-CUSTOM-COLOR-SIZE]`，颜色 `EE0000`，字号 `w:sz=24`，无加粗。

工具参考：

- 12 磅对应 `w:sz=24`，因为 WordprocessingML 字号单位是半磅。
- 这次只出现了 `w:sz=24`，没有看到对应 `w:szCs`。工具如果要稳妥设置中英文字号，应同时设置 `w:sz` 和 `w:szCs`。
- 自定义颜色可以直接写 `<w:color w:val="EE0000"/>`。

### 实验报告10：表格标题转普通正文

替换后内容：

```text
[FMT-003-TABLE-BODY]
```

定位：

- 全文第 24 个段落节点。
- `body` 第 2 个表格。
- 最近表格第 1 行、第 2 个单元格。

run 分布：

- R1: `[FMT-003-TABLE-BODY]`，无显式颜色，无 `w:b`，但仍有 `w:bCs`，字体 `Times New Roman / SimSun`。

工具参考：

- 从表格标题转正文时，Word/WPS 移除了普通加粗 `<w:b/>`。
- 但仍留下了 `<w:bCs/>`。这说明“取消加粗”不一定会清理所有加粗相关标签。
- 如果工具要彻底取消加粗，应同时移除 `<w:b>` 和 `<w:bCs>`。

### 实验报告10：表格内新增普通正文段落

新增内容：

```text
[FMT-003-REPORT-NEW-BODY]
```

定位：

- 全文第 88 个段落节点。
- `body` 第 2 个表格。
- 最近表格第 5 行、第 1 个单元格。
- 插入在 `四、给出实验过程、结果和讨论，并注明实现过程中遇到的问题。` 后面。

run 分布：

- R1: `[FMT-003-REPORT-NEW-BODY]`，无显式颜色，无加粗，字号 `szCs=22`，字体 `Times New Roman / SimSun`。

工具参考：

- 表格内新增正文段落可以是同一单元格中的新 `<w:p>`。
- 正文格式看起来主要是无颜色、无加粗，并继承表格中普通正文的字号和字体。
- 对 `insert_paragraph_after` 的正文策略，建议支持 `format_policy="body"`，避免复制标题段落的加粗格式。

## 对工具设计的直接建议

1. 写入工具需要 `format_policy`。

   建议给 `replace_text`、`insert_text_at`、`insert_text_in_table_cell`、`insert_paragraph_after` 增加参数：

   - `preserve`: 复制原 run 格式，适合标题占位符。
   - `clear`: 清除 run 级直接格式，适合从蓝色提示变正文。
   - `body`: 使用正文格式，至少移除颜色、加粗，并设置正文字号。
   - `custom`: 使用指定颜色、字号、加粗等参数。

2. 黑色正文不要强制写 `000000`。

   本次 Word/WPS 对蓝色转黑色的做法是移除 `<w:color>`。工具默认可以删除颜色属性，让文本继承默认黑色；只有用户明确指定黑色时再写 `000000`。

3. 取消加粗要同时处理 `w:b` 和 `w:bCs`。

   表格标题转普通正文后仍保留了 `w:bCs`。如果工具只删 `w:b`，可能在某些字体或语言场景中仍表现为加粗。

4. 设置字号时同时写 `w:sz` 和 `w:szCs`。

   Word/WPS 手动设置 12 磅只写了 `w:sz=24`。工具为了中英文一致，应同时写：

   ```xml
   <w:sz w:val="24"/>
   <w:szCs w:val="24"/>
   ```

5. 格式工具需要清理空 run。

   局部加粗编辑后出现了空文本 run。后续 `set_text_format` 或写入类工具应在操作后清理空文本 run，避免 XML 噪声累积。
