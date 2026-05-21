# DOCX 新建表格与表格操作源码变化记录

## Case

create_table_006

## 待编辑文件

- `cases/create_table_006/docx/实验报告10_create_table_006.docx`
- `cases/create_table_006/docx/实验报告模板_v3_create_table_006.docx`

## 手动编辑步骤

本轮测试的是在 Word/WPS 中新建表格，并继续对新表格做结构操作后，`.docx` 解包 XML 如何变化。

重点观察：

- 新建表格如何生成 `<w:tbl>`。
- 表格列宽是否写入 `<w:tblGrid>`。
- 新增行、列如何改变 `<w:tr>`、`<w:tc>`。
- 合并单元格如何表达。
- 删除行或列后，表格网格和行列结构如何变化。
- 在已有表格单元格中创建新表格时，是否形成嵌套 `<w:tbl>`。

### 1. 实验报告模板_v3_create_table_006.docx

打开：

`cases/create_table_006/docx/实验报告模板_v3_create_table_006.docx`

执行以下新建表格与表格操作：

#### 1.1 新建普通表格

1. 找到蓝色段落 `依据实验指导书`。
2. 将光标放到这段文字末尾。
3. 按一次 `Enter` 新增一段。
4. 通过 Word/WPS 的“插入表格”功能，插入一个 `3 列 x 4 行` 的表格。
5. 按下面内容填写表格：

```text
[TABLE-006-TEMPLATE-H1] | [TABLE-006-TEMPLATE-H2] | [TABLE-006-TEMPLATE-H3]
[TABLE-006-TEMPLATE-R1C1] | [TABLE-006-TEMPLATE-R1C2] | [TABLE-006-TEMPLATE-R1C3]
[TABLE-006-TEMPLATE-R2C1] | [TABLE-006-TEMPLATE-R2C2] | [TABLE-006-TEMPLATE-R2C3]
[TABLE-006-TEMPLATE-R3C1] | [TABLE-006-TEMPLATE-R3C2] | [TABLE-006-TEMPLATE-R3C3]
```

说明：

- 每个 `|` 代表换到右侧下一个单元格，不要把 `|` 字符输入到文档里。
- 第一行是表头行。

预期用途：

- 观察新建普通表格的基础 `<w:tbl>` 结构。
- 观察每一列是否生成 `<w:gridCol>`。
- 观察每个单元格是否至少包含一个 `<w:p>`。

#### 1.2 设置表头格式

1. 选中新表格第一行。
2. 设置为加粗。
3. 设置为居中。
4. 如果操作方便，将第一行底纹设置为浅灰色。

预期用途：

- 观察表头行格式是在 `<w:trPr>`、`<w:tcPr>`、段落属性还是 run 属性中表达。
- 观察底纹是否写入 `<w:shd>`。

#### 1.3 插入新行

1. 在 `[TABLE-006-TEMPLATE-R1C1]` 所在行下面插入一整行。
2. 在新行中填写：

```text
[TABLE-006-TEMPLATE-INSERT-ROW-C1] | [TABLE-006-TEMPLATE-INSERT-ROW-C2] | [TABLE-006-TEMPLATE-INSERT-ROW-C3]
```

预期用途：

- 观察新增行是复制相邻行结构，还是生成新的 `<w:tr>`。
- 观察新增行的列宽、边框、段落格式从哪里继承。

#### 1.4 插入新列

1. 选中 `[TABLE-006-TEMPLATE-H2]` 所在列。
2. 在它右侧插入一整列。
3. 从上到下填写新列：

```text
[TABLE-006-TEMPLATE-INSERT-COL-H]
[TABLE-006-TEMPLATE-INSERT-COL-R1]
[TABLE-006-TEMPLATE-INSERT-COL-R2]
[TABLE-006-TEMPLATE-INSERT-COL-R3]
[TABLE-006-TEMPLATE-INSERT-COL-R4]
```

说明：

- 插入新行后，表格现在应是 `4 列 x 5 行`。
- 新列一共有 5 个单元格需要填写。

预期用途：

- 观察插入列后每一行是否新增 `<w:tc>`。
- 观察 `<w:tblGrid>` 是否新增 `<w:gridCol>` 或调整列宽。

#### 1.5 合并单元格

如果你已经完成了前面的新建表格、插入行、插入列，直接从这里继续即可。

1. 在当前表格最下面再插入一整行。
2. 在新行中从左到右填写：

```text
[TABLE-006-TEMPLATE-MERGE-SOURCE-C1] | [TABLE-006-TEMPLATE-MERGE-SOURCE-C2] | [TABLE-006-TEMPLATE-MERGE-SOURCE-C3] | [TABLE-006-TEMPLATE-MERGE-SOURCE-C4]
```

3. 选中这一行的全部 4 个单元格。
4. 执行“合并单元格”。
5. 将合并后的单元格内容替换为：

```text
[TABLE-006-TEMPLATE-MERGED-LAST-ROW]
```

预期用途：

- 观察横向合并是否使用 `<w:gridSpan>`。
- 观察被合并掉的单元格是被删除，还是保留某种占位结构。
- 合并只作用于专用测试行，不覆盖前面基础数据、插入行、插入列的样本。

#### 1.6 删除一行

1. 在当前表格最下面再插入一整行。
2. 在新行中从左到右填写：

```text
[TABLE-006-TEMPLATE-DELETE-ROW-C1] | [TABLE-006-TEMPLATE-DELETE-ROW-C2] | [TABLE-006-TEMPLATE-DELETE-ROW-C3] | [TABLE-006-TEMPLATE-DELETE-ROW-C4]
```

3. 选中这一整行。
4. 删除这一整行。

预期用途：

- 观察删除新建表格中的整行是否直接删除对应 `<w:tr>`。
- 对比 004 中删除原有表格行的源码模式。
- 删除只作用于专用测试行，不删除前面已经保留的基础数据样本。

### 2. 实验报告10_create_table_006.docx

打开：

`cases/create_table_006/docx/实验报告10_create_table_006.docx`

执行以下新建嵌套表格与表格操作：

#### 2.1 在已有表格单元格中创建嵌套表格

1. 找到第二页主表格中的 `四、给出实验过程、结果和讨论，并注明实现过程中遇到的问题。`。
2. 将光标放到这句话后面。
3. 按一次 `Enter` 新增段落。
4. 通过 Word/WPS 的“插入表格”功能，插入一个 `2 列 x 3 行` 的表格。
5. 按下面内容填写表格：

```text
[TABLE-006-REPORT-H1] | [TABLE-006-REPORT-H2]
[TABLE-006-REPORT-R1C1] | [TABLE-006-REPORT-R1C2]
[TABLE-006-REPORT-R2C1] | [TABLE-006-REPORT-R2C2]
```

预期用途：

- 观察在已有大表格单元格中插入新表格时，是否形成嵌套 `<w:tbl>`。
- 观察嵌套表格前后是否自动插入空段落。
- 观察 `read_docx_structure` 后续应如何标记嵌套表格。

#### 2.2 修改嵌套表格内容

1. 将嵌套表格中的 `[TABLE-006-REPORT-R1C2]` 替换为：

```text
[TABLE-006-REPORT-REPLACED-CELL]
```

预期用途：

- 观察新建嵌套表格内普通单元格文本替换的结构。
- 对比 004 中原有表格单元格替换。

#### 2.3 嵌套表格插入行

1. 在嵌套表格第一行表头下面插入一整行。
2. 在新行填写：

```text
[TABLE-006-REPORT-INSERT-ROW-C1] | [TABLE-006-REPORT-INSERT-ROW-C2]
```

预期用途：

- 观察嵌套表格中插入行是否仍然是新增 `<w:tr>`。
- 观察嵌套表格的行列结构是否独立于外层主表格。

#### 2.4 嵌套表格合并单元格

1. 在嵌套表格最下面再插入一整行。
2. 在新行中填写：

```text
[TABLE-006-REPORT-MERGE-SOURCE-C1] | [TABLE-006-REPORT-MERGE-SOURCE-C2]
```

3. 选中这一行的两个单元格。
4. 执行“合并单元格”。
5. 将合并后的单元格内容替换为：

```text
[TABLE-006-REPORT-MERGED-LAST-ROW]
```

预期用途：

- 观察嵌套表格里的横向合并是否同样使用 `<w:gridSpan>`。
- 观察外层主表格是否只增加一个内层 `<w:tbl>`，而不是改变外层行列结构。
- 合并只作用于专用测试行，不覆盖嵌套表格原始数据行。

## 保存要求

编辑完成后：

1. 保存两个 `.docx`。
2. 关闭 Word/WPS。
3. 告诉我你已经保存完成。

关闭文档后再解包，避免文件还被编辑器占用或尚未完整写回磁盘。

## 建议插入标记

### 实验报告模板_v3

- `[TABLE-006-TEMPLATE-H1]`
- `[TABLE-006-TEMPLATE-H2]`
- `[TABLE-006-TEMPLATE-H3]`
- `[TABLE-006-TEMPLATE-R1C1]`
- `[TABLE-006-TEMPLATE-R1C2]`
- `[TABLE-006-TEMPLATE-R1C3]`
- `[TABLE-006-TEMPLATE-R2C1]`
- `[TABLE-006-TEMPLATE-R2C2]`
- `[TABLE-006-TEMPLATE-R2C3]`
- `[TABLE-006-TEMPLATE-R3C1]`
- `[TABLE-006-TEMPLATE-R3C2]`
- `[TABLE-006-TEMPLATE-R3C3]`
- `[TABLE-006-TEMPLATE-INSERT-ROW-C1]`
- `[TABLE-006-TEMPLATE-INSERT-ROW-C2]`
- `[TABLE-006-TEMPLATE-INSERT-ROW-C3]`
- `[TABLE-006-TEMPLATE-INSERT-COL-H]`
- `[TABLE-006-TEMPLATE-INSERT-COL-R1]`
- `[TABLE-006-TEMPLATE-INSERT-COL-R2]`
- `[TABLE-006-TEMPLATE-INSERT-COL-R3]`
- `[TABLE-006-TEMPLATE-INSERT-COL-R4]`
- `[TABLE-006-TEMPLATE-MERGE-SOURCE-C1]`
- `[TABLE-006-TEMPLATE-MERGE-SOURCE-C2]`
- `[TABLE-006-TEMPLATE-MERGE-SOURCE-C3]`
- `[TABLE-006-TEMPLATE-MERGE-SOURCE-C4]`
- `[TABLE-006-TEMPLATE-MERGED-LAST-ROW]`
- `[TABLE-006-TEMPLATE-DELETE-ROW-C1]`
- `[TABLE-006-TEMPLATE-DELETE-ROW-C2]`
- `[TABLE-006-TEMPLATE-DELETE-ROW-C3]`
- `[TABLE-006-TEMPLATE-DELETE-ROW-C4]`

说明：

- `[TABLE-006-TEMPLATE-MERGE-SOURCE-*]` 会在合并后被 `[TABLE-006-TEMPLATE-MERGED-LAST-ROW]` 覆盖，这是合并专用行的预期行为。
- `[TABLE-006-TEMPLATE-DELETE-ROW-*]` 会在删除行后消失，这是删除专用行的预期行为。
- 基础数据行、插入行、插入列的标记都应保留，不应该被合并或删除覆盖。

### 实验报告10

- `[TABLE-006-REPORT-H1]`
- `[TABLE-006-REPORT-H2]`
- `[TABLE-006-REPORT-R1C1]`
- `[TABLE-006-REPORT-R1C2]`
- `[TABLE-006-REPORT-R2C1]`
- `[TABLE-006-REPORT-R2C2]`
- `[TABLE-006-REPORT-REPLACED-CELL]`
- `[TABLE-006-REPORT-INSERT-ROW-C1]`
- `[TABLE-006-REPORT-INSERT-ROW-C2]`
- `[TABLE-006-REPORT-MERGE-SOURCE-C1]`
- `[TABLE-006-REPORT-MERGE-SOURCE-C2]`
- `[TABLE-006-REPORT-MERGED-LAST-ROW]`

说明：

- `[TABLE-006-REPORT-MERGE-SOURCE-*]` 会在合并后被 `[TABLE-006-REPORT-MERGED-LAST-ROW]` 覆盖，这是嵌套表格合并专用行的预期行为。
- 嵌套表格的基础数据行和插入行都应保留，不应该被合并覆盖。

## 编辑操作记录

### 实验报告10

- 在主表格 `四、给出实验过程、结果和讨论，并注明实现过程中遇到的问题。` 所在单元格内新建了一个嵌套表格。
- 嵌套表格表头为 `[TABLE-006-REPORT-H1]`、`[TABLE-006-REPORT-H2]`。
- 在嵌套表格表头下方插入一行，内容为 `[TABLE-006-REPORT-INSERT-ROW-C1]`、`[TABLE-006-REPORT-INSERT-ROW-C2]`。
- 将嵌套表格中的一个单元格替换为 `[TABLE-006-REPORT-REPLACED-CELL]`。
- 在嵌套表格底部新增合并专用行并合并为 `[TABLE-006-REPORT-MERGED-LAST-ROW]`。

注意：

- 实际编辑结果中，消失的是 `[TABLE-006-REPORT-R1C1]`，而不是手册中原计划替换的 `[TABLE-006-REPORT-R1C2]`。
- `[TABLE-006-REPORT-R1C2]` 仍然存在。
- 这说明手动替换时实际替换到了第一列单元格，后续分析以实际 XML 为准。

### 实验报告模板_v3

- 在 `依据实验指导书` 后新建了一个普通表格。
- 新表格最终为 4 列、6 行。
- 第一行是表头，设置了加粗、居中和灰色底纹。
- 在原数据区域中插入了一行，保留 `[TABLE-006-TEMPLATE-INSERT-ROW-*]` 标记。
- 在 `[TABLE-006-TEMPLATE-H2]` 右侧插入了一列，保留 `[TABLE-006-TEMPLATE-INSERT-COL-*]` 标记。
- 底部合并专用行被合并为 `[TABLE-006-TEMPLATE-MERGED-LAST-ROW]`。
- 底部删除专用行已删除，`[TABLE-006-TEMPLATE-DELETE-ROW-*]` 标记全部消失。

## 源码变化分析

已解包：

- `cases/create_table_006/unzipped/实验报告10_after`
- `cases/create_table_006/unzipped/实验报告模板_v3_after`

基线目录：

- `cases/baseline/unzipped/实验报告10`
- `cases/baseline/unzipped/实验报告模板_v3`

### 总体结论

本轮确认：新建表格、插入行、插入列、合并单元格、嵌套表格都主要体现在 `word/document.xml` 中。

其中：

- 新建普通表格：新增完整 `<w:tbl>`。
- 新建嵌套表格：在已有 `<w:tc>` 里新增子 `<w:tbl>`。
- 插入行：新增 `<w:tr>`。
- 插入列：每一行新增 `<w:tc>`，并修改 `<w:tblGrid>`。
- 横向合并：最终只保留一个 `<w:tc>`，这个单元格内写 `<w:gridSpan>`。
- 删除整行：目标 `<w:tr>` 被移除，删除专用标记不再存在。

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

- `word/document.xml`: 66950 字节 -> 74060 字节，增加 7110 字节。
- 表格数：3 -> 4。
- 行数：19 -> 24。
- 单元格数：26 -> 35。
- 段落数：111 -> 121。
- run 数：138 -> 147。
- 文本节点数：136 -> 145。
- `gridSpan` 数量：7 -> 8。

说明：

- `word/numbering.xml` 也发生变化，但本轮没有新增列表，主要应视为 Word/WPS 保存噪声。
- 本轮没有新增图片、链接或外部关系，核心仍是 `word/document.xml`。

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

- `word/document.xml`: 15961 字节 -> 30630 字节，增加 14669 字节。
- 表格数：0 -> 1。
- 行数：0 -> 6。
- 单元格数：0 -> 21。
- 段落数：22 -> 44。
- run 数：22 -> 43。
- 文本节点数：22 -> 43。
- `gridSpan` 数量：0 -> 1。
- `w:shd` 数量：5 -> 9。

说明：

- 模板文档没有新增 `word/numbering.xml`。
- `w:shd` 增加主要来自表头行设置灰色底纹。

## 具体源码观察

### 1. 新建普通表格

位置：

- `实验报告模板_v3_create_table_006.docx`
- 全文新增第 1 个表格。
- 顶层表格，嵌套深度 `depth=0`。

最终结构：

```text
table_index: 1
rows: 6
grid columns: 4
row cell counts: 4, 4, 4, 4, 4, 1
```

表格属性：

```xml
<w:tblStyle w:val="a7"/>
<w:tblW w:w="0" w:type="auto"/>
<w:tblLook w:val="04A0" w:firstRow="1" w:firstColumn="1" .../>
```

表格网格：

```xml
<w:gridCol w:w="2245"/>
<w:gridCol w:w="2245"/>
<w:gridCol w:w="1895"/>
<w:gridCol w:w="2245"/>
```

结论：

- Word/WPS 新建表格会生成完整 `<w:tbl>`。
- 插入列后，`<w:tblGrid>` 从原本 3 列变成 4 列。
- 新插入列宽度是 `1895`，其他列宽度是 `2245`。
- 表格整体宽度仍是自动宽度：`<w:tblW w:w="0" w:type="auto"/>`。

### 2. 表头格式

表头行：

```text
[TABLE-006-TEMPLATE-H1]
[TABLE-006-TEMPLATE-H2]
[TABLE-006-TEMPLATE-INSERT-COL-H]
[TABLE-006-TEMPLATE-H3]
```

源码特征：

```xml
<w:tcPr>
  <w:tcW w:w="2245" w:type="dxa"/>
  <w:shd w:val="clear" w:color="auto" w:fill="A5A5A5" w:themeFill="accent3"/>
</w:tcPr>
<w:pPr>
  <w:jc w:val="center"/>
  <w:rPr>
    <w:b/>
    <w:bCs/>
  </w:rPr>
</w:pPr>
<w:rPr>
  <w:b/>
  <w:bCs/>
</w:rPr>
```

结论：

- 灰色底纹写在单元格属性 `<w:tcPr><w:shd .../>`。
- 居中写在段落属性 `<w:pPr><w:jc w:val="center"/>`。
- 加粗同时出现在段落默认 run 属性和实际 run 属性中。
- 插入列的表头单元格 `[TABLE-006-TEMPLATE-INSERT-COL-H]` 也继承了表头加粗、居中、底纹。

### 3. 插入新行

模板表格最终第 5 行：

```text
[TABLE-006-TEMPLATE-INSERT-ROW-C1]
[TABLE-006-TEMPLATE-INSERT-ROW-C2]
[TABLE-006-TEMPLATE-INSERT-COL-R4]
[TABLE-006-TEMPLATE-INSERT-ROW-C3]
```

结构：

```text
cell_count: 4
tcW: 2245 | 2245 | 1895 | 2245
```

结论：

- 插入行表现为新增完整 `<w:tr>`。
- 插入列之后，新插入行也拥有 4 个 `<w:tc>`。
- 新行中的插入列单元格宽度仍是 `1895`，说明列结构已经被统一到整张表。

### 4. 插入新列

插入列标记：

```text
[TABLE-006-TEMPLATE-INSERT-COL-H]
[TABLE-006-TEMPLATE-INSERT-COL-R1]
[TABLE-006-TEMPLATE-INSERT-COL-R2]
[TABLE-006-TEMPLATE-INSERT-COL-R3]
[TABLE-006-TEMPLATE-INSERT-COL-R4]
```

这些标记分别出现在每一行的第 3 个单元格。

结论：

- 插入列不是单独在某一行操作，而是每一行都新增一个 `<w:tc>`。
- `<w:tblGrid>` 同步新增一列。
- 列插入后，后面的原第 3 列整体右移。

### 5. 横向合并单元格

模板表格最终第 6 行：

```text
[TABLE-006-TEMPLATE-MERGED-LAST-ROW]
```

源码特征：

```xml
<w:tr>
  <w:tc>
    <w:tcPr>
      <w:tcW w:w="8630" w:type="dxa"/>
      <w:gridSpan w:val="4"/>
    </w:tcPr>
    <w:p>
      <w:r>
        <w:t>[TABLE-006-TEMPLATE-MERGED-LAST-ROW]</w:t>
      </w:r>
    </w:p>
  </w:tc>
</w:tr>
```

结论：

- 横向合并后，这一行只剩 1 个 `<w:tc>`。
- 被合并掉的其他单元格没有保留为独立 `<w:tc>`。
- 合并跨度通过 `<w:gridSpan w:val="4"/>` 表达。
- 合并后单元格宽度变为整行宽度 `8630`。
- `[TABLE-006-TEMPLATE-MERGE-SOURCE-*]` 全部消失，这是合并专用行被覆盖的预期结果。

### 6. 删除整行

删除专用标记：

```text
[TABLE-006-TEMPLATE-DELETE-ROW-C1]
[TABLE-006-TEMPLATE-DELETE-ROW-C2]
[TABLE-006-TEMPLATE-DELETE-ROW-C3]
[TABLE-006-TEMPLATE-DELETE-ROW-C4]
```

解包结果：

- 这些标记全部不存在。
- 模板表格最终是 6 行，不包含删除专用行。

结论：

- 删除整行表现为删除完整 `<w:tr>`。
- 删除行不会留下空 `<w:tr>`。
- 删除专用行不影响前面的基础行、插入行、插入列和合并行。

### 7. 嵌套表格

位置：

- `实验报告10_create_table_006.docx`
- 外层主表格是 `body` 第 3 个表格。
- 新建嵌套表格是全文第 4 个表格。
- 嵌套深度 `depth=1`。

外层主表格变化：

```text
表格数：3 -> 4
主表格行数：仍为 7 行
主表格第 5 行第 1 个单元格 nested_tables: 1
```

外层单元格直接子节点顺序：

```text
tcPr
p   四、给出实验过程、结果和讨论，并注明实现过程中遇到的问题。
tbl 嵌套表格
p   空段落
p   空段落
...
```

结论：

- 嵌套表格不是新增到外层主表格同级，而是作为 `<w:tc>` 内部的子 `<w:tbl>`。
- 外层主表格的行列结构没有因为内层表格而改变。
- Word/WPS 在嵌套表格后留下了多个空 `<w:p>`，工具生成嵌套表格时需要保留至少一个后置段落，避免 Word 打开后自动修复；是否需要多个空段落可以后续简化测试。

### 8. 嵌套表格结构

嵌套表格属性：

```xml
<w:tblStyle w:val="ac"/>
<w:tblW w:w="0" w:type="auto"/>
<w:tblLook w:val="04A0" w:firstRow="1" w:firstColumn="1" .../>
```

嵌套表格网格：

```xml
<w:gridCol w:w="4084"/>
<w:gridCol w:w="4084"/>
```

最终结构：

```text
table_index: 4
depth: 1
rows: 5
row cell counts: 2, 2, 2, 2, 1
```

行内容：

```text
R1: [TABLE-006-REPORT-H1] | [TABLE-006-REPORT-H2]
R2: [TABLE-006-REPORT-INSERT-ROW-C1] | [TABLE-006-REPORT-INSERT-ROW-C2]
R3: [TABLE-006-REPORT-REPLACED-CELL] | [TABLE-006-REPORT-R1C2]
R4: [TABLE-006-REPORT-R2C1] | [TABLE-006-REPORT-R2C2]
R5: [TABLE-006-REPORT-MERGED-LAST-ROW]
```

结论：

- 嵌套表格的插入行仍然是新增 `<w:tr>`。
- 嵌套表格横向合并同样使用 `<w:gridSpan>`。
- 合并行只剩 1 个 `<w:tc>`，`gridSpan=2`。
- 嵌套表格内的文本继承了外层章节的加粗正文格式，因此所有标记都带加粗属性。

### 9. 嵌套表格替换偏差

手册原计划：

```text
将 [TABLE-006-REPORT-R1C2] 替换为 [TABLE-006-REPORT-REPLACED-CELL]
```

实际结果：

```text
R3C1: [TABLE-006-REPORT-REPLACED-CELL]
R3C2: [TABLE-006-REPORT-R1C2]
```

同时：

```text
[TABLE-006-REPORT-R1C1] 不存在
[TABLE-006-REPORT-R1C2] 仍然存在
```

结论：

- 实际替换的是原 `[TABLE-006-REPORT-R1C1]` 所在单元格。
- 这个偏差不影响“嵌套表格内替换”的结构观察，但后续如果要复现，应注意选择正确单元格。

## 对工具设计的直接建议

1. 新建表格工具应一次生成完整表格结构。

   最小结构包括：

   - `<w:tbl>`
   - `<w:tblPr>`
   - `<w:tblGrid>`
   - 多个 `<w:tr>`
   - 每个 `<w:tc>` 内至少一个 `<w:p>`

2. 插入列工具不能只改一个单元格。

   插入列需要：

   - 修改 `<w:tblGrid>`。
   - 给每一行新增一个 `<w:tc>`。
   - 注意已有 `gridSpan` 行的处理，合并行可能不应该直接新增普通单元格。

3. 合并单元格工具应使用 `gridSpan`。

   横向合并的稳定表达是：

   - 删除被合并覆盖的多余 `<w:tc>`。
   - 保留第一个 `<w:tc>`。
   - 给第一个 `<w:tc>` 增加 `<w:gridSpan w:val="N"/>`。
   - 调整 `tcW` 为合并后的宽度。

4. 删除整行工具应删除完整 `<w:tr>`。

   删除行不应该只清空内容，也不应该保留空行。

5. 嵌套表格工具要支持“目标单元格内插表”。

   目标位置应该能表达为：

   - 外层表格 index。
   - 外层行 index。
   - 外层列 index。
   - 插入到单元格内哪个段落之后。

6. 读取结构工具需要显式返回嵌套层级。

   仅使用全文第几个表格容易误判。建议返回：

   - `table_index`
   - `depth`
   - `parent_table_index`
   - `parent_row`
   - `parent_cell`
   - `direct_text`
   - `nested_tables`

7. 新建表格后格式继承很明显。

   - 模板中插入的表格继承了蓝色占位符上下文，因此表格文字仍是蓝色。
   - 报告主表格中插入的嵌套表格继承了章节标题的加粗格式。
   - 后续工具应允许 `format_policy="inherit" | "body" | "copy_from_sample"`，不能总是盲目继承。

重点观察：

- 新建表格新增完整 `<w:tbl>`。
- 新建表格包含 `<w:tblPr>`、`<w:tblGrid>`、`<w:tr>`、`<w:tc>`。
- 插入行新增完整 `<w:tr>`。
- 插入列修改每一行的 `<w:tc>` 数量，并调整 `<w:tblGrid>`。
- 横向合并使用 `<w:gridSpan>`。
- 删除行直接删除 `<w:tr>`。
- 嵌套表格表现为 `<w:tc>` 内的子 `<w:tbl>`。
- 新建表格会引起 `word/styles.xml`、`word/settings.xml`、`fontTable.xml` 等保存噪声，但业务核心仍在 `word/document.xml`。
