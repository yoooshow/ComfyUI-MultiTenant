# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This is a preview version of Google GenAI custom nodes

import json
import os
from typing import Optional

from google import genai

from .custom_exceptions import ConfigurationError
from .logger import get_node_logger

logger = get_node_logger(__name__)


class VertexAIClient:
    """
    A base class for initializing genai.Client in API key mode.
    Compatible with official Google endpoints and third-party relay/proxy services.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Initializes the client in API Key mode.

        Credentials are loaded from settings.json in this directory
        if not explicitly passed as arguments.

        Args:
            api_key: API key for the relay/proxy or Google API.
            base_url: Base URL override (e.g. 'https://4sapi.com').
            user_agent: The user agent string.

        Raises:
            ConfigurationError: If api_key is not provided or client init fails.
        """
        if not api_key or not base_url:
            cfg_path = os.path.join(os.path.dirname(__file__), "settings.json")
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path) as f:
                        cfg = json.load(f)
                    if not api_key:
                        api_key = cfg.get("api_key", "")
                    if not base_url:
                        base_url = cfg.get("base_url", "")
                except Exception:
                    pass
        if not api_key:
            raise ConfigurationError("api_key is required.")

        http_options_kwargs = {}
        if base_url:
            http_options_kwargs["base_url"] = base_url
        if user_agent:
            http_options_kwargs["headers"] = {"user-agent": user_agent}

        http_options = (
            genai.types.HttpOptions(**http_options_kwargs)
            if http_options_kwargs else None
        )

        try:
            self.client = genai.Client(
                vertexai=False,
                api_key=api_key,
                http_options=http_options,
            )
        except Exception as e:
            raise ConfigurationError(
                f"Failed to initialize genai.Client: {e}"
            )
