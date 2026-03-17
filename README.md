# LiteLLM Proxy

A Docker Compose setup for running [LiteLLM](https://github.com/BerriAI/litellm) proxy with PostgreSQL database, configured for GLM models via ZAI API and Claude models via OAuth.

## Features

- **GLM Models**: Access GLM-5 and GLM-5-AIR via ZAI API
- **Claude Models**: Wildcard support for all Anthropic models via Claude Code OAuth
- **PostgreSQL**: Persistent database for API keys, usage tracking, and logs
- **OAuth Header Stripping**: Custom callback automatically removes OAuth headers for ZAI models

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
| `LITELLM_MASTER_KEY` | Master key for proxy administration |
| `DATABASE_URL` | PostgreSQL connection string (auto-configured in Docker) |

### Available Models

| Model Name | Backend | Description |
|------------|---------|-------------|
| `glm` | ZAI API | GLM-5 model |
| `glm-fast` | ZAI API | GLM-5-AIR (faster variant) |
| `anthropic/*` | Claude OAuth | All Anthropic models via wildcard |

### Ports

| Service | Host Port | Container Port |
|---------|-----------|----------------|
| LiteLLM Proxy | 4000 | 4000 |
| PostgreSQL | 5433 | 5432 |

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
  -d '{"models": ["glm", "glm-fast", "anthropic/*"], "key_alias": "my-key"}'
```

The response will contain a `key` field — save it, you'll need it for API requests and Claude Code configuration.

### Claude Code Configuration

Add the following to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "apiKeyHelper": "echo sk-your-virtual-key",
  "apiBaseUrl": "http://localhost:4000"
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

The `strip_oauth_callback.py` module automatically removes OAuth `Authorization` headers when routing requests to ZAI models. This prevents authentication conflicts when using Claude Code OAuth alongside the ZAI API.

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
