"""Streaming LLM pipeline for live voice tutoring.

Mirrors the structure of ``deeptutor.agents.chat.agentic_pipeline`` but is
massively simpler — no tool loop, no multi-stage reasoning. The contract:

  - Yields token / sentence / done / error events as fast as the LLM streams.
  - Honors ``abort_event`` between every yielded chunk (target < 100 ms).
  - Uses the existing ``deeptutor.services.llm.stream`` factory — never
    imports a provider SDK directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from deeptutor.services.llm import stream as llm_stream

logger = logging.getLogger(__name__)

LIVE_MAX_TOKENS = 200
LIVE_TEMPERATURE = 0.6
SENTENCE_TERMINATORS = (".", "!", "?")
SENTENCE_MAX_BUFFER = 90
# For the FIRST audible sentence in a reply we accept clause-level breaks
# (comma / colon / dash) once the buffer carries enough words. This is what
# determines time-to-first-audio, so we trade a little prosody for snappier
# perceived responsiveness. After the first sentence we revert to clean
# sentence-boundary flushing.
FIRST_SENTENCE_CLAUSE_BREAKS = (", ", "; ", ": ", " — ", " - ")
FIRST_SENTENCE_MIN_WORDS = 5
FIRST_SENTENCE_MAX_BUFFER = 55

LIVE_SYSTEM_PROMPT_TEMPLATE = """\
You are a live adaptive AI tutor in a real-time voice session.

Learner knowledge state (skill -> mastery 0.0-1.0):
{mastery_json}

Session rules:
- MAXIMUM 2 sentences per response. This is voice — brevity is mandatory.
- End every response with exactly one question.
- mastery < 0.3   -> foundational, use analogies, define terms.
- mastery 0.3-0.6 -> probe understanding, add nuance.
- mastery > 0.6   -> challenge assumptions, ask for synthesis.
- Never use markdown, bullets, or formatting of any kind.
- Speak in natural conversational sentences only.
- If the learner's message was an interruption (short or mid-thought), respond naturally.
"""


def LIVE_SYSTEM_PROMPT(mastery: dict[str, float] | None = None) -> str:
    """Render the system prompt with the learner's current mastery state."""
    payload = json.dumps(mastery or {}, ensure_ascii=False, sort_keys=True)
    return LIVE_SYSTEM_PROMPT_TEMPLATE.format(mastery_json=payload)


async def warmup_llm() -> int:
    """Issue a tiny LLM request so the next real turn lands on a warm pool.

    First-call TTFT to OpenAI from a cold process is dominated by TLS
    handshake + ``httpx`` connection-pool setup (~3-4 s). Triggering a
    one-token call ahead of the user's first transcript hides that cost.

    Returns the warmup TTFT in milliseconds (best-effort; ``-1`` on error).
    """
    try:
        started = time.monotonic()
        async for _ in llm_stream(
            prompt="ok",
            system_prompt="Reply with one word.",
            max_tokens=1,
            temperature=0.0,
        ):
            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.info("LLM warmup TTFT=%d ms", elapsed_ms)
            return elapsed_ms
        return -1
    except Exception as exc:
        logger.debug("LLM warmup failed (non-fatal): %s", exc)
        return -1


def _flush_sentence(buffer: str, *, first: bool = False) -> tuple[str, str]:
    """Split ``buffer`` at the last sentence terminator.

    Returns ``(sentence, remainder)``. If no terminator is found and the
    buffer exceeds ``SENTENCE_MAX_BUFFER``, the entire buffer is treated
    as a sentence (so very long single-sentence responses still get spoken).

    When ``first=True`` we are still trying to emit the first audible chunk
    of a response. We additionally accept clause-level breaks (comma, colon,
    dash) once the buffer carries at least ``FIRST_SENTENCE_MIN_WORDS``
    words, and a tighter byte cap, to minimize time-to-first-audio.
    """
    last = -1
    for term in SENTENCE_TERMINATORS:
        idx = buffer.rfind(term)
        if idx > last:
            last = idx
    if last >= 0:
        return buffer[: last + 1].strip(), buffer[last + 1 :]
    if first:
        word_count = len(buffer.split())
        if word_count >= FIRST_SENTENCE_MIN_WORDS:
            best = -1
            best_len = 0
            for sep in FIRST_SENTENCE_CLAUSE_BREAKS:
                idx = buffer.find(sep)
                if idx >= 0 and idx > best:
                    best = idx
                    best_len = len(sep)
            if best > 0:
                cut = best + best_len
                return buffer[:cut].strip(), buffer[cut:]
        if len(buffer) >= FIRST_SENTENCE_MAX_BUFFER:
            return buffer.strip(), ""
    elif len(buffer) >= SENTENCE_MAX_BUFFER:
        return buffer.strip(), ""
    return "", buffer


async def stream_live_response(
    messages: list[dict[str, str]],
    mastery: dict[str, float],
    abort_event: asyncio.Event,
    *,
    max_tokens: int = LIVE_MAX_TOKENS,
    temperature: float = LIVE_TEMPERATURE,
) -> AsyncGenerator[dict[str, Any], None]:
    """Stream a tutor response token-by-token with sentence-boundary events.

    Yields:
        ``{"type": "token", "text": str, "index": int}``
        ``{"type": "sentence", "text": str}``
        ``{"type": "done", "full_text": str, "ttft_ms": int}``
        ``{"type": "error", "message": str, "retryable": bool}``
    """
    if not messages:
        yield {"type": "error", "message": "No messages provided", "retryable": False}
        return

    system_prompt = LIVE_SYSTEM_PROMPT(mastery)

    last = messages[-1]
    user_prompt = str(last.get("content", "")) if last.get("role") == "user" else ""
    history = messages[:-1] if user_prompt else messages

    started_monotonic = time.monotonic()
    ttft_ms: int | None = None
    full_text_parts: list[str] = []
    sentence_buffer = ""
    token_index = 0
    sentences_emitted = 0

    try:
        chunk_iter = llm_stream(
            prompt=user_prompt or "",
            system_prompt=system_prompt,
            messages=history if history else None,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        async for chunk in chunk_iter:
            if abort_event.is_set():
                break
            if not chunk:
                continue

            if ttft_ms is None:
                ttft_ms = int((time.monotonic() - started_monotonic) * 1000)

            full_text_parts.append(chunk)
            sentence_buffer += chunk
            token_index += 1

            yield {"type": "token", "text": chunk, "index": token_index}

            sentence, remainder = _flush_sentence(
                sentence_buffer, first=sentences_emitted == 0
            )
            if sentence:
                sentence_buffer = remainder
                sentences_emitted += 1
                yield {"type": "sentence", "text": sentence}

        if not abort_event.is_set():
            tail = sentence_buffer.strip()
            if tail:
                yield {"type": "sentence", "text": tail}

            full_text = "".join(full_text_parts).strip()
            yield {
                "type": "done",
                "full_text": full_text,
                "ttft_ms": ttft_ms or 0,
            }
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Live voice pipeline failed")
        yield {
            "type": "error",
            "message": str(exc) or "LLM stream failed",
            "retryable": True,
        }
