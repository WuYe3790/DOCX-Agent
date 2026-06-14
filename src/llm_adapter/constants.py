"""LLM Adapter 常量

集中存放模型相关的硬编码常量(枚举、默认值等),避免散落在 provider.py 各处。

注意:这些常量是 Step 1+ 接入新模型(如 sensenova-u1-fast 生图)时引入的,
与 Step 5 之前的 _DEFAULT_* 表(在 provider.py 内)职责不同:
    - _DEFAULT_* 表是 provider 行为 fallback(请求注入模板、quirks 等)
    - 这里常量是模型自身约束(尺寸枚举、模型名默认值等)
"""

# 商汤 sensenova-u1-fast 合法尺寸(11 种 aspect ratio,2K 分辨率)
# 来源: 官方文档 https://docs.sensenova.cn — /v1/images/generations 接口 size 字段
# 任何不在此集合的 size 都会被 create_image_generation 拒绝,避免触发 400 错误。
SENSENOVA_U1_VALID_SIZES: frozenset[str] = frozenset({
    "1664x2496",  # 2:3
    "2496x1664",  # 3:2
    "1760x2368",  # 3:4
    "2368x1760",  # 4:3
    "1824x2272",  # 4:5
    "2272x1824",  # 5:4
    "2048x2048",  # 1:1
    "2752x1536",  # 16:9  ← 默认
    "1536x2752",  # 9:16
    "3072x1376",  # 21:9
    "1344x3136",  # 9:21
})

# 默认生图模型(可被 config.json 的 providers.<name>.image_model 覆盖,
# 或 SENSENOVA_IMAGE_MODEL 环境变量覆盖)。
DEFAULT_IMAGE_MODEL: str = "sensenova-u1-fast"