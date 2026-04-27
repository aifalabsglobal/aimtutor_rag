"""Live voice pipeline — sentence flushing and abort handling."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from deeptutor.agents.live import pipeline as pipeline_mod
from deeptutor.agents.live.pipeline import (
    LIVE_SYSTEM_PROMPT,
    _flush_sentence,
    stream_live_response,
)


def test_live_system_prompt_includes_mastery_payload() -> None:
    prompt = LIVE_SYSTEM_PROMPT({"linear_algebra": 0.7})
    assert "linear_algebra" in prompt
    assert "0.7" in prompt
    assert "MAXIMUM 2 sentences" in prompt


def test_flush_sentence_splits_on_terminator() -> None:
    sentence, remainder = _flush_sentence("Hello world. And then ")
    assert sentence == "Hello world."
    assert remainder == " And then "


def test_flush_sentence_keeps_buffer_without_terminator() -> None:
    sentence, remainder = _flush_sentence("partial sentence")
    assert sentence == ""
    assert remainder == "partial sentence"


def test_flush_sentence_first_accepts_clause_break_after_min_words() -> None:
    sentence, remainder = _flush_sentence(
        "Photosynthesis is a process, where plants ", first=True
    )
    assert sentence == "Photosynthesis is a process,"
    assert remainder.strip() == "where plants"


def test_flush_sentence_first_holds_short_clauses() -> None:
    sentence, remainder = _flush_sentence("Yes, but ", first=True)
    assert sentence == ""
    assert remainder == "Yes, but "


def test_flush_sentence_non_first_ignores_clause_breaks() -> None:
    sentence, remainder = _flush_sentence(
        "and another long clause, with no period yet", first=False
    )
    assert sentence == ""
    assert remainder == "and another long clause, with no period yet"


@pytest.mark.asyncio
async def test_stream_live_response_emits_token_sentence_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = ["Sure", ", ", "you ", "got it. ", "Why?"]

    async def fake_llm_stream(**_kwargs: object) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(pipeline_mod, "llm_stream", fake_llm_stream)

    abort = asyncio.Event()
    events: list[dict] = []
    async for event in stream_live_response(
        [{"role": "user", "content": "What is 2+2?"}], {"general": 0.5}, abort
    ):
        events.append(event)

    types = [e["type"] for e in events]
    assert types.count("token") == len(chunks)
    assert "sentence" in types
    assert types[-1] == "done"

    sentences = [e["text"] for e in events if e["type"] == "sentence"]
    assert any("got it." in s for s in sentences)
    assert any("Why?" in s for s in sentences)


@pytest.mark.asyncio
async def test_stream_live_response_aborts_quickly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks = ["one ", "two ", "three ", "four ", "five"]

    async def fake_llm_stream(**_kwargs: object) -> AsyncIterator[str]:
        for chunk in chunks:
            yield chunk

    monkeypatch.setattr(pipeline_mod, "llm_stream", fake_llm_stream)

    abort = asyncio.Event()
    events: list[dict] = []
    async for event in stream_live_response(
        [{"role": "user", "content": "hi"}], {}, abort
    ):
        events.append(event)
        if event["type"] == "token" and event.get("index") == 2:
            abort.set()

    types = [e["type"] for e in events]
    assert types.count("token") <= 3
    assert "done" not in types  # done is suppressed when aborted


@pytest.mark.asyncio
async def test_stream_live_response_emits_error_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_llm_stream(**_kwargs: object) -> AsyncIterator[str]:
        if False:
            yield ""  # pragma: no cover
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline_mod, "llm_stream", fake_llm_stream)

    abort = asyncio.Event()
    events: list[dict] = []
    async for event in stream_live_response(
        [{"role": "user", "content": "hi"}], {}, abort
    ):
        events.append(event)

    assert events[-1]["type"] == "error"
    assert events[-1]["retryable"] is True
