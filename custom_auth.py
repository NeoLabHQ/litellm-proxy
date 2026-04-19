"""
Static Token Authentication for LiteLLM Proxy

Validates incoming requests against a shared static token (PROXY_STATIC_TOKEN env var).
Runs at the proxy level before any routing, covering all endpoints including
Anthropic passthrough.

Usage:
    In config.yaml:
        general_settings:
            custom_auth: custom_auth.static_token_auth

    In .env:
        PROXY_STATIC_TOKEN=your-shared-secret-token
"""

import os

from fastapi import Request
from litellm.proxy._types import UserAPIKeyAuth

STATIC_TOKEN = os.environ.get("PROXY_STATIC_TOKEN", "").strip()

if STATIC_TOKEN:
    print("[Auth] Static token authentication enabled", flush=True)
else:
    print("[Auth] No PROXY_STATIC_TOKEN configured — all requests allowed", flush=True)


async def static_token_auth(request: Request, api_key: str) -> UserAPIKeyAuth:
    if not STATIC_TOKEN:
        return UserAPIKeyAuth(api_key=api_key)

    # api_key is extracted by LiteLLM from Authorization/x-litellm-api-key header
    client_key = api_key or ""

    # Strip "Bearer " prefix if present
    if client_key.lower().startswith("bearer "):
        client_key = client_key[7:]

    if client_key != STATIC_TOKEN:
        print("[Auth] Rejected request — invalid static token", flush=True)
        from litellm.proxy._types import ProxyException
        raise ProxyException(
            message="Unauthorized: invalid proxy token",
            type="auth_error",
            param=None,
            code=401,
        )

    return UserAPIKeyAuth(api_key=api_key)
