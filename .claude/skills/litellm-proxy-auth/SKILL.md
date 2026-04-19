---
name: LiteLLM Proxy Authentication Hooks
description: How custom_auth, CustomLogger hooks, and FastAPI middleware interact with standard and passthrough endpoints in LiteLLM proxy
topics: litellm, proxy, authentication, passthrough, anthropic, custom_auth, hooks
created: 2026-04-19
updated: 2026-04-19
scratchpad: .specs/scratchpad/516cd93e.md
---

# LiteLLM Proxy Authentication Hooks

## Overview

LiteLLM proxy has two distinct auth hook systems. `custom_auth` (via `general_settings`) fires for ALL routes including true HTTP passthrough endpoints. `CustomLogger.async_pre_call_hook` only fires when LiteLLM routes the request through its SDK — it is silently skipped for true passthrough routes like `/anthropic/v1/messages`.

---

## Key Concepts

- **`custom_auth`**: A FastAPI `Depends(user_api_key_auth)` dependency injected into every route handler — fires before any routing decision
- **`async_pre_call_hook`**: A CustomLogger callback that fires inside the LiteLLM SDK call — not triggered for HTTP passthrough
- **True passthrough**: Routes like `/anthropic/{endpoint:path}` that forward raw HTTP to the upstream provider — LiteLLM SDK is not involved
- **Unified `/v1/messages`**: A beta endpoint that routes through the LiteLLM SDK (pre_call_hook fires here), distinct from `/anthropic/v1/messages`

---

## Auth Hook Coverage Matrix

| Hook | `/v1/chat/completions` | `/v1/messages` (beta) | `/anthropic/v1/messages` (passthrough) |
|------|----------------------|----------------------|----------------------------------------|
| `custom_auth` (general_settings) | YES | YES | YES |
| `async_pre_call_hook` (CustomLogger) | YES | YES | NO |
| FastAPI BaseHTTPMiddleware | YES | YES | YES |

Source: verified in `litellm/proxy/pass_through_endpoints/llm_passthrough_endpoints.py` and `litellm/proxy/anthropic_endpoints/endpoints.py` on BerriAI/litellm main branch.

---

## Documentation & References

| Resource | Description | Link |
|----------|-------------|------|
| Custom Auth docs | Function signature, config options, modes | https://docs.litellm.ai/docs/proxy/custom_auth |
| Anthropic Passthrough docs | `/anthropic/{endpoint}` passthrough usage | https://docs.litellm.ai/docs/pass_through/anthropic_completion |
| Pass-through endpoints docs | Custom passthrough config, auth field | https://docs.litellm.ai/docs/proxy/pass_through |
| All settings | Full config.yaml reference | https://docs.litellm.ai/docs/proxy/config_settings |
| Source: passthrough routes | llm_passthrough_endpoints.py | https://github.com/BerriAI/litellm/blob/main/litellm/proxy/pass_through_endpoints/llm_passthrough_endpoints.py |
| Source: user_api_key_auth | auth/user_api_key_auth.py | https://github.com/BerriAI/litellm/blob/main/litellm/proxy/auth/user_api_key_auth.py |

---

## custom_auth: Function Signature and Config

### config.yaml

```yaml
general_settings:
  custom_auth: mymodule.my_auth_function
  custom_auth_settings:
    mode: "on"   # "on" = only custom auth; "auto" = custom + LiteLLM both; "off" = disabled
```

### Function signature

```python
from fastapi import Request
from litellm.proxy._types import UserAPIKeyAuth

async def my_auth_function(request: Request, api_key: str) -> UserAPIKeyAuth:
    # request.headers contains all HTTP headers (Authorization, x-api-key, etc.)
    # api_key is extracted by LiteLLM from the Authorization / x-api-key header
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if token != "my-expected-secret":
        from litellm.proxy._types import ProxyException
        raise ProxyException(message="Unauthorized", type="auth_error", param=None, code=401)
    return UserAPIKeyAuth(api_key=api_key, user_id="my-user")
```

- Must be `async`
- `request`: FastAPI `Request` — access headers via `request.headers`
- `api_key`: already extracted by LiteLLM from `Authorization: Bearer ...` or `x-api-key` header
- Return `UserAPIKeyAuth` or a str (a valid LiteLLM key to substitute)
- Raise `ProxyException` (not a plain Exception) for structured error responses to the client

### ProxyException for clean error responses

```python
from litellm.proxy._types import ProxyException
raise ProxyException(
    message="Unauthorized: invalid token",
    type="auth_error",
    param=None,
    code=401,
)
```

---

## How user_api_key_auth Calls custom_auth (Source-Verified)

The flow in `litellm/proxy/auth/user_api_key_auth.py`:

```
user_api_key_auth(request, api_key, ...)
  └── if enterprise_custom_auth: call it
  └── elif user_custom_auth:            # ← your custom_auth function
        response = await user_custom_auth(request=request, api_key=api_key)
  └── else: standard LiteLLM key check
```

`user_custom_auth` is populated at startup from `general_settings.custom_auth` via `get_instance_fn()`.

---

## Passthrough Route Auth (Source-Verified)

`/anthropic/{endpoint:path}` in `llm_passthrough_endpoints.py`:

```python
@router.api_route(
    "/anthropic/{endpoint:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def anthropic_proxy_route(
    endpoint: str,
    request: Request,
    fastapi_response: Response,
    user_api_key_dict: UserAPIKeyAuth = Depends(user_api_key_auth),  # auth fires here
):
    ...
    # Then forwards raw HTTP to api.anthropic.com — no LiteLLM SDK call
```

Because `user_api_key_auth` is a `Depends`, FastAPI resolves it before the handler runs. `custom_auth` is called within `user_api_key_auth`. This is why `custom_auth` covers passthrough and `async_pre_call_hook` does not.

---

## Common Pitfalls & Solutions

| Issue | Impact | Solution |
|-------|--------|----------|
| Using `async_pre_call_hook` for auth expecting it to cover passthrough | Auth bypass on `/anthropic/*` | Migrate auth to `custom_auth` in general_settings |
| Raising plain `Exception` in custom_auth | LiteLLM may return 500 instead of 401 | Raise `ProxyException` with correct `code` |
| Reading headers from `data["proxy_server_request"]` in pre_call_hook | Only works in SDK path, not passthrough | In custom_auth, read from `request.headers` directly |
| `mode: "auto"` when master_key is set | LiteLLM also validates its own keys | Use `mode: "on"` to rely solely on custom auth |
| Custom pass-through endpoints (not built-in) need `auth: true` | Requests bypass auth | Add `auth: true` to each entry under `general_settings.pass_through_endpoints` — Enterprise feature |

---

## Patterns & Best Practices

### Migrating from async_pre_call_hook to custom_auth

The existing pattern in `request_transformer.py` reads headers from `data["proxy_server_request"]["headers"]` inside `async_pre_call_hook`. To cover passthrough, the auth check must move to a `custom_auth` function that receives `request: Request` directly:

```python
# OLD (misses passthrough):
async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
    headers = data.get("proxy_server_request", {}).get("headers", {})
    token = headers.get("x-litellm-api-key", "")
    if token != self.static_token:
        raise Exception("Unauthorized")

# NEW (covers all routes including passthrough):
async def my_auth(request: Request, api_key: str) -> UserAPIKeyAuth:
    token = request.headers.get("x-litellm-api-key", "") or api_key
    if token != os.environ.get("PROXY_STATIC_TOKEN", ""):
        raise ProxyException(message="Unauthorized", type="auth_error", param=None, code=401)
    return UserAPIKeyAuth(api_key=token)
```

### Coexistence: custom_auth + CustomLogger for non-auth transforms

Keep `CustomLogger` (callbacks) for request/response transforms and token rotation. Move only the auth/rejection logic to `custom_auth`. The two systems are independent and complementary.

---

## Sources & Verification

| Source | Type | Last Verified |
|--------|------|---------------|
| https://docs.litellm.ai/docs/proxy/custom_auth | Official | 2026-04-19 |
| https://github.com/BerriAI/litellm/blob/main/litellm/proxy/pass_through_endpoints/llm_passthrough_endpoints.py | Primary source | 2026-04-19 |
| https://github.com/BerriAI/litellm/blob/main/litellm/proxy/auth/user_api_key_auth.py | Primary source | 2026-04-19 |
| https://github.com/BerriAI/litellm/blob/main/litellm/proxy/anthropic_endpoints/endpoints.py | Primary source | 2026-04-19 |
| https://github.com/BerriAI/litellm/blob/main/litellm/proxy/proxy_server.py | Primary source | 2026-04-19 |

---

## Changelog

| Date | Changes |
|------|---------|
| 2026-04-19 | Initial creation — LiteLLM custom auth coverage for passthrough endpoints |
