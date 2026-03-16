"""
Custom LiteLLM callback that strips the OAuth Authorization header
for non-Claude models (e.g., GLM via ZAI).
"""

import json
import traceback
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth


class StripOAuthForZAI(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict, cache, data, call_type):
        model = data.get("model", "")

        zai_models = ["glm"]
        is_zai_model = any(model.startswith(m) for m in zai_models)

        if not is_zai_model:
            return data

        print(f"[StripOAuth] GLM model detected: {model}", flush=True)
        print(f"[StripOAuth] Top-level keys: {list(data.keys())}", flush=True)

        # Search for authorization in ALL nested dicts
        def find_and_remove_auth(obj, path=""):
            if isinstance(obj, dict):
                if "authorization" in obj:
                    print(f"[StripOAuth] FOUND 'authorization' at {path}", flush=True)
                    del obj["authorization"]
                if "Authorization" in obj:
                    print(f"[StripOAuth] FOUND 'Authorization' at {path}", flush=True)
                    del obj["Authorization"]
                for key, val in list(obj.items()):
                    if isinstance(val, dict):
                        find_and_remove_auth(val, f"{path}.{key}")

        find_and_remove_auth(data, "data")

        # Also check specific known locations
        for key in ["provider_specific_header", "litellm_metadata", "metadata",
                     "proxy_server_request", "litellm_params", "optional_params"]:
            if key in data:
                val = data[key]
                if isinstance(val, dict):
                    print(f"[StripOAuth] data['{key}'] keys: {list(val.keys())[:20]}", flush=True)

        return data


strip_oauth_for_zai = StripOAuthForZAI()
