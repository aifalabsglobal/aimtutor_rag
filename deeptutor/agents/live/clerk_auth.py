"""Clerk session-token verification for the live voice WebSocket.

When ``CLERK_SECRET_KEY`` (and ``NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY``) are set
we delegate to the official ``clerk-backend-api`` Python SDK. When they're
not set the WS treats the token string itself as the user_id — parity with
the frontend's ``isClerkPublishableConfigured()`` opt-in check.

The SDK is imported lazily so the package keeps working in environments
that do not have ``clerk-backend-api`` installed yet.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_clerk_client: Any | None = None
_clerk_init_attempted = False


def is_clerk_configured() -> bool:
    """Mirror of ``web/lib/clerk-config.ts:isClerkServerConfigured``."""
    return bool(
        (os.environ.get("CLERK_SECRET_KEY") or "").strip()
        and (os.environ.get("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY") or "").strip()
    )


def _get_client() -> Any | None:
    """Lazily build a Clerk SDK client. Returns ``None`` if unavailable."""
    global _clerk_client, _clerk_init_attempted
    if _clerk_init_attempted:
        return _clerk_client
    _clerk_init_attempted = True

    secret_key = (os.environ.get("CLERK_SECRET_KEY") or "").strip()
    if not secret_key:
        return None

    try:
        from clerk_backend_api import Clerk  # type: ignore[import-not-found]

        _clerk_client = Clerk(bearer_auth=secret_key)
        logger.info("Clerk SDK initialized for live voice session auth")
    except Exception as exc:
        logger.warning(
            "clerk-backend-api unavailable; live voice WS will reject when Clerk is enabled. "
            "Install it with `pip install clerk-backend-api`. Error: %s",
            exc,
        )
        _clerk_client = None
    return _clerk_client


async def verify_session_token(token: str) -> str | None:
    """Verify a Clerk session JWT and return the user id, else ``None``.

    Uses the SDK's built-in JWT verification (no network round-trip per call;
    JWKS is cached internally by the SDK).
    """
    if not token:
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        from clerk_backend_api.security.types import (  # type: ignore[import-not-found]
            AuthenticateRequestOptions,
        )

        request_state = client.authenticate_request(
            None,
            AuthenticateRequestOptions(
                jwt_key=os.environ.get("CLERK_JWT_KEY") or None,
                authorized_parties=None,
            ),
            token,
        )
        if not request_state.is_signed_in:
            return None
        payload = getattr(request_state, "payload", None)
        if isinstance(payload, dict):
            sub = payload.get("sub") or payload.get("user_id")
            if isinstance(sub, str) and sub:
                return sub
    except Exception:
        pass

    # Fallback: many Clerk SDK versions expose `verify_token` returning a
    # decoded JWT payload directly. Use it if available.
    try:
        verify = getattr(client, "verify_token", None)
        if callable(verify):
            payload = verify(token)
            if isinstance(payload, dict):
                sub = payload.get("sub") or payload.get("user_id")
                if isinstance(sub, str) and sub:
                    return sub
    except Exception as exc:
        logger.debug("Clerk verify_token fallback failed: %s", exc)

    return None
