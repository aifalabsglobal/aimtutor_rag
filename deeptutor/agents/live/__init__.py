"""
Live Voice Session
==================

Real-time, full-duplex voice tutoring capability for AimTutor.

Architecture:
    Browser mic / SpeechRecognition
              |
              v
    /api/v1/ws/live (FastAPI WebSocket)
              |
              v
    LiveSession + SessionRegistry (session.py)
              |
              v
    stream_live_response (pipeline.py) -> deeptutor.services.llm.stream
              |
              v
    Bayesian Knowledge Tracing (bkt.py)
              |
              v
    KnowledgeStore (knowledge_store.py) — in-memory, optional Redis

Auth:
    Clerk session token verified via the official ``clerk-backend-api``
    SDK in ``clerk_auth.py``. When Clerk is not configured the WS treats
    the supplied token string as the user_id (parity with the frontend's
    ``isClerkPublishableConfigured()`` check).

Public API:
    LiveSession, SessionRegistry, get_session_registry
    stream_live_response, LIVE_SYSTEM_PROMPT
    bkt_update, infer_correctness, topic_to_skill
    KnowledgeStore, get_knowledge_store
    verify_session_token
"""

from .bkt import bkt_update, infer_correctness, topic_to_skill
from .clerk_auth import is_clerk_configured, verify_session_token
from .knowledge_store import KnowledgeStore, get_knowledge_store
from .pipeline import LIVE_SYSTEM_PROMPT, stream_live_response, warmup_llm
from .session import LiveSession, SessionRegistry, get_session_registry

__all__ = [
    "LiveSession",
    "SessionRegistry",
    "get_session_registry",
    "stream_live_response",
    "warmup_llm",
    "LIVE_SYSTEM_PROMPT",
    "bkt_update",
    "infer_correctness",
    "topic_to_skill",
    "KnowledgeStore",
    "get_knowledge_store",
    "verify_session_token",
    "is_clerk_configured",
]
