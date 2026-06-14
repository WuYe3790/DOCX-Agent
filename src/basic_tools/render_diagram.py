"""render_diagram — 用 Graphviz/Mermaid 代码精确渲染流程图/信息图

针对 generate_image (商汤文生图) 的痛点设计: 文生图对"流程图、状态机、架构图"
这类「有逻辑结构」的图天生不合适, 节点位置错乱、箭头方向乱、文字模糊。
本工具让 LLM 直接写 Graphviz DOT 或 Mermaid 源码, 通过在线渲染服务
(https://kroki.io) 输出精确 PNG, 再用 insert_image_after_paragraph 插入 Word。

工具调用流:
    主 agent → render_diagram(source, language="graphviz")
            → HTTP 调用 kroki.io → PNG bytes
            → 写到 out/sessions/<id>/workspace/media/<filename>.png
            → 返回 JSON {status, path, ...} 给主 agent
            → 主 agent 把 path 嵌入 Markdown 草稿
            → 后续 markdown_to_word 编译时嵌入 docx

⚠️ 协议陷阱 (踩过就懂):
   Kroki 后端用 Java java.util.zip.Inflater 反序列化, 期望完整 zlib 格式
   (78 9C 头 + adler32 尾)。**不要剥头尾**, 那是 plantuml.com 自己 server 的
   旧协议 (PlantUML 用 Hpack/Deflate)。误剥会触发 HTTP 400
   "Error while decoding the payload"。详见 _kroki_encode_source 注释和
   docs.kroki.io/kroki/setup/encode-diagram/ 的官方 Python 示例。
"""

from __future__ import annotations

import base64
import json
import logging
import sys
import time
import zlib
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# === 依赖 ===
sys.path.append(str(Path(__file__).parent.parent))
from workspace.guard import workspace_dir  # noqa: E402


# === 常量 ===
KROKI_BASE = "https://kroki.io"
KROKI_TIMEOUT = 30           # 单次 HTTP 调用秒数 (graphviz 复杂图可能 5-10s)
KROKI_MAX_RETRIES = 2        # 5xx 重试次数, 退避 1.5s/3s
POST_THRESHOLD = 3000        # encoded 长度阈值, 超过切 POST 避免 URL 过长
DEFAULT_OUTPUT_FILENAME = "diagram.png"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class KrokiRenderError(Exception):
    """Kroki 渲染失败的标准异常, 携带足够上下文供 LLM 修代码。"""

    def __init__(self, language: str, http_status: int, body: str,
                 source_snippet: str = ""):
        self.language = language
        self.http_status = http_status
        self.body = body.strip()[:1500]
        self.source_snippet = source_snippet[:200]
        super().__init__(
            f"Kroki render failed: {language} HTTP {http_status}"
        )


def _emit_progress(session_id: str, event: str, **fields) -> None:
    """工具进度日志: 写到 out/sessions/<id>/logs/render_diagram.log。

    与 image_refiner 同款模式 (写文件 + 兜底吞异常)。
    路径独立于 generate_image.log, 避免两个工具混在一起便于排查。
    """
    import datetime as _dt
    kv = " ".join(f"{k}={v}" for k, v in fields.items())
    try:
        session_root = workspace_dir(session_id).parent
        log_dir = session_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "render_diagram.log"
        ts = _dt.datetime.now().isoformat(timespec="seconds")
        line = f"{ts} [{event}] {kv}\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass  # 日志失败绝不能影响主流程
    logger.info("render_diagram event=%s %s", event, kv)


# === 编码 ===
def _kroki_encode_source(source: str) -> str:
    """把图表源码编码成 Kroki URL path 可用的字符串。

    流程:
        1. UTF-8 编码 (DOT/Mermaid 源码含中文/Unicode 时必备)
        2. zlib.compress (默认带完整 zlib 格式: 78 9C 头 + raw deflate + adler32 尾)
        3. base64.urlsafe_b64encode (Kroki 要 URL-safe 字母表)
        4. 去掉末尾 '=' padding (Kroki 路径段不接受 padding 字符)

    ⚠️ 不要做 [2:-4] 剥 zlib header/adler32!
        那是 plantuml.com 官方 server 的旧协议 (PlantUML 用自己的 Hpack/Deflate)。
        Kroki 是独立项目, 后端用 Java java.util.zip.Inflater 反序列化,
        期望完整 zlib 格式。误剥会触发 HTTP 400 "Error while decoding the payload"。
        官方文档: https://docs.kroki.io/kroki/setup/encode-diagram/
    """
    raw = source.encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    encoded = base64.urlsafe_b64encode(compressed).rstrip(b"=")
    return encoded.decode("ascii")


# === HTTP 调用 ===
def _kroki_get(language: str, encoded: str, fmt: str = "png") -> bytes:
    """GET https://kroki.io/<lang>/<fmt>/<encoded> → 原始 PNG bytes。

    用于编码后长度 < POST_THRESHOLD 的源码。5xx 重试 2 次, 退避 1.5s/3s。

    Raises:
        KrokiRenderError: HTTP 4xx (语法错误等) 或重试耗尽后的 5xx, 或非 PNG 响应
        requests.RequestException: 网络层异常透传给上层走 renderer_unavailable
    """
    url = f"{KROKI_BASE}/{language}/{fmt}/{encoded}"
    last_exc = None
    for attempt in range(KROKI_MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, timeout=KROKI_TIMEOUT,
                headers={"User-Agent": "docx-agent/1.0"},
            )
            if resp.status_code == 200:
                if resp.content[:8] != PNG_MAGIC:
                    raise KrokiRenderError(
                        language=language, http_status=200,
                        body=f"non-PNG response, first 16 bytes: {resp.content[:16]!r}",
                    )
                return resp.content
            if resp.status_code in (502, 503, 504) and attempt < KROKI_MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            # 400 语法错误或其他不可重试错误: 把 Kroki stderr 透传给 LLM
            raise KrokiRenderError(
                language=language,
                http_status=resp.status_code,
                body=resp.text[:2000],
            )
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= KROKI_MAX_RETRIES:
                raise
            time.sleep(1.5 * (attempt + 1))
    # 理论上走不到 (retry 循环里要么 return 要么 raise), 兜底
    raise KrokiRenderError(
        language=language, http_status=0,
        body=f"network error after retries: {last_exc}",
    )


def _kroki_post(language: str, source: str, fmt: str = "png") -> bytes:
    """POST 路径: 源码大到 URL 装不下时走这条 (encoded >= POST_THRESHOLD)。

    body 是 raw source 文本 (UTF-8), 不是 encoded。
    Kroki POST endpoint 接受 Content-Type: text/plain。
    """
    url = f"{KROKI_BASE}/{language}/{fmt}"
    last_exc = None
    for attempt in range(KROKI_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                data=source.encode("utf-8"),
                headers={
                    "Content-Type": "text/plain",
                    "User-Agent": "docx-agent/1.0",
                },
                timeout=KROKI_TIMEOUT,
            )
            if resp.status_code == 200:
                if resp.content[:8] != PNG_MAGIC:
                    raise KrokiRenderError(
                        language=language, http_status=200,
                        body=f"non-PNG response, first 16 bytes: {resp.content[:16]!r}",
                    )
                return resp.content
            if resp.status_code in (502, 503, 504) and attempt < KROKI_MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise KrokiRenderError(
                language=language,
                http_status=resp.status_code,
                body=resp.text[:2000],
            )
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= KROKI_MAX_RETRIES:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise KrokiRenderError(
        language=language, http_status=0,
        body=f"network error after retries: {last_exc}",
    )


def _kroki_render(language: str, source: str, fmt: str = "png") -> tuple[bytes, str]:
    """根据 encoded 长度选 GET 或 POST, 返回 (PNG bytes, 'GET'/'POST')。"""
    encoded = _kroki_encode_source(source)
    if len(encoded) < POST_THRESHOLD:
        return _kroki_get(language, encoded, fmt), "GET"
    return _kroki_post(language, source, fmt), "POST"


# === LLM hint 模板 (语法错误时附在 error JSON 里指导 LLM 修代码) ===
_SYNTAX_HINT_GRAPHVIZ = (
    "DOT 必须以 'digraph G { ... }' 或 'graph G { ... }' 起头, "
    "语句以分号或换行结束, 中文 label 直接用 UTF-8 字符串。"
)
_SYNTAX_HINT_MERMAID = (
    "Mermaid 必须以图类型声明起头 (graph TD / sequenceDiagram / gantt / "
    "classDiagram 等), 节点连接用 -->, 中文 label 直接用 UTF-8 字符串。"
)


def _make_hint(language: str) -> str:
    if language == "graphviz":
        return _SYNTAX_HINT_GRAPHVIZ
    if language == "mermaid":
        return _SYNTAX_HINT_MERMAID
    return ""


# === 主入口 ===
def render_diagram(
    session_id: str,
    source: str,
    language: str = "graphviz",
    output_filename: str = DEFAULT_OUTPUT_FILENAME,
) -> str:
    """渲染 Graphviz/Mermaid 源码为 PNG, 写到 session workspace 的 media/ 目录。

    Args:
        session_id:      workspace 所属 session
        source:          图表源码 (DOT 或 Mermaid)
        language:        "graphviz" | "mermaid"
        output_filename: workspace 内 media/ 目录下的文件名, 默认 diagram.png

    Returns:
        JSON 字符串。成功例:
            {"status": "ok", "language": "graphviz", "path": "media/diagram.png",
             "size_bytes": 12345, "transport": "GET", "elapsed_ms": 1234}
        语法错误例 (HTTP 400):
            {"status": "error", "error_type": "syntax_error", "language": "graphviz",
             "message": "...", "renderer_stderr": "...", "source_snippet": "...",
             "hint": "..."}
        网络/服务不可用例 (HTTP 5xx 重试耗尽 / Timeout):
            {"status": "error", "error_type": "renderer_unavailable",
             "language": "graphviz", "message": "..."}
        参数错误例:
            {"status": "error", "error_type": "bad_argument", "message": "..."}
    """
    # 防御 1: language 必须合法
    if language not in ("graphviz", "mermaid"):
        return json.dumps({
            "status": "error",
            "error_type": "bad_argument",
            "message": (
                f"非法 language: {language!r}, 仅支持 'graphviz' 或 'mermaid'。"
            ),
        }, ensure_ascii=False)

    # 防御 2: output_filename 不允许含路径分隔符或 ..
    # (与 _media.download_to_workspace:80-83 同款防御, 防止越权写入)
    if "/" in output_filename or "\\" in output_filename or output_filename.startswith(".."):
        return json.dumps({
            "status": "error",
            "error_type": "bad_argument",
            "message": (
                f"非法 output_filename: {output_filename!r}。"
                "不允许包含路径分隔符或 .."
            ),
        }, ensure_ascii=False)

    # 防御 3: source 非空
    if not source or not source.strip():
        return json.dumps({
            "status": "error",
            "error_type": "bad_argument",
            "message": "source 不能为空。请传入完整的 Graphviz DOT 或 Mermaid 源码。",
        }, ensure_ascii=False)

    _emit_progress(
        session_id, "tool_start",
        language=language, filename=output_filename,
        source_len=len(source),
    )

    # === Step 1: 调用 Kroki 渲染 ===
    started = time.monotonic()
    try:
        png_bytes, transport = _kroki_render(language, source)
    except KrokiRenderError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _emit_progress(
            session_id, "kroki_error",
            http_status=exc.http_status, language=language,
            elapsed_ms=elapsed_ms, body=exc.body[:200],
        )
        if exc.http_status == 400:
            return json.dumps({
                "status": "error",
                "error_type": "syntax_error",
                "language": language,
                "message": (
                    f"{language} 源码语法错误, 渲染器返回以下信息, 请修正后重试:"
                ),
                "renderer_stderr": exc.body,
                "source_snippet": source[:200],
                "hint": _make_hint(language),
            }, ensure_ascii=False)
        # 5xx / 网络 / 非 PNG 响应都归到 renderer_unavailable
        return json.dumps({
            "status": "error",
            "error_type": "renderer_unavailable",
            "language": language,
            "http_status": exc.http_status,
            "message": (
                f"kroki.io 暂时不可达 (HTTP {exc.http_status}), 已重试 "
                f"{KROKI_MAX_RETRIES} 次。请稍后重试, 或检查网络/代理。"
                "本工具不降级到 generate_image。"
            ),
            "renderer_body": exc.body,
        }, ensure_ascii=False)
    except requests.RequestException as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _emit_progress(
            session_id, "network_error",
            language=language, elapsed_ms=elapsed_ms, exc=str(exc)[:200],
        )
        return json.dumps({
            "status": "error",
            "error_type": "renderer_unavailable",
            "language": language,
            "message": (
                f"调用 kroki.io 网络异常: {exc}。请检查网络/代理。"
                "本工具不降级到 generate_image。"
            ),
        }, ensure_ascii=False)

    # === Step 2: 写到 workspace/media/ ===
    try:
        workspace = workspace_dir(session_id)
    except Exception as exc:
        return json.dumps({
            "status": "error",
            "error_type": "workspace_error",
            "message": f"workspace 路径解析失败: {exc}",
        }, ensure_ascii=False)

    media_dir = workspace / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    target = media_dir / output_filename
    target.write_bytes(png_bytes)

    elapsed_ms = int((time.monotonic() - started) * 1000)
    rel_path = f"media/{output_filename}"

    _emit_progress(
        session_id, "tool_done",
        language=language, path=rel_path, transport=transport,
        size_bytes=len(png_bytes), elapsed_ms=elapsed_ms,
    )

    return json.dumps({
        "status": "ok",
        "language": language,
        "path": rel_path,
        "size_bytes": len(png_bytes),
        "transport": transport,
        "elapsed_ms": elapsed_ms,
    }, ensure_ascii=False)


# === Tool schema (主 agent 看到的) ===
tools_schema = {
    "type": "function",
    "function": {
        "name": "render_diagram",
        "description": (
            "把 Graphviz DOT 或 Mermaid 源码渲染成 PNG, 保存到 session workspace 的 media/ 目录。"
            "用途: 流程图、状态机、架构图、组织结构图、依赖关系图、决策树、时序图、类图等"
            "「有逻辑结构」的图。相对于 generate_image (像素级写实图) 的优势:"
            "节点位置精确、箭头方向正确、文字不模糊、可指定子图嵌套与样式。"
            "⚠️ 拿到 path 后, 你必须在 Markdown 草稿中用标准图片语法嵌入, 格式严格为: "
            "`![图表说明|center](返回的path)`, 随后再调用 insert_image_after_paragraph 把图"
            "插入到 Word。仅写了路径而不在草稿里引用, 等于图被藏在沙箱里, 用户看不到。"
            "⚠️ 在线渲染 (kroki.io), 需网络可达。失败时把 stderr 回显, 改源码重试即可, "
            "不要回退到 generate_image。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["graphviz", "mermaid"],
                    "default": "graphviz",
                    "description": (
                        "图表语法。graphviz (DOT) 推荐用于: 流程图、状态机、架构图、"
                        "组织结构、依赖关系、决策树、网络拓扑等节点-边模型。"
                        "mermaid 推荐用于: sequenceDiagram (时序图)、gantt (甘特图)、"
                        "classDiagram、stateDiagram-v2、erDiagram、pie。"
                    ),
                },
                "source": {
                    "type": "string",
                    "description": (
                        "完整的图表源码。graphviz 以 'digraph G { ... }' 起头; "
                        "mermaid 直接写图表声明 (如 'graph TD; A-->B;')。"
                        "中文/Unicode 节点 label 直接用 UTF-8 字符串。"
                    ),
                },
                "output_filename": {
                    "type": "string",
                    "default": DEFAULT_OUTPUT_FILENAME,
                    "description": "workspace 内 media/ 目录下的文件名, 默认 diagram.png",
                },
            },
            "required": ["source"],
        },
    },
}
