# LiteLLM Proxy

[LiteLLM](https://github.com/BerriAI/litellm) proxy setup for routing requests across multiple LLM providers with automatic fallbacks.

## Models

| Model | Provider | Description |
|-------|----------|-------------|
| `glm` | ZAI API | GLM-5 |
| `glm-fast` | ZAI API | GLM-5-AIR (faster) |
| `kimi` | Kimi API | Kimi-for-coding |
| `openrouter` | OpenRouter | Qwen 3.6 Plus (free) |
| `anthropic/*` | Anthropic | All Claude models via OAuth wildcard |

Fallbacks: `anthropic/*` -> `glm`, `anthropic/claude-haiku-*` -> `glm-fast`

## Quick Start

1. Configure environment:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in your API keys:
   ```env
   ZAI_API_KEY=...
   KIMI_API_KEY=...
   OPENROUTER_API_KEY=...
   PROXY_STATIC_TOKEN=...
   LITELLM_MASTER_KEY=...
   ```
   Generate tokens: `openssl rand -hex 32`

2. Start the proxy:
   ```bash
   docker compose up -d
   ```

3. Set `PROXY_STATIC_TOKEN` in `.env` — share this token with teammates. All requests must include it via `x-litellm-api-key` header.

## Claude Code Configuration

Global (`~/.claude/settings.json`) or per-project (`.claude/settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000",
    "ANTHROPIC_MODEL": "glm",
    "ANTHROPIC_CUSTOM_HEADERS": "x-litellm-api-key: Bearer YOUR_PROXY_STATIC_TOKEN",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
  }
}
```

- `API_TIMEOUT_MS` — request timeout (useful for slow models)
- `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` — disables telemetry and non-essential network requests

To skip the Claude Code onboarding screen, add to `~/.claude.json`:

```json
{
  "hasCompletedOnboarding": true
}
```

## Admin UI

[http://localhost:4000/ui](http://localhost:4000/ui) — login with any username and your `LITELLM_MASTER_KEY` as password.

## Notes

- `request_transformer.py` validates static token and strips OAuth headers when routing to non-Anthropic providers
