#!/usr/bin/env python3
"""
诊断脚本: 直接连 WebSocket, 打印每个事件的精确到达时间, 验证后端流式推送节奏
不依赖任何前端代码 — 纯协议层诊断
"""
import asyncio
import json
import time
import sys
import websockets

async def diagnose():
    uri = "ws://127.0.0.1:8000/api/ws/agent"
    prompt = "请阅读 J:\\学习\\大三下\\计算机劳动实践\\实验13\\实验报告13.docx 并完成编写, 要求保留已有内容"

    print(f"[{time.strftime('%H:%M:%S.')}] Connecting to {uri}...")
    async with websockets.connect(uri) as ws:
        print(f"[{time.strftime('%H:%M:%S.')}] Connected. Sending start...")
        await ws.send(json.dumps({"type": "start", "prompt": prompt, "docx_path": ""}))

        # 计数器
        event_count = 0
        reasoning_count = 0
        content_count = 0
        reasoning_total_chars = 0
        content_total_chars = 0
        first_event_time = None
        last_event_time = None
        gaps = []  # 事件间隔

        print(f"\n{'='*80}")
        print(f"{'idx':>5} | {'Δms':>6} | {'type':<14} | {'len':>5} | {'cum':>5} | detail")
        print(f"{'='*80}")

        try:
            while True:
                raw = await ws.recv()
                now = time.time()
                if first_event_time is None:
                    first_event_time = now
                if last_event_time is not None:
                    gaps.append((now - last_event_time) * 1000)
                last_event_time = now

                try:
                    data = json.loads(raw)
                except:
                    print(f"{event_count:>5} | (parse error)")
                    continue

                event_count += 1
                etype = data.get("type", "?")

                if etype == "reasoning":
                    reasoning_count += 1
                    delta = data.get("delta", "")
                    reasoning_total_chars += len(delta)
                    dt = f"+{(now - first_event_time)*1000:.0f}ms" if first_event_time else "0ms"
                    print(f"{event_count:>5} | {dt:>6} | {etype:<14} | {len(delta):>5} | {reasoning_total_chars:>5} | {repr(delta[:60])}")
                elif etype == "content":
                    content_count += 1
                    delta = data.get("delta", "")
                    content_total_chars += len(delta)
                    dt = f"+{(now - first_event_time)*1000:.0f}ms" if first_event_time else "0ms"
                    print(f"{event_count:>5} | {dt:>6} | {etype:<14} | {len(delta):>5} | {content_total_chars:>5} | {repr(delta[:60])}")
                elif etype in ("tool_start", "tool_end", "round_start", "wait_approval", "done"):
                    dt = f"+{(now - first_event_time)*1000:.0f}ms" if first_event_time else "0ms"
                    print(f"{event_count:>5} | {dt:>6} | {etype:<14} | {'-':>5} | {'-':>5} | {json.dumps(data, ensure_ascii=False)[:80]}")
                else:
                    dt = f"+{(now - first_event_time)*1000:.0f}ms" if first_event_time else "0ms"
                    print(f"{event_count:>5} | {dt:>6} | {etype:<14} | {'-':>5} | {'-':>5} | {str(data)[:80]}")

                if etype in ("wait_approval", "done", "error"):
                    print(f"\n[收到 {etype}, 退出]")
                    break
        except Exception as e:
            print(f"\n[连接断开: {e}]")

        # 统计
        print(f"\n{'='*80}")
        print(f"统计:")
        print(f"  总事件数: {event_count}")
        print(f"  reasoning 事件数: {reasoning_count} (总字符: {reasoning_total_chars})")
        print(f"  content 事件数: {content_count} (总字符: {content_total_chars})")
        if gaps:
            gaps_sorted = sorted(gaps)
            print(f"  事件间隔统计 (ms):")
            print(f"    最小: {min(gaps):.1f}")
            print(f"    中位: {gaps_sorted[len(gaps)//2]:.1f}")
            print(f"    最大: {max(gaps):.1f}")
            print(f"    平均: {sum(gaps)/len(gaps):.1f}")
            # 关键诊断: 如果平均间隔 < 50ms 但浏览器看到"一次性蹦出" → 前端问题
            #          如果 reasoning 事件本身就很少 (< 5 个) → 后端 chunk 太大
        print(f"{'='*80}")

if __name__ == "__main__":
    asyncio.run(diagnose())
