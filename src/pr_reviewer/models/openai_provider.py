"""OpenAI adapter. The API key stays on this object and in the Authorization header."""

from __future__ import annotations

import time

import httpx

from pr_reviewer.models.provider import (
    ModelProviderFailure,
    ModelRequest,
    ModelResponse,
    ModelTimeout,
    finish_completion,
    raise_for_provider_status,
    render_untrusted_user_message,
)
from pr_reviewer.models.providers import provider_auth_headers


class OpenAIProvider:
    def __init__(self, api_key: str, http: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._http = http if http is not None else httpx.Client(base_url="https://api.openai.com")

    def complete_json(self, request: ModelRequest) -> ModelResponse:
        started = time.perf_counter()
        body = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": request.prompt_content},
                {"role": "user", "content": render_untrusted_user_message(request)},
            ],
        }
        try:
            response = self._http.post(
                "/v1/chat/completions",
                json=body,
                headers=provider_auth_headers("openai", self._api_key),
                timeout=request.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise ModelTimeout() from exc
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        raise_for_provider_status(response)
        payload = response.json()
        try:
            content = str(payload["choices"][0]["message"]["content"])
            usage = payload.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
            request_id = payload.get("id")
            provider_request_id = str(request_id) if request_id is not None else None
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderFailure() from exc
        return finish_completion(
            vendor="openai",
            request=request,
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_request_id=provider_request_id,
            latency_ms=latency_ms,
        )
