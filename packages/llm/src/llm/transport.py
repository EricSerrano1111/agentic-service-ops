"""The only code that touches the Gemini SDK. Tests replace it with a fake transport."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel

from .config import LLMSettings


class Transport(Protocol):
    """Sends one request, with no retries of its own. Raises the SDK's errors as-is."""

    async def generate(
        self, *, model: str, prompt: str, response_model: type[BaseModel] | None
    ) -> Any:
        """Return an object with `.text` and `.usage_metadata`, like the SDK's response."""
        ...


class GeminiTransport:
    """google-genai async client, one request per call.

    The SDK's own retries stay off (`attempts=1`): the client's retry policy is the only
    one, so waits are counted once against `LLM_MAX_RETRY_WAIT_S`.
    """

    def __init__(self, settings: LLMSettings) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self._settings = settings
        self._client = genai.Client(
            api_key=settings.api_key.reveal(),
            http_options=types.HttpOptions(
                timeout=int(settings.request_timeout_s * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def __repr__(self) -> str:
        return f"GeminiTransport(mode={self._settings.mode!r})"

    async def generate(
        self, *, model: str, prompt: str, response_model: type[BaseModel] | None
    ) -> Any:
        types = self._types
        config = types.GenerateContentConfig(
            temperature=self._settings.temperature,
            thinking_config=types.ThinkingConfig(thinking_level=self._settings.thinking_level),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if response_model is not None:
            config.response_mime_type = "application/json"
            config.response_json_schema = response_model.model_json_schema()
        return await self._client.aio.models.generate_content(
            model=model, contents=prompt, config=config
        )
