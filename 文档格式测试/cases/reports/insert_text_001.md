# DOCX 插入文字源码变化记录

## Case

insert_text_001

## 待编辑文件

- `cases/insert_text_001/docx/实验报告10_insert_text_001.docx`
- `cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx`

## 手动编辑步骤

### 1. 实验报告模板_v3_insert_text_001.docx

打开：

`cases/insert_text_001/docx/实验报告模板_v3_insert_text_001.docx`

执行以下插入：

1. 找到蓝色标题行 `实验1*****`。
2. 将光标放到 `*****` 后面。
3. 插入文本：

```text
[INS-TEXT-001-TEMPLATE-TITLE]
```

4. 找到蓝色段落 `依据实验指导书`。
5. 将光标放到 `依据` 和 `实验指导书` 中间。
6. 插入文本：

```text
[INS-TEXT-001-TEMPLATE-MID]
```

7. 找到黑色字段 `姓名`。
8. 将光标放到 `姓名` 后面。
9. 插入文本：

```text
[INS-TEXT-001-TEMPLATE-NAME]
```

预期用途：

- 标题插入：观察同一段落中蓝色 run 是否被拆分。
- 蓝色正文中间插入：观察同一格式文本中间插入时 `<w:t>` 是原地变化还是拆成多个 `<w:r>`。
- 黑色普通字段插入：对比普通文本和蓝色文本的源码变化差异。

### 2. 实验报告10_insert_text_001.docx

打开：

`cases/insert_text_001/docx/实验报告10_insert_text_001.docx`

执行以下插入：

1. 找到第二页表格中的 `RESTful API应用实践`。
2. 将光标放到这句话后面。
3. 插入文本：

```text
[INS-TEXT-001-REPORT-TITLE]
```

4. 找到 `请给出详细的设计流程图。`。
5. 将光标放到句号后面。
6. 插入文本：

```text
[INS-TEXT-001-REPORT-BODY]
```

7. 回到封面信息表，找到 `姓名：` 右侧的空白单元格。
8. 在空白单元格里插入文本：

```text
[INS-TEXT-001-REPORT-CELL]
```

预期用途：

- 实验名称插入：观察表格单元格中已有文本后追加内容的变化。
- 正文说明插入：观察大表格正文段落中的 run 变化。
- 空白单元格插入：观察原本空 `<w:p>` 里新增 `<w:r><w:t>` 的结构。

## 保存要求

编辑完成后：

1. 保存两个 `.docx`。
2. 关闭 Word/WPS。
3. 告诉我你已经保存完成。

关闭文档后再解包，避免文件还被编辑器占用或尚未完整写回磁盘。

## 建议插入标记

- `[INS-TEXT-001-TEMPLATE-TITLE]`
- `[INS-TEXT-001-TEMPLATE-MID]`
- `[INS-TEXT-001-TEMPLATE-NAME]`
- `[INS-TEXT-001-REPORT-TITLE]`
- `[INS-TEXT-001-REPORT-BODY]`
- `[INS-TEXT-001-REPORT-CELL]`

## 编辑操作记录

### 实验报告10

- 在 `RESTful API应用实践` 后插入 `[INS-TEXT-001-REPORT-TITLE]`。
- 在 `请给出详细的设计流程图。` 后插入 `[INS-TEXT-001-REPORT-BODY]`。
- 在封面 `姓名：` 右侧空白单元格插入 `[INS-TEXT-001-REPORT-CELL]`。

### 实验报告模板_v3

- 在蓝色标题 `实验1*****` 的 `*****` 后插入 `[INS-TEXT-001-TEMPLATE-TITLE]`。
- 在蓝色段落 `依据实验指导书` 的 `依据` 和 `实验指导书` 中间插入 `[INS-TEXT-001-TEMPLATE-MID]`。
- 在黑色字段 `姓名` 后插入 `[INS-TEXT-001-TEMPLATE-NAME]`。

## 源码变化分析

已解包：

- `cases/insert_text_001/unzipped/实验报告10`
- `cases/insert_text_001/unzipped/实验报告模板_v3`

基线目录：

- `cases/baseline/unzipped/实验报告10`
- `cases/baseline/unzipped/实验报告模板_v3`

### 总体结论

本次都是纯文字插入，没有新增图片、超链接、样式定义或关系项。

核心业务变化都在：

- `word/document.xml`

未变化：

- `word/_rels/document.xml.rels`
- `[Content_Types].xml`
- `word/media/image1.jpeg`

Word/WPS 保存时还会重写一些非业务文件。做文档编辑 agent 的 diff 工具时，这类文件应优先当作保存噪声处理，除非用户明确编辑了对应内容：

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

- `word/document.xml`: 66950 字节 -> 68396 字节，增加 1446 字节。
- 段落数不变：111 -> 111。
- run 数增加：138 -> 141。
- 文本节点数增加：136 -> 139。
- 表格数不变：3 -> 3。
- `word/_rels/document.xml.rels` 未变化。
- 图片文件 `word/media/image1.jpeg` 未变化。

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

- `word/document.xml`: 15961 字节 -> 17658 字节，增加 1697 字节。
- 段落数增加：22 -> 23。
- run 数增加：22 -> 29。
- 文本节点数增加：22 -> 29。
- 表格数不变：0 -> 0。
- `word/_rels/document.xml.rels` 未变化。

额外观察：

- 除计划中的 3 个模板插入点外，模板末尾还多了一个新段落 `[INS-TEXT-001-TEMPLATE-NEWLINE]`。
- 这个额外插入很好，可以作为“新增段落”的测试样本。

## 插入点源码定位

### 实验报告10：空白表格单元格插入

插入内容：

```text
[INS-TEXT-001-REPORT-CELL]
```

定位：

- 全文第 9 个段落节点。
- `body` 第 1 个表格。
- 最近表格第 1 行、第 2 个单元格。
- 原本是空 `<w:p>`，插入后新增一个 run。

新 run 摘要：

```xml
<w:r>
  <w:rPr>
    <w:sz w:val="21"/>
    <w:szCs w:val="21"/>
  </w:rPr>
  <w:t>[INS-TEXT-001-REPORT-CELL]</w:t>
</w:r>
```

工具参考：

- 对空单元格插字，不会新增表格、行、列。
- 变化通常是在原有空段落 `<w:p>` 中新增 `<w:r><w:t>...</w:t></w:r>`。

### 实验报告10：表格已有文本末尾插入

插入内容：

```text
[INS-TEXT-001-REPORT-TITLE]
```

定位：

- 全文第 24 个段落节点。
- `body` 第 2 个表格。
- 最近表格第 1 行、第 2 个单元格。

插入后段落文本：

```text
RESTful API应用实践[INS-TEXT-001-REPORT-TITLE]
```

run 分布：

- R1: `RESTful API`，加粗，字号 `22/22`。
- R2: `应用实践`，加粗，字号 `22/22`。
- R3: `[INS-TEXT-001-REPORT-TITLE]`，加粗，字号 `22/22`。

工具参考：

- 在已有文本末尾插入时，Word/WPS 没有把文本拼进原来的 `<w:t>`。
- 它新增了一个同格式 `<w:r>`。
- 插入 run 继承了当前位置格式：加粗、字号相同。

### 实验报告10：正文说明后插入

插入内容：

```text
[INS-TEXT-001-REPORT-BODY]
```

定位：

- 全文第 41 个段落节点。
- `body` 第 2 个表格。
- 最近表格第 4 行、第 1 个单元格。

插入后段落文本：

```text
请给出详细的设计流程图。[INS-TEXT-001-REPORT-BODY]
```

run 分布：

- R1: `请`，字号 `szCs=22`。
- R2: `给出详细的设计流程图。`，字号 `szCs=22`。
- R3: `[INS-TEXT-001-REPORT-BODY]`，字号 `szCs=22`。

工具参考：

- 末尾插入仍然新增 run。
- 原段落中已有的 run 拆分保持不变。
- 插入 run 的格式继承光标处格式。

### 实验报告模板_v3：蓝色标题末尾插入

插入内容：

```text
[INS-TEXT-001-TEMPLATE-TITLE]
```

定位：

- 全文第 1 个段落节点。
- 非表格段落。

插入后段落文本：

```text
实验1*****[INS-TEXT-001-TEMPLATE-TITLE]
```

run 分布：

- R1: `实验`，加粗，字号 `44/28`。
- R2: `1`，蓝色 `0000FF`，加粗，字号 `44/28`。
- R4: `*****`，蓝色 `0000FF`，加粗，字号 `44/28`。
- R5: `[INS-TEXT-001-TEMPLATE-TITLE]`，蓝色 `0000FF`，加粗，字号 `44/28`。

工具参考：

- 标题末尾插入新增了一个蓝色 run。
- 插入文本继承了前一个蓝色占位符的格式。
- 颜色仍是 `<w:color w:val="0000FF"/>`。

### 实验报告模板_v3：黑色普通字段末尾插入

插入内容：

```text
[INS-TEXT-001-TEMPLATE-NAME]
```

定位：

- 全文第 2 个段落节点。
- 非表格段落。

插入后段落文本：

```text
姓名  [INS-TEXT-001-TEMPLATE-NAME]
```

run 分布：

- R1: `姓名  `，加粗，字号 `28/28`。
- R2: `[INS-TEXT-001-TEMPLATE-NAME]`，加粗，字号 `28/28`。

工具参考：

- 普通黑色字段末尾插入也新增 run。
- 没有显式 `<w:color>`，显示颜色由默认样式决定。

### 实验报告模板_v3：蓝色正文中间插入

插入内容：

```text
[INS-TEXT-001-TEMPLATE-MID]
```

定位：

- 全文第 8 个段落节点。
- 非表格段落。

插入后段落文本：

```text
依据[INS-TEXT-001-TEMPLATE-MID]实验指导书
```

run 分布：

- R1: `依据`，蓝色 `0000FF`，字号 `szCs=21`。
- R2: `[INS-TEXT-001-TEMPLATE-MID]`，蓝色 `0000FF`，字号 `szCs=21`。
- R3: `实验指导书`，蓝色 `0000FF`，字号 `szCs=21`。

等价变化模式：

```xml
<!-- 原来近似是一个 run -->
<w:t>依据实验指导书</w:t>

<!-- 插入后变成三个连续 run -->
<w:t>依据</w:t>
<w:t>[INS-TEXT-001-TEMPLATE-MID]</w:t>
<w:t>实验指导书</w:t>
```

工具参考：

- 在一个 `<w:t>` 中间插入文字时，Word/WPS 会把原文本拆成前后两个 run。
- 插入内容作为中间的新 run。
- 三个 run 的格式保持一致。
- 这是文档编辑 agent 最需要支持的核心模式：对单个文本节点做中间插入时，不能假设仍是一个 `<w:t>`。

### 实验报告模板_v3：新增段落

插入内容：

```text
[INS-TEXT-001-TEMPLATE-NEWLINE]
```

定位：

- 全文第 23 个段落节点。
- 非表格段落。
- 出现在原正文末尾、`sectPr` 之前。

run 分布：

- R1: `[INS-TEXT-001-TEMPLATE-`
- R2: `NEWLINE`
- R3: `]`

工具参考：

- 新增段落会在 `<w:body>` 的 `sectPr` 之前插入新的 `<w:p>`。
- 一个连续输入的标记也可能被拆成多个 run。
- 不要用“一个插入字符串一定对应一个 `<w:t>`”作为工具假设。

## 对工具设计的直接建议

1. 文本定位不要只靠第几个 `<w:t>`。

   Word 会拆分 run，尤其是中文、英文、符号、输入法状态、格式继承发生变化时。更稳的方式是把段落内所有 `<w:t>` 拼接成逻辑文本，再维护字符偏移到 run 的映射。

2. 插入文字应支持三种模式。

   - 空段落或空单元格：新增 `<w:r><w:t>...</w:t></w:r>`。
   - 文本末尾：通常新增同格式 run。
   - 文本中间：拆分原 run，插入新 run，再保留后半段。

3. 格式继承应从光标位置附近的 run 获取。

   本次所有插入内容都继承了附近格式。例如蓝色区域继续是 `0000FF`，加粗标题继续加粗。

4. diff 时优先提取结构化语义。

   推荐输出：

   - 段落完整文本变化。
   - 表格位置：第几个表格、第几行、第几列。
   - run 变化：新增 run、拆分 run、格式继承。
   - 关系变化：图片、超链接、脚注等。

5. 保存噪声要过滤。

   只插入文本时，`styles.xml`、`settings.xml`、`fontTable.xml`、`footer*.xml` 等也可能被重写。不要把这些直接解释为用户编辑了样式或页脚。
