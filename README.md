# LiteLLM Proxy for Claude Code

## Problem

Claude Code only speaks the Anthropic API. If you want to use alternative LLM providers (GLM, Kimi, OpenRouter, etc.) or rotate multiple Claude OAuth tokens across a team, there is no built-in way to do it.

## Solution

A [LiteLLM](https://github.com/BerriAI/litellm) proxy with a custom request transformer that converts Anthropic API calls into requests compatible with various providers. Claude Code connects to the proxy as if it were talking to Anthropic, and the proxy handles the rest.

## Quick Start

1. Configure environment:
   ```bash
   cp .env.example .env
   cp config.yaml.example config.yaml
   ```
   Edit `.env` and fill in your API keys:
   ```env
   ZAI_API_KEY=...
   KIMI_API_KEY=...
   OPENROUTER_API_KEY=...
   CLAUDE_OAUTH_TOKENS=sk-ant-oat-token1,sk-ant-oat-token2
   PROXY_STATIC_TOKEN=...
   LITELLM_MASTER_KEY=...
   ```
   Generate tokens: `openssl rand -hex 32`

2. Customize `config.yaml` for your deployment (add/remove models, adjust fallbacks).

3. Start the proxy:

   **Docker** (recommended for most setups):
   ```bash
   docker compose up -d
   ```

   **Bare metal** (for low-disk servers, no Docker needed):
   ```bash
   sudo ./install.sh
   ```
   Installs litellm via pip, creates a systemd service on port 4000. Files are symlinked from the repo.
   
   To update after code changes: `git pull && sudo ./install.sh` (detects existing install, just restarts).
   
   To check logs: `journalctl -u litellm-proxy -f`
   
   To remove: `sudo ./install.sh --uninstall`

## Claude Code Client Setup

Add to your Claude Code settings (`~/.claude/settings.json` or per-project `.claude/settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://your-server:4000",
    "ANTHROPIC_MODEL": "glm",
    "ANTHROPIC_CUSTOM_HEADERS": "x-litellm-api-key: YOUR_PROXY_STATIC_TOKEN",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
```

- `ANTHROPIC_BASE_URL` — point to your proxy instance
- `ANTHROPIC_MODEL` — the model alias from your `config.yaml` (e.g., `glm`, `kimi`, `openrouter`)
- `ANTHROPIC_CUSTOM_HEADERS` — passes the static auth token; the format is `x-litellm-api-key: YOUR_PROXY_STATIC_TOKEN` (no "Bearer" prefix)
- `API_TIMEOUT_MS` — request timeout in milliseconds (useful for slow models)
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` — disables telemetry and non-essential network requests

To skip the Claude Code onboarding screen, add to `~/.claude.json`:

```json
{
  "hasCompletedOnboarding": true
}
```

## How It Works

### Request Transformer

The proxy includes `request_transformer.py` — a custom LiteLLM callback that solves several compatibility problems when routing Anthropic API traffic to different providers:

1. **Claude OAuth Token Rotation** — Maintains a pool of Claude OAuth tokens (`CLAUDE_OAUTH_TOKENS` env var) and round-robins across them. Tokens that hit rate limits are automatically placed on a 60-second cooldown. When all tokens are cooling down, the one expiring soonest is used.

2. **OAuth Header Stripping** — Claude Code sends OAuth `Authorization` headers with every request. Non-Anthropic providers (GLM, Kimi) reject these headers. The transformer recursively strips them before forwarding.

3. **Thinking Block Removal (Requests)** — Some providers return "thinking" blocks in responses. Claude Code caches these in conversation history. When the conversation later routes to Anthropic, these cached blocks cause validation errors because Anthropic requires non-empty thinking content. The transformer strips thinking blocks from outgoing messages.

4. **Thinking Block Removal (Responses)** — OpenRouter returns reasoning/thinking blocks that would pollute the conversation cache. The transformer strips them from responses at the source.

### Static Token Authentication

`custom_auth.py` provides lightweight authentication without a database. Set the `PROXY_STATIC_TOKEN` env var and all requests must include a matching token via the `x-litellm-api-key` header. If `PROXY_STATIC_TOKEN` is not set, all requests are allowed.

This is the "light mode" — no database required. For per-user tokens and usage tracking, you can optionally configure LiteLLM's built-in database-backed auth instead.

### Claude OAuth Token Rotation

If your team uses multiple Claude Code Link sessions, you can pool the OAuth tokens for load balancing:

1. Each team member completes the Claude Code OAuth flow (Claude Code Link) to obtain an `sk-ant-oat-...` token
2. Collect the tokens and set them as a comma-separated list in the `CLAUDE_OAUTH_TOKENS` env var
3. The proxy rotates through tokens automatically, cooling down rate-limited ones

This allows the team to share Claude API capacity across multiple live sessions.

### Token Mode Control

By default, the proxy rotates tokens from the `CLAUDE_OAUTH_TOKENS` pool for all Claude requests. You can switch to **passthrough** mode where each client's own session token is forwarded to Claude API as-is.

**Global setting** (env var):
```env
CLAUDE_TOKEN_MODE=passthrough   # or "rotate" (default)
```

**Per-request override** (header): clients can override the global mode by adding `x-claude-token-mode` to their custom headers:
```json
{
  "env": {
    "ANTHROPIC_CUSTOM_HEADERS": "x-litellm-api-key: YOUR_TOKEN, x-claude-token-mode: passthrough"
  }
}
```

| Mode | Behavior |
|------|----------|
| `rotate` | Server picks next token from `CLAUDE_OAUTH_TOKENS` pool (default) |
| `passthrough` | Client's own Authorization token is forwarded to Claude API |

If mode is `rotate` but no tokens are configured in `CLAUDE_OAUTH_TOKENS`, the proxy automatically falls back to passthrough.

### Provider Switching

The proxy routes requests to different providers based on the model name. Supported models are configured in `config.yaml`:

| Model | Provider | Description |
|-------|----------|-------------|
| `glm` | ZAI API | GLM-5 |
| `glm-fast` | ZAI API | GLM-5-AIR (faster) |
| `kimi` | Kimi API | Kimi-for-coding |
| `openrouter` | OpenRouter | Qwen 3.6 Plus (free) |
| `anthropic/*` | Anthropic | All Claude models via OAuth wildcard |

Fallbacks: `anthropic/*` -> `glm`, `anthropic/claude-haiku-*` -> `glm-fast`

## Configuration

- **`config.yaml`** — Model routing, fallbacks, and LiteLLM settings. Customized per deployment; see `config.yaml.example` for the reference configuration.
- **`.env`** — API keys and tokens. See `.env.example` for all required variables.
- **`request_transformer.py`** — Request/response transformation callback.
- **`custom_auth.py`** — Static token authentication handler.
