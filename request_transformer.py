"""
LiteLLM Request/Response Transformer Callback

This callback handles compatibility issues when using multiple LLM providers
through a single LiteLLM proxy. It performs three key transformations:

1. OAuth Header Stripping for GLM Models (ZAI API)
   - ZAI's GLM models don't accept OAuth Authorization headers
   - Claude Code sends OAuth headers for all requests
   - We strip these headers before forwarding to ZAI endpoints

2. Thinking Block Removal from Anthropic Requests
   - Some providers (e.g., OpenRouter) return "thinking" blocks in responses
   - Claude Code caches these blocks in conversation history
   - Anthropic's API rejects requests with empty thinking blocks
   - We strip thinking blocks from messages before sending to Anthropic

3. Thinking Block Removal from OpenRouter Responses
   - OpenRouter returns reasoning/thinking blocks in responses
   - These get cached by Claude Code and cause issues later
   - We strip them at the source to prevent pollution

Usage:
    In config.yaml:
        litellm_settings:
            callbacks:
                - request_transformer.request_transformer
"""

from litellm.integrations.custom_logger import CustomLogger


class RequestTransformer(CustomLogger):
    """
    Custom LiteLLM callback that transforms requests and responses
    for multi-provider compatibility.
    """
    
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
        
        # Strip OAuth headers for GLM models (ZAI doesn't accept them)
        self._strip_oauth_for_zai(model, data)
        
        # Strip thinking blocks for Anthropic models (API validation requirement)
        self._strip_thinking_blocks_for_anthropic(model, data)
        
        return data

    async def async_post_call_success_hook(self, user_api_key_dict, cache, data, response, call_type):
        """
        Called after a successful LLM API response. Transforms the response
        to ensure compatibility with Claude Code.
        
        Args:
            user_api_key_dict: User API key information
            cache: LiteLLM cache object
            data: Original request data dict
            response: LLM API response object
            call_type: Type of API call
            
        Returns:
            Modified response object
        """
        model = data.get("model", "") if isinstance(data, dict) else ""
        
        # Strip thinking blocks from OpenRouter responses to prevent caching issues
        return self._strip_thinking_blocks_from_openrouter_response(model, response)

    def _strip_oauth_for_zai(self, model, data):
        """
        Remove OAuth Authorization headers for GLM/ZAI models.
        
        ZAI's API endpoints reject requests with OAuth headers, but Claude Code
        includes them for all requests. This recursively searches and removes
        both 'authorization' and 'Authorization' keys from all nested dicts.
        
        Args:
            model: Model name string (e.g., "glm", "glm-fast")
            data: Request data dict to modify in-place
        """
        # List of model prefixes that route through ZAI API
        zai_models = ["glm"]
        
        # Skip if not a ZAI model
        if not any(model.startswith(m) for m in zai_models):
            return

        print(f"[Transform] GLM model detected: {model}", flush=True)

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
