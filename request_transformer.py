"""
LiteLLM Request/Response Transformer Callback

This callback handles compatibility issues when using multiple LLM providers
through a single LiteLLM proxy. It performs four key transformations:

1. Claude OAuth Token Rotation
   - Maintains a pool of shared Claude OAuth tokens (CLAUDE_OAUTH_TOKENS env var)
   - Round-robins across tokens, with automatic cooldown on rate-limited ones
   - Injects the pooled token via data["api_key"] for Claude/Anthropic models

2. OAuth Header Stripping for Non-Claude Models (GLM, Kimi)
   - Some providers don't accept OAuth Authorization headers
   - Claude Code sends OAuth headers for all requests
   - We strip these headers before forwarding to non-Claude endpoints

3. Thinking Block Removal from Anthropic Requests
   - Some providers (e.g., OpenRouter) return "thinking" blocks in responses
   - Claude Code caches these blocks in conversation history
   - Anthropic's API rejects requests with empty thinking blocks
   - We strip thinking blocks from messages before sending to Anthropic

4. Thinking Block Removal from OpenRouter Responses
   - OpenRouter returns reasoning/thinking blocks in responses
   - These get cached by Claude Code and cause issues later
   - We strip them at the source to prevent pollution

Usage:
    In config.yaml:
        litellm_settings:
            callbacks:
                - request_transformer.request_transformer

    In .env:
        CLAUDE_OAUTH_TOKENS=sk-ant-oat-token1,sk-ant-oat-token2,sk-ant-oat-token3

Static token authentication is handled separately via custom_auth.py
(configured as general_settings.custom_auth in config.yaml).
"""

import os
import time
import threading

from litellm.integrations.custom_logger import CustomLogger

# Cooldown duration in seconds for rate-limited tokens
TOKEN_COOLDOWN_SECONDS = 60


class RequestTransformer(CustomLogger):
    """
    Custom LiteLLM callback that transforms requests and responses
    for multi-provider compatibility, with Claude OAuth token rotation.
    """

    def __init__(self):
        super().__init__()
        raw = os.environ.get("CLAUDE_OAUTH_TOKENS", "")
        self.tokens = [t.strip() for t in raw.split(",") if t.strip()]
        self.cooldowns = {}  # token -> cooldown_until timestamp
        self.index = 0
        self.lock = threading.Lock()

        if self.tokens:
            print(f"[TokenRotator] Loaded {len(self.tokens)} Claude OAuth tokens", flush=True)
        else:
            print("[TokenRotator] No CLAUDE_OAUTH_TOKENS configured — Claude models will use client-provided auth", flush=True)

    def _get_next_token(self):
        """Get next available token using round-robin, skipping cooled-down ones."""
        with self.lock:
            now = time.time()
            # Try to find a non-cooled-down token
            for _ in range(len(self.tokens)):
                token = self.tokens[self.index % len(self.tokens)]
                self.index += 1
                cooldown_until = self.cooldowns.get(token, 0)
                if cooldown_until < now:
                    return token
            # All tokens are cooling down — return the one that expires soonest
            return min(self.tokens, key=lambda t: self.cooldowns.get(t, 0))

    def _cooldown_token(self, token):
        """Put a token on cooldown after a rate limit."""
        with self.lock:
            self.cooldowns[token] = time.time() + TOKEN_COOLDOWN_SECONDS
            # Mask token for logging: show first 15 and last 4 chars
            masked = f"{token[:15]}...{token[-4:]}" if len(token) > 19 else "***"
            print(f"[TokenRotator] Token {masked} cooled down for {TOKEN_COOLDOWN_SECONDS}s", flush=True)

    def _is_claude_model(self, model):
        """Check if a model is a Claude/Anthropic model."""
        return "claude" in model or "anthropic" in model

    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        """
        Called before each LLM API request. Transforms the request data
        based on the target model/provider.

        Args:
            user_api_key_dict: User API key information
            cache: LiteLLM cache object
            data: Request data dict containing 'model', 'messages', etc.
            call_type: Type of API call (completion, embedding, etc.)

        Returns:
            Modified request data dict
        """
        model = data.get("model", "")

        # Rotate Claude OAuth token from pool (if configured)
        self._inject_pooled_token(model, data)

        # Strip OAuth headers for non-Claude models (GLM, Kimi don't accept them)
        self._strip_oauth_for_non_claude(model, data)

        # Strip thinking blocks for Anthropic models (API validation requirement)
        self._strip_thinking_blocks_for_anthropic(model, data)

        return data

    async def async_post_call_success_hook(self, data, user_api_key_dict, response):
        """
        Called after a successful LLM API response. Transforms the response
        to ensure compatibility with Claude Code.

        Args:
            data: Original request data dict
            user_api_key_dict: User API key information
            response: LLM API response object

        Returns:
            Modified response object
        """
        model = data.get("model", "") if isinstance(data, dict) else ""
        
        # Strip thinking blocks from OpenRouter responses to prevent caching issues
        return self._strip_thinking_blocks_from_openrouter_response(model, response)

    def _inject_pooled_token(self, model, data):
        """
        For Claude/Anthropic models, replace the client's auth with a pooled token.
        Strips the client's forwarded Authorization header and sets data["api_key"].
        """
        if not self.tokens or not self._is_claude_model(model):
            return

        token = self._get_next_token()
        data["api_key"] = token

        # Store which token we used so we can cool it down on failure
        metadata = data.get("metadata", {})
        metadata["_pooled_token"] = token
        data["metadata"] = metadata

        # Strip any client-forwarded Authorization headers
        self._remove_auth_headers(data)

        masked = f"{token[:15]}...{token[-4:]}" if len(token) > 19 else "***"
        print(f"[TokenRotator] Using token {masked} for {model}", flush=True)

    def _remove_auth_headers(self, data):
        """Remove Authorization headers from all nested dicts in data."""
        if isinstance(data, dict):
            for key in ["authorization", "Authorization"]:
                if key in data:
                    del data[key]
            for val in data.values():
                if isinstance(val, dict):
                    self._remove_auth_headers(val)

    async def async_post_call_failure_hook(self, request_data, original_exception, user_api_key_dict):
        """Cool down a token if it got rate-limited (HTTP 429)."""
        if not self.tokens:
            return

        status_code = getattr(original_exception, "status_code", None)
        if status_code != 429:
            return

        metadata = request_data.get("metadata", {}) if isinstance(request_data, dict) else {}
        token = metadata.get("_pooled_token")
        if token:
            self._cooldown_token(token)

    def _strip_oauth_for_non_claude(self, model, data):
        """
        Remove OAuth Authorization headers for non-Claude models.
        
        Some providers (GLM via ZAI, Kimi) reject requests with OAuth headers,
        but Claude Code includes them for all requests. This recursively searches
        and removes both 'authorization' and 'Authorization' keys from all nested dicts.
        
        Args:
            model: Model name string (e.g., "glm", "glm-fast", "kimi")
            data: Request data dict to modify in-place
        """
        # List of model prefixes that don't accept OAuth headers
        # - GLM models via ZAI API
        # - Kimi models via Kimi API
        non_claude_models = ["glm", "kimi"]

        # Skip if not a non-Claude model
        # Check both the model name and after any provider prefix (e.g., "anthropic/kimi-...")
        model_without_prefix = model.split("/", 1)[-1] if "/" in model else model
        if not any(model.startswith(m) or model_without_prefix.startswith(m) for m in non_claude_models):
            return

        print(f"[Transform] Non-Claude model detected: {model}", flush=True)

        def remove_auth_recursive(obj, path=""):
            """
            Recursively search and remove authorization headers from nested dicts.
            
            Args:
                obj: Object to search (dict or other)
                path: Current path in the structure (for logging)
            """
            if isinstance(obj, dict):
                # Remove both lowercase and capitalized variants
                for key in ["authorization", "Authorization"]:
                    if key in obj:
                        print(f"[Transform] Removing '{key}' at {path}", flush=True)
                        del obj[key]
                
                # Recursively search nested dictionaries
                for key, val in list(obj.items()):
                    if isinstance(val, dict):
                        remove_auth_recursive(val, f"{path}.{key}")

        remove_auth_recursive(data, "data")

    def _strip_thinking_blocks_for_anthropic(self, model, data):
        """
        Remove thinking blocks from messages for Anthropic/Claude models.
        
        Anthropic's API validates thinking blocks strictly - each must contain
        non-empty thinking content. When switching from providers that return
        thinking blocks (e.g., OpenRouter) to Anthropic, cached thinking blocks
        may cause validation errors. This strips them proactively.
        
        Args:
            model: Model name string (e.g., "claude-sonnet-4-6", "anthropic/claude-3")
            data: Request data dict containing 'messages' to modify in-place
        """
        # Only process Anthropic/Claude models
        if "claude" not in model and "anthropic" not in model:
            return

        messages = data.get("messages", [])
        
        for msg in messages:
            # Check if message has content blocks (not simple string content)
            if "content" in msg and isinstance(msg["content"], list):
                original_len = len(msg["content"])
                
                # Filter out thinking blocks
                msg["content"] = [
                    block for block in msg["content"]
                    if not (isinstance(block, dict) and block.get("type") == "thinking")
                ]
                
                # Log if we removed any blocks
                if len(msg["content"]) < original_len:
                    print(f"[Transform] Stripped {original_len - len(msg['content'])} thinking blocks from request", flush=True)

    def _strip_thinking_blocks_from_openrouter_response(self, model, response):
        """
        Remove thinking blocks from OpenRouter responses.
        
        OpenRouter returns reasoning/thinking blocks in responses (e.g., from
        Qwen models). These get cached by Claude Code in conversation history.
        When later switching to Anthropic models, these cached blocks cause
        API validation errors. Stripping them at the source prevents this issue.
        
        Args:
            model: Model name string (e.g., "openrouter")
            response: Response object with choices containing message content
            
        Returns:
            Modified response object with thinking blocks removed
        """
        # Only process OpenRouter models
        if "openrouter" not in str(model):
            return response

        # Check if response has the expected structure
        if not (hasattr(response, 'choices') and response.choices):
            return response

        # Process each choice in the response
        for choice in response.choices:
            if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                # Check if content is structured as blocks (not simple string)
                if isinstance(choice.message.content, list):
                    original_len = len(choice.message.content)
                    
                    # Filter out thinking blocks
                    choice.message.content = [
                        block for block in choice.message.content
                        if not (isinstance(block, dict) and block.get('type') == 'thinking')
                    ]
                    
                    # Log if we removed any blocks
                    if len(choice.message.content) < original_len:
                        print(f"[Transform] Stripped {original_len - len(choice.message.content)} thinking blocks from response", flush=True)

        return response


# Singleton instance for LiteLLM to import
request_transformer = RequestTransformer()
