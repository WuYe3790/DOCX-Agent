# DOCX 替换、删除、新增段落源码变化记录

## Case

edit_text_002

## 待编辑文件

- `cases/edit_text_002/docx/实验报告10_edit_text_002.docx`
- `cases/edit_text_002/docx/实验报告模板_v3_edit_text_002.docx`

## 手动编辑步骤

### 1. 实验报告模板_v3_edit_text_002.docx

打开：

`cases/edit_text_002/docx/实验报告模板_v3_edit_text_002.docx`

执行以下编辑：

1. 找到蓝色标题行 `实验1*****`。
2. 删除标题中的 `*****`，保留 `实验1`。

预期用途：

- 标题删除：观察删除一个完整蓝色 run 后，Word/WPS 是否保留空 `<w:r>` 或直接移除 run。
- 删除测试没有新增可搜索文本，后续用标题文本 `实验1` 和原 `*****` 是否消失来定位变化。

3. 找到蓝色段落 `依据实验指导书`。
4. 选中整段 `依据实验指导书`。
5. 替换为：

```text
[REPLACE-TEXT-002-TEMPLATE-BLUE]
```

预期用途：

- 蓝色正文替换：观察整段替换时，新文本是否继承原蓝色格式。
- 检查替换后是复用原 `<w:r>`，还是删除原 run 后新增 run。

6. 找到黑色标题段落 `【实验心得】`。
7. 将光标放到该段落末尾。
8. 按 Enter 新增一段。
9. 在新增段落中输入：

```text
[INSERT-PARA-002-TEMPLATE-HEART]
```

预期用途：

- 新增段落：观察 Word/WPS 在两个已有段落之间插入 `<w:p>` 的位置。
- 观察新段落复制了前一段、后一段，还是当前输入位置的段落属性。

### 2. 实验报告10_edit_text_002.docx

打开：

`cases/edit_text_002/docx/实验报告10_edit_text_002.docx`

执行以下编辑：

1. 找到第二页表格中的 `RESTful API应用实践`。
2. 选中整句 `RESTful API应用实践`。
3. 替换为：

```text
[REPLACE-TEXT-002-REPORT-TITLE]
```

预期用途：

- 表格单元格替换：观察表格内已有文本被整体替换时，run 和单元格结构如何变化。
- 检查新文本是否继承原实验名称的加粗、字号等格式。

## 保存要求

编辑完成后：

1. 保存两个 `.docx`。
2. 关闭 Word/WPS。
3. 告诉我你已经保存完成。

关闭文档后再解包，避免文件还被编辑器占用或尚未完整写回磁盘。

## 建议插入标记

- `[REPLACE-TEXT-002-TEMPLATE-BLUE]`
- `[INSERT-PARA-002-TEMPLATE-HEART]`
- `[REPLACE-TEXT-002-REPORT-TITLE]`

删除测试标记：

- `[DELETE-TEXT-002-TEMPLATE-STARS]`

说明：

- `[DELETE-TEXT-002-TEMPLATE-STARS]` 只是测试项名称，不需要输入到文档里。
- 删除测试通过观察 `实验1*****` 是否变成 `实验1` 来定位变化。

## 编辑操作记录

### 实验报告10

- 将表格中的 `RESTful API应用实践` 替换为 `[REPLACE-TEXT-002-REPORT-TITLE]`。

### 实验报告模板_v3

- 删除蓝色标题 `实验1*****` 中的 `*****`。
- 将蓝色段落 `依据实验指导书` 替换为 `[REPLACE-TEXT-002-TEMPLATE-BLUE]`。
- 在 `【实验心得】` 后新增一段 `[INSERT-PARA-002-TEMPLATE-HEART]`。

## 源码变化分析

已解包：

- `cases/edit_text_002/unzipped/实验报告10_after`
- `cases/edit_text_002/unzipped/实验报告模板_v3_after`

基线目录：

- `cases/edit_text_002/unzipped/实验报告10_before`
- `cases/edit_text_002/unzipped/实验报告模板_v3_before`

### 总体结论

本次是纯文字替换、删除和新增段落，没有新增图片、超链接、样式定义或关系项。

核心业务变化都在：

- `word/document.xml`

未变化：

- `word/_rels/document.xml.rels`
- `[Content_Types].xml`
- `word/media/image1.jpeg`

Word/WPS 保存时仍然会重写一些非业务文件。做文档编辑 agent 的 diff 工具时，这类文件应优先当作保存噪声处理，除非用户明确编辑了对应内容：

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

- `word/document.xml`: 15961 字节 -> 16354 字节，增加 393 字节。
- 段落数增加：22 -> 23。
- run 数不变：22 -> 22。
- 文本节点数不变：22 -> 22。
- 表格数不变：0 -> 0。
- `word/_rels/document.xml.rels` 未变化。

节点数量说明：

- 新增段落增加了 1 个 run 和 1 个文本节点。
- 删除标题星号减少了 1 个 run 和 1 个文本节点。
- 所以最终 run/text 节点总数不变。

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

- `word/document.xml`: 66950 字节 -> 67614 字节，增加 664 字节。
- 段落数不变：111 -> 111。
- run 数减少：138 -> 137。
- 文本节点数减少：136 -> 135。
- 表格数不变：3 -> 3。
- `word/_rels/document.xml.rels` 未变化。
- 图片文件 `word/media/image1.jpeg` 未变化。

节点数量说明：

- `RESTful API应用实践` 原来由 2 个 run 组成。
- 替换后变成 1 个 run。
- 所以 run/text 节点各减少 1 个。

## 编辑点源码定位

### 实验报告模板_v3：删除标题星号

删除内容：

```text
*****
```

删除前段落文本：

```text
实验1*****
```

删除后段落文本：

```text
实验1
```

定位：

- 全文第 1 个段落节点。
- 非表格段落。

删除前 run 分布：

- R1: `实验`，加粗，字号 `44/28`。
- R2: `1`，蓝色 `0000FF`，加粗，字号 `44/28`。
- R4: `*****`，蓝色 `0000FF`，加粗，字号 `44/28`。

删除后 run 分布：

- R1: `实验`，加粗，字号 `44/28`。
- R2: `1`，蓝色 `0000FF`，加粗，字号 `44/28`。

工具参考：

- Word/WPS 删除完整占位星号时，直接移除了包含 `*****` 的 run。
- 没有留下空 `<w:t>` 或空 `<w:r>`。
- 删除工具应优先清理空文本 run，避免保留不可见噪声节点。

### 实验报告模板_v3：替换蓝色占位文本

替换后内容：

```text
[REPLACE-TEXT-002-TEMPLATE-BLUE]
```

定位：

- 全文第 8 个段落节点。
- 非表格段落。

替换前段落文本：

```text
依据实验指导书
```

替换前 run 分布：

- R1: `依据实验指导书`，蓝色 `0000FF`，字号 `szCs=21`。

替换后段落文本：

```text
[REPLACE-TEXT-002-TEMPLATE-BLUE]
```

替换后 run 分布：

- R1: `[REPLACE-TEXT-002-TEMPLATE-BLUE]`，蓝色 `0000FF`，字号 `szCs=21`。

工具参考：

- 整段替换复用了原 run 的格式。
- 原文本所在 run 的 `<w:t>` 内容被替换成新文本。
- 对单 run 完整替换，工具可以直接改该 run 的 `<w:t>`，无需新增 run。

### 实验报告模板_v3：在实验心得后新增段落

新增内容：

```text
[INSERT-PARA-002-TEMPLATE-HEART]
```

定位：

- 新增段落为全文第 22 个段落节点。
- 非表格段落。
- 插入在 `【实验心得】` 后、原蓝色提示段落前。

新增前局部段落：

```text
P21: 【实验心得】
P22: 出现问题、解决方法、体会等，一般不超过200字。
```

新增后局部段落：

```text
P21: 【实验心得】
P22: [INSERT-PARA-002-TEMPLATE-HEART]
P23: 出现问题、解决方法、体会等，一般不超过200字。
```

新增段落 run 分布：

- R1: `[INSERT-PARA-002-TEMPLATE-HEART]`，加粗，字号 `szCs=21`。

工具参考：

- Word/WPS 在两个已有段落之间插入了新的 `<w:p>`。
- 原蓝色提示段落整体后移。
- 新段落继承了 `【实验心得】` 附近的黑色加粗格式，而不是后面蓝色提示段落的蓝色格式。
- 新增段落工具需要明确“复制前一段格式”还是“复制后一段格式”，否则输出格式会依赖光标位置。

### 实验报告10：替换表格单元格文本

替换后内容：

```text
[REPLACE-TEXT-002-REPORT-TITLE]
```

定位：

- 全文第 24 个段落节点。
- `body` 第 2 个表格。
- 最近表格第 1 行、第 2 个单元格。

替换前段落文本：

```text
RESTful API应用实践
```

替换前 run 分布：

- R1: `RESTful API`，加粗，字号 `22/22`。
- R2: `应用实践`，加粗，字号 `22/22`。

替换后段落文本：

```text
[REPLACE-TEXT-002-REPORT-TITLE]
```

替换后 run 分布：

- R1: `[REPLACE-TEXT-002-REPORT-TITLE]`，加粗，字号 `22/22`。

工具参考：

- 跨两个 run 的整句替换后，Word/WPS 合并成了一个 run。
- 新 run 继承了原文本的共同格式：加粗、字号 `22/22`。
- 替换工具需要支持“逻辑文本跨 run 命中”，不能只在单个 `<w:t>` 内查找。
- 当被替换范围覆盖多个同格式 run 时，可以用第一个 run 的格式创建替换 run，并移除被覆盖的后续 run。

## 对工具设计的直接建议

1. 替换工具必须基于段落逻辑文本定位。

   先把一个段落内的所有 `<w:t>` 拼接成完整文本，再建立字符偏移到 run/text 节点的映射。这样才能处理 `RESTful API应用实践` 这种跨 run 替换。

2. 完整覆盖一个 run 时，优先复用原 run。

   `依据实验指导书` 替换成 `[REPLACE-TEXT-002-TEMPLATE-BLUE]` 时，Word/WPS 保留了原 run 格式，只替换 `<w:t>` 内容。

3. 跨多个同格式 run 替换时，可以合并为一个 run。

   `RESTful API` + `应用实践` 被替换后变成一个加粗 run。工具可以复制第一个 run 的 `<w:rPr>`，写入新 `<w:t>`，然后删除后续被覆盖 run。

4. 删除工具要清理空 run。

   删除 `*****` 后，Word/WPS 没有保留空 run。工具删除文本后也应移除空 `<w:t>` 所在 run，除非该 run 包含图片、制表符、换行等非文本内容。

5. 新增段落要显式控制格式来源。

   本次新增段落继承了前一段 `【实验心得】` 的黑色加粗格式，而不是后一段蓝色提示格式。工具设计应提供类似参数：

   - `style_source="previous"`
   - `style_source="next"`
   - `style_source="empty"`

