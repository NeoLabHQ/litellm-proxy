# LiteLLM Proxy

LiteLLM proxy for Claude Code — routes Anthropic API calls to alternative providers with token rotation and request transformation.

## Project Structure

```
config.yaml.example       # Reference config — copy to config.yaml
.env.example               # Reference env — copy to .env
config.yaml                # Active config (gitignored)
.env                       # Active secrets (gitignored)
custom_auth.py             # Static token auth handler
request_transformer.py     # Request/response transformation callback
Dockerfile                 # Docker deployment (litellm v1.83.7)
docker-compose.yml         # Docker orchestration
install.sh                 # Bare-metal installer (pip + systemd)
```

## Deployment

### Docker (default)

```bash
docker compose up -d --build
```

Rebuilds the image and restarts. Config files are bind-mounted read-only.

### Bare Metal (low-disk servers)

```bash
sudo ./install.sh              # Install (first run) or restart (subsequent runs)
sudo ./install.sh --uninstall  # Remove everything
```

Installs litellm via pip in a venv at `/opt/litellm-proxy/`, runs as a systemd service on port 4000. Files are symlinked from the repo — no copying.

## Update Workflow

After making changes to `request_transformer.py`, `custom_auth.py`, or `config.yaml`:

- **Docker:** `docker compose up -d` (bind-mounted files, restart picks up changes)
- **Bare metal:** `git pull && sudo ./install.sh` (files are symlinked, script detects existing install and just restarts)

## Version Pinning

LiteLLM version is pinned in both deployment methods:
- `Dockerfile`: image tag `main-v1.83.7-stable`
- `install.sh`: pip install `litellm[proxy]==1.83.7`

Keep these in sync when upgrading.

## Key Design Decisions

- No database — `allow_requests_on_db_unavailable: true` in config
- Static token auth via `PROXY_STATIC_TOKEN` env var (no per-user keys)
- Token rotation pool via `CLAUDE_OAUTH_TOKENS` with automatic cooldown on 429s
- Tool schema flattening for Anthropic API compatibility (oneOf/allOf/anyOf)
