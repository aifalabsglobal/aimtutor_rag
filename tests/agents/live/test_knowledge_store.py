"""KnowledgeStore — in-memory branch (Redis branch covered by integration)."""

from __future__ import annotations

import pytest

from deeptutor.agents.live.bkt import DEFAULT_MASTERY, DEFAULT_SKILL
from deeptutor.agents.live.knowledge_store import KnowledgeStore


@pytest.mark.asyncio
async def test_get_unknown_user_returns_default() -> None:
    store = KnowledgeStore(redis_url=None)
    mastery = await store.get("brand_new_user")
    assert mastery == {DEFAULT_SKILL: DEFAULT_MASTERY}


@pytest.mark.asyncio
async def test_update_skill_persists_in_memory() -> None:
    store = KnowledgeStore(redis_url=None)
    await store.update_skill("alice", "linear_algebra", 0.42)

    mastery = await store.get("alice")
    assert mastery["linear_algebra"] == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_update_skill_clamps_to_unit_interval() -> None:
    store = KnowledgeStore(redis_url=None)
    await store.update_skill("alice", "skill", 1.7)
    await store.update_skill("alice", "skill_two", -0.4)

    mastery = await store.get("alice")
    assert mastery["skill"] == 1.0
    assert mastery["skill_two"] == 0.0


@pytest.mark.asyncio
async def test_get_with_empty_user_returns_default() -> None:
    store = KnowledgeStore(redis_url=None)
    assert await store.get("") == {DEFAULT_SKILL: DEFAULT_MASTERY}


@pytest.mark.asyncio
async def test_update_skill_ignores_empty_inputs() -> None:
    store = KnowledgeStore(redis_url=None)
    await store.update_skill("", "skill", 0.5)
    await store.update_skill("alice", "", 0.5)

    assert await store.get("alice") == {DEFAULT_SKILL: DEFAULT_MASTERY}
