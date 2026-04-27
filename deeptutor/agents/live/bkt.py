"""Bayesian Knowledge Tracing — pure functions, no I/O.

Standard 4-parameter BKT model (Corbett & Anderson, 1995):
    P(L) — probability of learning a skill in one opportunity
    P(F) — probability of forgetting (usually small)
    P(S) — probability of slipping (knew it but answered wrong)
    P(G) — probability of guessing (didn't know but answered right)
"""

from __future__ import annotations

import re

P_LEARN = 0.15
P_FORGET = 0.005
P_SLIP = 0.10
P_GUESS = 0.20

DEFAULT_MASTERY = 0.25
DEFAULT_SKILL = "default"

AFFIRMATIONS = (
    "correct",
    "exactly",
    "well done",
    "right",
    "great job",
    "great",
    "yes",
    "spot on",
    "nicely",
    "perfect",
    "good thinking",
)

CORRECTIONS = (
    "actually",
    "not quite",
    "not exactly",
    "let me clarify",
    "close but",
    "almost",
    "incorrect",
    "that's wrong",
    "let's reconsider",
    "rethink",
)


def bkt_update(p_mastery: float, is_correct: bool) -> float:
    """Standard BKT posterior update. Returns new ``p_mastery`` in ``[0, 1]``.

    Steps:
      1. Compute posterior given evidence (correct/incorrect).
      2. Apply learning transition: P(L_t+1) = P_after + (1 - P_after) * P_learn.
      3. Apply optional forgetting decay (small).
    """
    p = max(0.0, min(1.0, float(p_mastery)))

    if is_correct:
        numerator = p * (1.0 - P_SLIP)
        denominator = numerator + (1.0 - p) * P_GUESS
    else:
        numerator = p * P_SLIP
        denominator = numerator + (1.0 - p) * (1.0 - P_GUESS)

    posterior = numerator / denominator if denominator > 0 else p

    after_learn = posterior + (1.0 - posterior) * P_LEARN
    after_forget = after_learn * (1.0 - P_FORGET)

    return max(0.0, min(1.0, after_forget))


def infer_correctness(ai_response: str) -> bool:
    """Heuristic: detect affirmation vs. correction language in the AI response.

    Returns ``True`` when affirmations outweigh corrections (or both are zero —
    a neutral probing response is treated as a small positive signal).
    """
    if not ai_response:
        return True

    lower = ai_response.lower()
    aff = sum(1 for phrase in AFFIRMATIONS if phrase in lower)
    neg = sum(1 for phrase in CORRECTIONS if phrase in lower)
    return aff >= neg


_NON_SKILL_CHARS = re.compile(r"[^a-z0-9_]+")


def topic_to_skill(topic: str) -> str:
    """Normalize a free-form topic string to a canonical skill key.

    Examples
    --------
    >>> topic_to_skill("Linear Algebra")
    'linear_algebra'
    >>> topic_to_skill("  Photosynthesis!  ")
    'photosynthesis'
    >>> topic_to_skill("")
    'default'
    """
    if not topic:
        return DEFAULT_SKILL
    cleaned = _NON_SKILL_CHARS.sub("_", topic.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or DEFAULT_SKILL
