# DOCX 文字排版与缩进源码变化记录

## Case

text_layout_005

## 待编辑文件

- `cases/text_layout_005/docx/实验报告10_text_layout_005.docx`
- `cases/text_layout_005/docx/实验报告模板_v3_text_layout_005.docx`

## 手动编辑步骤

本轮测试的是 Word/WPS 里文字排版对 `.docx` 解包 XML 的影响。

重点不是 Markdown，也不是单纯空行，而是以下排版动作：

- 手动输入多个空格。
- 输入 Tab。
- 设置首行缩进。
- 设置悬挂缩进。
- 使用 Word/WPS 的项目符号或多级列表缩进。

### 1. 实验报告模板_v3_text_layout_005.docx

打开：

`cases/text_layout_005/docx/实验报告模板_v3_text_layout_005.docx`

执行以下文字排版编辑：

#### 1.1 手打前导空格

1. 找到蓝色段落 `依据实验指导书`。
2. 在这段后面按一次 `Enter` 新增一段。
3. 在新段落最前面手动输入 4 个半角空格。
4. 接着输入：

```text
[LAYOUT-005-TEMPLATE-LEADING-SPACES]
```

预期用途：

- 观察段首连续空格是否保存在 `<w:t>` 中。
- 观察 `<w:t>` 是否出现 `xml:space="preserve"`。
- 对比“手打空格”和“段落缩进属性”的源码差异。

#### 1.2 文本中间多个空格

1. 在上一段后面按一次 `Enter` 新增一段。
2. 输入以下内容，注意 `A` 和 `B` 中间手动输入 6 个半角空格：

```text
[LAYOUT-005-TEMPLATE-INLINE-SPACES-A]      [LAYOUT-005-TEMPLATE-INLINE-SPACES-B]
```

预期用途：

- 观察文本中间连续空格是否保存在同一个 `<w:t>` 中。
- 观察中间空格是否也触发 `xml:space="preserve"`。

#### 1.3 Tab 排版

1. 在上一段后面按一次 `Enter` 新增一段。
2. 输入：

```text
[LAYOUT-005-TEMPLATE-TAB-A]
```

3. 按一次 `Tab`。
4. 继续输入：

```text
[LAYOUT-005-TEMPLATE-TAB-B]
```

预期用途：

- 观察 Tab 是保存成真实制表符，还是生成 `<w:tab/>`。
- 后续工具需要区分“空格对齐”和“Tab 对齐”。

#### 1.4 首行缩进

1. 在上一段后面按一次 `Enter` 新增一段。
2. 输入：

```text
[LAYOUT-005-TEMPLATE-FIRST-LINE-INDENT]
```

3. 选中这一整段。
4. 通过 Word/WPS 的段落设置，将它设置为首行缩进 2 字符。

预期用途：

- 观察首行缩进是否写入 `<w:pPr><w:ind .../>`。
- 观察首行缩进属性和手打空格是否完全不同。

#### 1.5 悬挂缩进

1. 在上一段后面按一次 `Enter` 新增一段。
2. 输入：

```text
[LAYOUT-005-TEMPLATE-HANGING-INDENT] 这一段用于观察悬挂缩进，文本可以稍微长一点，方便看第二行是否和第一行不同。
```

3. 选中这一整段。
4. 通过 Word/WPS 的段落设置，将它设置为悬挂缩进 2 字符。

预期用途：

- 观察悬挂缩进是否也是 `<w:ind>`，但属性名和值不同。
- 对比首行缩进和悬挂缩进的 XML 表达。

### 2. 实验报告10_text_layout_005.docx

打开：

`cases/text_layout_005/docx/实验报告10_text_layout_005.docx`

执行以下文字排版编辑：

#### 2.1 表格单元格内手打空格

1. 找到封面信息表中 `姓名：` 右侧的空白单元格。
2. 在空白单元格中先手动输入 4 个半角空格。
3. 接着输入：

```text
[LAYOUT-005-REPORT-CELL-LEADING-SPACES]
```

预期用途：

- 观察表格单元格里段首空格是否也通过 `xml:space="preserve"` 保留。
- 对比普通段落和表格单元格内的空格处理差异。

#### 2.2 表格单元格内多级列表

1. 找到第二页主表格中的 `二、实验的设备及软件` 所在的大单元格。
2. 将光标放到这一单元格内容末尾。
3. 按一次 `Enter` 新增段落。
4. 使用 Word/WPS 的项目符号列表或多级列表功能，输入以下内容。
5. 其中第二级和第三级必须通过 `Tab` 或“增加缩进级别”生成，不要手打空格伪造缩进。

```text
[LAYOUT-005-REPORT-LIST-L1-A]
[LAYOUT-005-REPORT-LIST-L2-A]
[LAYOUT-005-REPORT-LIST-L3-A]
[LAYOUT-005-REPORT-LIST-L2-B]
[LAYOUT-005-REPORT-LIST-L1-B]
```

建议层级：

```text
- [LAYOUT-005-REPORT-LIST-L1-A]
  - [LAYOUT-005-REPORT-LIST-L2-A]
    - [LAYOUT-005-REPORT-LIST-L3-A]
  - [LAYOUT-005-REPORT-LIST-L2-B]
- [LAYOUT-005-REPORT-LIST-L1-B]
```

预期用途：

- 观察多级列表是否在段落属性里生成 `<w:numPr>`。
- 观察每一级是否通过 `<w:ilvl>` 表达。
- 观察列表编号定义是否写入或修改 `word/numbering.xml`。
- 对比“Word 列表缩进”和“手打空格缩进”的源码差异。

#### 2.3 表格单元格内普通缩进段落

1. 在上面的列表后面退出列表模式。
2. 新增一个普通段落。
3. 输入：

```text
[LAYOUT-005-REPORT-PARAGRAPH-INDENT]
```

4. 选中这一段。
5. 通过 Word/WPS 的段落设置，将左缩进设置为 2 字符或约 0.74 厘米。

预期用途：

- 观察普通左缩进是否写入 `<w:ind w:left="...">`。
- 对比普通段落缩进和列表缩进的 XML 差异。

## 保存要求

编辑完成后：

1. 保存两个 `.docx`。
2. 关闭 Word/WPS。
3. 告诉我你已经保存完成。

关闭文档后再解包，避免文件还被编辑器占用或尚未完整写回磁盘。

## 建议插入标记

- `[LAYOUT-005-TEMPLATE-LEADING-SPACES]`
- `[LAYOUT-005-TEMPLATE-INLINE-SPACES-A]`
- `[LAYOUT-005-TEMPLATE-INLINE-SPACES-B]`
- `[LAYOUT-005-TEMPLATE-TAB-A]`
- `[LAYOUT-005-TEMPLATE-TAB-B]`
- `[LAYOUT-005-TEMPLATE-FIRST-LINE-INDENT]`
- `[LAYOUT-005-TEMPLATE-HANGING-INDENT]`
- `[LAYOUT-005-REPORT-CELL-LEADING-SPACES]`
- `[LAYOUT-005-REPORT-LIST-L1-A]`
- `[LAYOUT-005-REPORT-LIST-L2-A]`
- `[LAYOUT-005-REPORT-LIST-L3-A]`
- `[LAYOUT-005-REPORT-LIST-L2-B]`
- `[LAYOUT-005-REPORT-LIST-L1-B]`
- `[LAYOUT-005-REPORT-PARAGRAPH-INDENT]`

## 编辑操作记录

### 实验报告10

- 在封面信息表 `姓名：` 右侧单元格输入 4 个半角空格后追加 `[LAYOUT-005-REPORT-CELL-LEADING-SPACES]`。
- 在主表格 `二、实验的设备及软件` 所在大单元格末尾新增 5 行项目符号列表：
  - `[LAYOUT-005-REPORT-LIST-L1-A]`
  - `[LAYOUT-005-REPORT-LIST-L2-A]`
  - `[LAYOUT-005-REPORT-LIST-L3-A]`
  - `[LAYOUT-005-REPORT-LIST-L2-B]`
  - `[LAYOUT-005-REPORT-LIST-L1-B]`
- 在列表后新增普通段落 `[LAYOUT-005-REPORT-PARAGRAPH-INDENT]`，并设置左缩进。

### 实验报告模板_v3

- 在 `依据实验指导书` 后新增多段排版测试文本：
  - `[LAYOUT-005-TEMPLATE-LEADING-SPACES]`
  - `[LAYOUT-005-TEMPLATE-INLINE-SPACES-A]      [LAYOUT-005-TEMPLATE-INLINE-SPACES-B]`
  - `[LAYOUT-005-TEMPLATE-TAB-A]	[LAYOUT-005-TEMPLATE-TAB-B]`
  - `[LAYOUT-005-TEMPLATE-FIRST-LINE-INDENT]`
  - `[LAYOUT-005-TEMPLATE-HANGING-INDENT]`
- 对首行缩进和悬挂缩进段落分别设置了对应段落格式。

## 源码变化分析

已解包：

- `cases/text_layout_005/unzipped/实验报告10_after`
- `cases/text_layout_005/unzipped/实验报告模板_v3_after`

基线目录：

- `cases/baseline/unzipped/实验报告10`
- `cases/baseline/unzipped/实验报告模板_v3`

### 总体结论

本轮测试确认：空格、Tab、段落缩进、多级列表缩进在 WordprocessingML 里不是同一种结构。

- 手打连续空格：保存在 `<w:t xml:space="preserve">    </w:t>` 中。
- Tab：不是普通文本，而是独立 `<w:tab/>`。
- 普通段落缩进：写在段落属性 `<w:pPr><w:ind .../>`。
- 多级列表缩进：段落里写 `<w:numPr>`，真正每级缩进定义在 `word/numbering.xml`。

对工具设计的关键影响：

- 如果用户想要“文本前面有几个真实空格”，工具应该写 `w:t` 并设置 `xml:space="preserve"`。
- 如果用户想要“排版缩进”，不要用空格模拟，应该写 `<w:ind>` 或列表 `<w:numPr>`。
- 如果用户想要“列表的二级/三级缩进”，不能只给文本前面加空格，必须创建或复用 numbering 定义。
- Tab 应该作为专门结构处理，不能简单当作 `\t` 写入普通 `<w:t>`。

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

- `word/document.xml`: 66950 字节 -> 71500 字节。
- `word/numbering.xml`: 14717 字节 -> 20052 字节。
- 段落数：111 -> 117。
- run 数：138 -> 146。
- 文本节点数：136 -> 144。
- `<w:tab/>` 数量仍为 0。
- 表格数不变：3 -> 3。

`word/numbering.xml` 本轮发生业务变化，因为新增了项目符号列表。这个文件不能像纯文本插入时那样简单归为保存噪声。

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

- `word/document.xml`: 15961 字节 -> 20055 字节。
- 段落数：22 -> 27。
- run 数：22 -> 33。
- 文本节点数：22 -> 32。
- `<w:tab/>` 数量：0 -> 1。
- 表格数不变：0 -> 0。

模板文档没有 `word/numbering.xml`，本轮也没有新增列表定义。

## 具体源码观察

### 1. 手打段首空格

#### 实验报告10：表格单元格中段首空格

标记：

```text
[LAYOUT-005-REPORT-CELL-LEADING-SPACES]
```

定位：

- 全文第 9 个段落。
- `body` 第 2 个表格。
- 第 1 行第 2 个单元格。

段落文本：

```text
    [LAYOUT-005-REPORT-CELL-LEADING-SPACES]
```

源码特征：

```xml
<w:r>
  <w:t xml:space="preserve">    </w:t>
</w:r>
<w:r>
  <w:t>[LAYOUT-005-REPORT-CELL-LEADING-SPACES]</w:t>
</w:r>
```

结论：

- Word/WPS 将段首 4 个半角空格保存成独立 run。
- 空格 run 的 `<w:t>` 带 `xml:space="preserve"`。
- 这说明如果工具要写“真实空格”，必须保留 `xml:space="preserve"`，否则 XML 规范层面可能被折叠或丢失。

#### 实验报告模板_v3：段首空格样本

标记：

```text
[LAYOUT-005-TEMPLATE-LEADING-SPACES]
```

本次解包结果里，这一段没有出现前导空格文本节点，而是表现为段落缩进：

```xml
<w:ind w:firstLine="420"/>
<w:t>[LAYOUT-005-TEMPLATE-LEADING-SPACES]</w:t>
```

结论：

- 这个样本没有成功形成“前导空格源码样本”。
- 可能原因是编辑时没有输入空格、空格被编辑器行为吸收，或该位置继承/应用了首行缩进。
- 真实空格样本以实验报告10中的表格单元格为准。

### 2. 文本中间连续空格

标记：

```text
[LAYOUT-005-TEMPLATE-INLINE-SPACES-A]      [LAYOUT-005-TEMPLATE-INLINE-SPACES-B]
```

定位：

- 模板文档全文第 10 个段落。

run 分布：

- R1: `[LAYOUT-005-TEMPLATE-INLINE-SPACES-`
- R2: `A]`
- R3: `      `，带 `xml:space="preserve"`
- R4: `[`
- R5: `LAYOUT-005-TEMPLATE-INLINE-SPACES-B]`

核心源码：

```xml
<w:t>A]</w:t>
<w:t xml:space="preserve">      </w:t>
<w:t>[</w:t>
```

结论：

- 文本中间连续空格也会用 `xml:space="preserve"` 保存。
- Word/WPS 可能把一个逻辑字符串拆成多个 run，中间还可能插入校对节点，例如 `<w:proofErr>`。
- 工具不能假设“一个连续输入字符串等于一个 `<w:t>`”。

### 3. Tab 排版

标记：

```text
[LAYOUT-005-TEMPLATE-TAB-A]	[LAYOUT-005-TEMPLATE-TAB-B]
```

定位：

- 模板文档全文第 11 个段落。

源码特征：

```xml
<w:t>[LAYOUT-005-TEMPLATE-TAB-A]</w:t>
<w:tab/>
<w:t>[LAYOUT-005-TEMPLATE-TAB-B]</w:t>
```

结论：

- Tab 不写成普通 `<w:t>` 文本。
- Word/WPS 会生成独立的 `<w:tab/>` 节点。
- 后续工具如果支持插入 Tab，应该创建 `<w:r><w:tab/></w:r>`，而不是简单写入 `\t`。

### 4. 首行缩进

标记：

```text
[LAYOUT-005-TEMPLATE-FIRST-LINE-INDENT]
```

定位：

- 模板文档全文第 12 个段落。

源码特征：

```xml
<w:ind w:leftChars="200" w:left="420" w:firstLine="420"/>
```

结论：

- 首行缩进是段落属性，不是文本前加空格。
- 本次 2 字符首行缩进同时写入了：
  - `w:leftChars="200"`
  - `w:left="420"`
  - `w:firstLine="420"`
- 工具设计时应提供段落级格式能力，例如 `set_paragraph_indent(first_line_chars=200)` 或 `first_line_twips=420`。

### 5. 悬挂缩进

标记：

```text
[LAYOUT-005-TEMPLATE-HANGING-INDENT]
```

定位：

- 模板文档全文第 13 个段落。

源码特征：

```xml
<w:ind w:leftChars="200" w:left="840" w:hanging="420"/>
```

结论：

- 悬挂缩进也是 `<w:ind>`。
- 它和首行缩进的区别是使用 `w:hanging`，而不是 `w:firstLine`。
- 本次样本中左缩进是 `840`，悬挂量是 `420`。
- 不能用文本空格模拟悬挂缩进，否则第二行不会稳定对齐。

### 6. 普通左缩进

标记：

```text
[LAYOUT-005-REPORT-PARAGRAPH-INDENT]
```

定位：

- 实验报告10全文第 43 个段落。
- `body` 第 3 个表格。
- 第 3 行第 1 个单元格。

源码特征：

```xml
<w:ind w:left="420"/>
```

结论：

- 普通左缩进只需要段落级 `<w:ind w:left="...">`。
- 它不需要 `w:numPr`，也不修改 `word/numbering.xml`。

### 7. 多级项目符号列表

标记和层级：

```text
[LAYOUT-005-REPORT-LIST-L1-A]  ilvl=0
[LAYOUT-005-REPORT-LIST-L2-A]  ilvl=1
[LAYOUT-005-REPORT-LIST-L3-A]  ilvl=2
[LAYOUT-005-REPORT-LIST-L2-B]  ilvl=1
[LAYOUT-005-REPORT-LIST-L1-B]  ilvl=0
```

定位：

- 实验报告10全文第 38 到 42 个段落。
- `body` 第 3 个表格。
- 第 3 行第 1 个单元格。

段落里的列表属性：

```xml
<w:numPr>
  <w:ilvl w:val="0"/>
  <w:numId w:val="7"/>
</w:numPr>
```

第二级：

```xml
<w:ilvl w:val="1"/>
<w:numId w:val="7"/>
```

第三级：

```xml
<w:ilvl w:val="2"/>
<w:numId w:val="7"/>
```

`word/numbering.xml` 中：

```xml
<w:num w:numId="7">
  <w:abstractNumId w:val="2"/>
</w:num>
```

`abstractNumId=2` 的关键定义：

```xml
<!-- level 0 -->
<w:numFmt w:val="bullet"/>
<w:lvlText w:val=""/>
<w:ind w:left="920" w:hanging="440"/>

<!-- level 1 -->
<w:numFmt w:val="bullet"/>
<w:lvlText w:val=""/>
<w:ind w:left="1360" w:hanging="440"/>

<!-- level 2 -->
<w:numFmt w:val="bullet"/>
<w:lvlText w:val=""/>
<w:ind w:left="1800" w:hanging="440"/>
```

结论：

- 列表的层级不靠文本前空格，而靠 `<w:ilvl>`。
- 同一组列表共用 `numId=7`。
- 每一级的实际缩进、悬挂量、符号字符在 `numbering.xml` 的 abstract numbering 里定义。
- 段落自身只有 `w:numPr` 和少量段落属性；真正的列表排版不能只看 `document.xml`。

## 对工具设计的直接建议

1. 文本工具要区分“空格字符”和“缩进格式”。

   - 用户说“前面加 4 个空格”：写 `w:t xml:space="preserve"`。
   - 用户说“首行缩进 2 字符”：写 `w:pPr/w:ind`。
   - 用户说“左缩进一点”：写 `w:ind w:left`。

2. Tab 需要单独工具或单独 token。

   Tab 对应 `<w:tab/>`，不要混在普通文本里盲写。

3. 多级列表需要专门工具。

   最小工具参数可以是：

   - `paragraphs`: 每行文本。
   - `levels`: 每行对应的 `0/1/2/...`。
   - `list_type`: `bullet` 或 `numbered`。
   - `format_source`: 复制附近列表，或者新建列表定义。

4. 列表工具必须同时处理 `document.xml` 和 `numbering.xml`。

   只在段落里写 `<w:numPr>` 不够，还需要确保 `numId` 指向有效的 abstract numbering。

5. diff 工具需要把 `numbering.xml` 当作业务文件。

   纯文本编辑时它常是保存噪声；但列表编辑时它是核心变化。

重点观察：

- 手打连续空格会保存在 `<w:t>`，并通过 `xml:space="preserve"` 保留。
- Tab 表现为 `<w:tab/>`。
- 首行缩进、悬挂缩进、左缩进都写入 `<w:pPr><w:ind>`，但属性不同。
- 多级列表写入 `<w:pPr><w:numPr>`。
- 多级列表层级通过 `<w:ilvl>` 表达。
- 列表定义会导致 `word/numbering.xml` 变化。
- 普通段落、表格单元格、蓝色占位段落中的排版属性会继承当前位置格式，不能一概而论。
