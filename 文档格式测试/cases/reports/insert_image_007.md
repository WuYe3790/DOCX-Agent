# DOCX 插入图片源码变化记录

## Case

insert_image_007

## 待编辑文件

- `cases/insert_image_007/docx/实验报告10_insert_image_007.docx`
- `cases/insert_image_007/docx/实验报告模板_v3_insert_image_007.docx`

## 手动编辑步骤

### 1. 实验报告模板_v3_insert_image_007.docx

打开：

`cases/insert_image_007/docx/实验报告模板_v3_insert_image_007.docx`

执行以下操作：

1. 找到蓝色段落 `依据实验指导书`。
2. 在该段落下方敲击回车换行，新建一个段落。
3. 在新段落中插入图片 `cases/insert_image_007/test_chart.png`。
4. 将图片设置为**嵌入型**（默认），并设置**居中对齐**。
5. 将图片尺寸调整到合适大小（例如宽度 10~12cm 左右）。

预期用途：
- 观察在普通正文段落下方插入图片时，`<w:drawing>` XML 结构如何生成。
- 观察图片在 `word/media/` 下的新增和命名方式。
- 观察 `word/_rels/document.xml.rels` 的图片关系绑定（Relationship）。
- 观察 `[Content_Types].xml` 对 `.png` 类型文件的 MIME 声明变化。

### 2. 实验报告10_insert_image_007.docx

打开：

`cases/insert_image_007/docx/实验报告10_insert_image_007.docx`

执行以下操作：

1. 找到 `三、实验程序流程图` 标题下方的 `请给出详细的设计流程图。` 段落。
2. 在该段落下方敲击回车新建一个段落。
3. 在新段落中插入图片 `cases/insert_image_007/test_chart.png`。
4. 将图片设置为**嵌入型**（默认），居中对齐并调整到合适大小。

预期用途：
- 观察在稍大、包含更多复杂格式的实际报告文档中，插入新图片时的 OpenXML 节点排布与关系引用的递增。

## 保存要求

编辑完成后：

1. 保存两个 `.docx`。
2. 关闭 Word/WPS。
3. 告诉我你已经保存完成。

关闭文档后再解包，避免文件还被编辑器占用或尚未完整写回磁盘。

## 建议插入标记

- `cases/insert_image_007/test_chart.png`

## 编辑操作记录

### 实验报告10

- 在段落 `请给出详细的设计流程图。` 下方敲击回车换行，并插入了图片 `test_chart.png`。
- 图片被设置为嵌入型、居中对齐。

### 实验报告模板_v3

- 在蓝色段落 `依据实验指导书` 下方敲击回车换行，并插入了图片 `test_chart.png`。
- 图片被设置为嵌入型、居中对齐。

## 源码变化分析

已解包：

- `cases/insert_image_007/unzipped/实验报告10_after`
- `cases/insert_image_007/unzipped/实验报告模板_v3_after`

基线目录：

- `cases/baseline/unzipped/实验报告10`
- `cases/baseline/unzipped/实验报告模板_v3`

### 总体结论

本次是插入图片的操作。与普通的文本操作相比，图片插入是 DOCX 规范中较复杂的复合操作，涉及如下多处关键变化：
1. **媒体文件写入**：图片源文件被作为二进制数据拷贝进 ZIP 包内的 `word/media/` 目录下（如 `image1.png` 或 `image2.png`）。
2. **关系链注册**：在 `word/_rels/document.xml.rels` 中动态新增一个 Relationship 项目，将其映射到 `word/media/` 对应的具体文件，以分配关系 ID（`rId`）。
3. **内容类型声明**：若包内未声明该扩展名，需在全局 `[Content_Types].xml` 注册对 `.png` 扩展名与 MIME 类型 `image/png` 的声明，否则 Office 软件会报告文档损坏或拒绝加载图片。
4. **Drawing 标签生成**：在 `word/document.xml` 对应的段落中，插入 `<w:drawing>` 包裹的 OpenXML DrawingML 格式子树，且在其 `<a:blip>` 的 `r:embed` 属性里写入前述的关系 ID。

保存时的其他如 `docProps/`, `word/styles.xml`, `settings.xml` 等哈希变化应作为保存噪声处理。

### 变化文件清单

#### 实验报告模板_v3

有哈希变化的文件：

- `[Content_Types].xml`
- `word/_rels/document.xml.rels`
- `word/document.xml`
- `word/settings.xml`
- `word/styles.xml`
- `word/fontTable.xml`

核心变化：

- **新增文件**：`word/media/image1.png` (2667 字节，SHA256 与 `test_chart.png` 一致)。
- **关系链更新**：`word/_rels/document.xml.rels` 从 1337 字节变为 1470 字节，新增：
  ```xml
  <Relationship Id="rId6" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
  ```
- **MIME 注册**：`[Content_Types].xml` 从 1957 字节变为 2007 字节，新增：
  ```xml
  <Default Extension="png" ContentType="image/png"/>
  ```
- **正文 XML structure**：`word/document.xml` 从 15961 字节变为 17661 字节，段落中新增了：
  ```xml
  <w:p ...>
    <w:pPr>
      <w:jc w:val="center"/>
      ...
    </w:pPr>
    <w:r>
      <w:drawing>
        <wp:inline ...>
          <wp:extent cx="3810000" cy="2857500"/>
          <wp:docPr id="1899066527" name="图片 1"/>
          ...
          <a:blip r:embed="rId6"/>
          ...
          <a:ext cx="3810000" cy="2857500"/>
        </wp:inline>
      </w:drawing>
    </w:r>
  </w:p>
  ```

节点数量变化：
- 段落数：22 -> 23 (+1)
- run 数：22 -> 23 (+1)
- 文本节点数：22 -> 22 (未变，Drawing 内部不含 `<w:t>`)
- Drawing 数：0 -> 1 (+1)
- 表格数：0 -> 0

#### 实验报告10

有哈希变化的文件：

- `[Content_Types].xml`
- `word/_rels/document.xml.rels`
- `word/document.xml`
- `word/settings.xml`
- `word/styles.xml`
- `word/fontTable.xml`
- `word/numbering.xml`
- `word/webSettings.xml`

核心变化：

- **新增文件**：`word/media/image2.png` (2667 字节，SHA256 与 `test_chart.png` 一致。由于原本已含一个 jpeg 图片，新图命名递增为 `image2.png`)。
- **关系链更新**：`word/_rels/document.xml.rels` 从 1762 字节变为 1895 字节，新增关系 ID 绑定：
  ```xml
  <Relationship Id="rId10" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image2.png"/>
  ```
- **MIME 注册**：`[Content_Types].xml` 增加了对 png 的 Default 声明，使其同时支持 `.jpeg` 与 `.png`。
- **正文 XML structure**：`word/document.xml` 从 66950 字节变为 69434 字节，插入了以 `rId10` 为 embed 值的 `<w:drawing>` 图形结构。

节点数量变化：
- 段落数：111 -> 112 (+1)
- run 数：138 -> 139 (+1)
- 文本节点数：136 -> 136 (未变)
- Drawing 数：1 -> 2 (+1)
- 表格数：3 -> 3

### 实验报告模板_v3：在依据实验指导书下插入图片

插入内容：

图片 `cases/insert_image_007/test_chart.png`，居中对齐，宽度约为 10 厘米（3810000 EMU）。

定位：

- 新增的段落位于全局第 9 个段落节点。
- 非表格段落。
- 插入在 `依据实验指导书` 段落下方。

插入前局部段落：

```text
P8: 依据实验指导书
P9: （空段落）
P10: 【实验内容】
```

插入后局部段落：

```text
P8: 依据实验指导书
P9: （Drawing 节点，无文字，嵌入式图片，居中对齐）
P10: （空段落）
P11: 【实验内容】
```

新段落 XML 结构：

- 新段落 `<w:p>` 含有段落属性 `<w:pPr>`，并在其中设置了 `<w:jc w:val="center"/>` 居中对齐。
- 新段落中包含单个 run `<w:r>`，其下包含 `<w:drawing>`。
- `<w:drawing>` 最内层 blip 结构为 `<a:blip r:embed="rId6"/>`，成功关联到 Relationship 中的图片 ID。

工具参考：

- 插入图片时，工具必须新建一个 `<w:p>`，包含居中对齐属性 `<w:jc w:val="center"/>`，在其下创建 `<w:r>` 及标准的 DrawingXML 图形树结构。
- 必须要维护和分配一个唯一的 Relationship ID 并反向写回 Drawing 树的 `r:embed` 属性。

### 实验报告10：在流程图说明下插入图片

插入内容：

图片 `cases/insert_image_007/test_chart.png`，居中对齐，宽度约为 10 厘米（3810000 EMU）。

定位：

- 新增的段落位于全局第 42 个段落节点。
- 处于大表格正文的特定行。
- 插入在 `请给出详细的设计流程图。` 段落下方。

插入前局部段落：

```text
P40: 三、实验程序流程图
P41: 请给出详细的设计流程图。
```

插入后局部段落：

```text
P40: 三、实验程序流程图
P41: 请给出详细的设计流程图。
P42: （Drawing 节点，无文字，嵌入式图片，居中对齐）
```

新段落 XML 结构：

- 新段落 `<w:p>` 设置了居中对齐 `<w:jc w:val="center"/>`。
- 包含单个 run `<w:r>` 及 `<w:drawing>`，在 `<a:blip r:embed="rId10"/>` 中嵌入了关系 ID `rId10`。
- 媒体文件保存为 `word/media/image2.png`，因为该文件包里原本已经包含了 `media/image1.jpeg`。

工具参考：

- 当源文档中已经含有图片时，新增图片的目标名称不能硬编码为 `image1.png`，必须读取 `word/media/` 目录下的已有图片数量并计算出递增的新名称（如 `image2.png`），以避免命名冲突。
- 对关系 ID 的分配同样需要递增分配，不能硬编码。

## 对工具设计的直接建议

1. **图片资源的命名需支持动态递增分配**：
   
   在解包和重打包 ZIP 写入图片资源时，必须先扫描 `word/media/` 目录下已有的图片名（例如 `image1.jpeg`），生成递增的文件名（例如 `image2.png`），切忌硬编码，以防止覆盖已有图片或导致文档损坏。

2. **关系链（Relationships）需动态注入和合并**：
   
   向 Word 写入图片时，必须解析原有的 `word/_rels/document.xml.rels`，生成一个唯一的关系 ID（如 `rId10`），并将该 Relationship 项（Type 为 `.../relationships/image`，Target 指向新写入的 `media/image{N}.png`）追加到关系链文件中，且关系 ID 需在原最大 ID 的基础上进行递增分配。

3. **全局 `[Content_Types].xml` 的 MIME 注册检查**：
   
   在重打包时，必须检查 `[Content_Types].xml`。如果插入的是 `.png` 图片且原文档中未注册该扩展名，必须动态补充 `<Default Extension="png" ContentType="image/png"/>`。若缺失此声明，Office 套件会显示“发现无法读取的内容”并拒绝打开文档。

4. **规范的 DrawingML XML 生成结构**：
   
   编译生成 `<w:drawing>` 时，应符合嵌入型图片的标准 OpenXML DrawingML 格式规范。必须包含：
   - `<wp:extent cx="{width}" cy="{height}"/>` 指定图片在 Word 里的实际尺寸（单位为 EMU，1 英寸 = 914400 EMU）。
   - `<wp:docPr id="{id}" name="{alt}"/>` 赋给唯一的图形 id。
   - `<a:blip r:embed="{rId}"/>` 填写分配的关系 ID。
   - 保证 Drawing 节点外包裹单个 `<w:r>` 并放置在居中 `<w:jc w:val="center"/>` 的独立 `<w:p>` 节点中。

5. **过滤保存噪声，防止冗余写回**：
   
   WPS/Word 重新保存文档时，会连带修改 `settings.xml`、`styles.xml`、`fontTable.xml` 以及页眉页脚等非业务核心文件。工具底层设计只应当把编译生成的 `document.xml`、`.xml.rels`、`[Content_Types].xml` 以及新增的 `media/` 图片打包写回，忽略非图片插入业务的配置变化，以过滤噪声。
