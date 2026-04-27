"""Quick latency probe for /api/v1/ws/live (one-shot)."""

from __future__ import annotations

import asyncio
import json
import time

import websockets


async def probe() -> None:
    uri = "ws://localhost:8001/api/v1/ws/live?token=local-dev-user"
    started = time.monotonic()
    async with websockets.connect(uri, max_size=2**20) as ws:
        ready = json.loads(await ws.recv())
        ready_ms = int((time.monotonic() - started) * 1000)
        print(f"ready ({ready_ms} ms): {ready}")

        await ws.send(
            json.dumps(
                {
                    "type": "transcript",
                    "text": "What is photosynthesis?",
                    "is_final": True,
                }
            )
        )
        sent_at = time.monotonic()

        first_token_ms: int | None = None
        first_sentence_ms: int | None = None
        full_text_parts: list[str] = []
        sentences = 0

        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=20)
            frame = json.loads(raw)
            kind = frame.get("type")
            if kind == "token":
                if first_token_ms is None:
                    first_token_ms = int((time.monotonic() - sent_at) * 1000)
                full_text_parts.append(frame.get("text", ""))
            elif kind == "sentence":
                sentences += 1
                if first_sentence_ms is None:
                    first_sentence_ms = int((time.monotonic() - sent_at) * 1000)
                print(f"sentence #{sentences} @ {first_sentence_ms}+ms: {frame['text']!r}")
            elif kind == "done":
                total_ms = int((time.monotonic() - sent_at) * 1000)
                print()
                print(f"first token   : {first_token_ms} ms")
                print(f"first sentence: {first_sentence_ms} ms")
                print(f"backend TTFT  : {frame.get('ttft_ms')} ms")
                print(f"total time    : {total_ms} ms")
                print(f"sentences emt : {sentences}")
                print(f"chars         : {len(''.join(full_text_parts))}")
                break
            elif kind == "error":
                print(f"ERROR: {frame}")
                break


if __name__ == "__main__":
    asyncio.run(probe())
