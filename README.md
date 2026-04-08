# LiteLLM Proxy

A Docker Compose setup for running [LiteLLM](https://github.com/BerriAI/litellm) proxy, configured for GLM models via ZAI API, Kimi models, OpenRouter, and Claude models via OAuth.

## Features

- **GLM Models**: Access GLM-5 and GLM-5-AIR via ZAI API
- **Kimi Models**: Kimi-for-coding via Anthropic-compatible API
- **OpenRouter Models**: Access models via OpenRouter (e.g. Qwen)
- **Claude Models**: Wildcard support for all Anthropic models via Claude Code OAuth
- **Fallbacks**: Automatic fallback from Claude models to GLM
- **OAuth Header Stripping**: Custom callback automatically removes OAuth headers for non-Anthropic models

## Prerequisites

- Docker and Docker Compose
- ZAI API key (for GLM models)
- Claude Code OAuth setup (for Anthropic models)

## Quick Start

1. Create your environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your API keys:
   ```env
   ZAI_API_KEY=your_zai_api_key_here
   LITELLM_MASTER_KEY=your_secure_master_key_here
   ```
   Generate a secure master key with:
   ```bash
   echo "sk-litellm-master-$(openssl rand -hex 32)"
   ```

3. Start the services:
   ```bash
   docker compose up -d
   ```

4. Verify the proxy is running:
   ```bash
   curl http://localhost:4000/health
   ```

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ZAI_API_KEY` | API key for ZAI/GLM models |
| `KIMI_API_KEY` | API key for Kimi models |
| `OPENROUTER_API_KEY` | API key for OpenRouter |
| `LITELLM_MASTER_KEY` | Master key for proxy administration |

### Available Models

| Model Name | Backend | Description |
|------------|---------|-------------|
| `glm` | ZAI API | GLM-5 model |
| `glm-fast` | ZAI API | GLM-5-AIR (faster variant) |
| `kimi` | Kimi API | Kimi-for-coding |
| `openrouter` | OpenRouter | Qwen 3.6 Plus (free) |
| `anthropic/*` | Claude OAuth | All Anthropic models via wildcard |


## Admin UI

Access the LiteLLM dashboard at [http://localhost:4000/ui](http://localhost:4000/ui).

Login with:
- **Username:** any (e.g. `admin`)
- **Password:** your `LITELLM_MASTER_KEY`

From the UI you can manage API keys, view usage, and configure models.

## Usage

### Generate a Virtual API Key

After the proxy is running, generate a virtual API key:

```bash
curl -X POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer YOUR_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"models": ["glm", "glm-fast", "kimi", "openrouter", "anthropic/*"], "key_alias": "my-key"}'
```

The response will contain a `key` field — save it, you'll need it for API requests and Claude Code configuration.

### Claude Code Configuration

Add the following to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4000",
    "ANTHROPIC_MODEL": "glm",
    "ANTHROPIC_CUSTOM_HEADERS": "x-litellm-api-key: Bearer YOUR_VIRTUAL_KEY"
  }
}
```

### Making API Requests

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_VIRTUAL_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## OAuth Header Stripping

The `request_transformer.py` module automatically removes OAuth `Authorization` headers when routing requests to non-Anthropic models. This prevents authentication conflicts when using Claude Code OAuth alongside third-party APIs.

## Management

```bash
# View logs
docker compose logs -f litellm

# Stop services
docker compose down

# Stop and remove volumes
docker compose down -v
```

## License

MIT
