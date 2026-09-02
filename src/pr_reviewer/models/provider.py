"""Runner-side model adapter interface. Holds no hosted database handle.

The hosted ledger type for openai|anthropic is ModelProviderName in events/record_model_call.py.
This module's ModelProvider is the adapter Protocol. They are different types.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pr_reviewer.contracts.finding_candidate import FindingCandidate
from pr_reviewer.models.providers import provider_auth_headers
from pr_reviewer.security.prompt_boundaries import UntrustedText, wrap_untrusted

ModelVendor = Literal["openai", "anthropic"]

# USD per million tokens (input, output). Unknown models fail closed so cost cannot go uncounted.
_PRICE_PER_MILLION: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("openai", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("anthropic", "claude-3-5-haiku-latest"): (Decimal("0.80"), Decimal("4.00")),
}


class ModelTimeout(Exception):
    """The provider did not answer before ModelRequest.timeout_seconds."""


class InvalidModelJson(Exception):
    """The provider returned a body that is not JSON."""


class ModelSchemaMismatch(Exception):
    """The provider JSON did not match the requested schema."""


class ModelContextLimit(Exception):
    """The prompt exceeded the model's context window."""


class ModelRateLimit(Exception):
    """The provider rejected the call as rate limited."""


class ModelProviderFailure(Exception):
    """Any other provider HTTP or protocol failure."""


class ModelKeyInvalid(Exception):
    """The provider rejected the API key before any review ran."""


class UntrustedInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    content: str


class ModelRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    prompt_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    prompt_content: str = Field(min_length=1)
    schema_name: str = Field(min_length=1)
    untrusted_inputs: list[UntrustedInput]
    timeout_seconds: float = Field(gt=0)
    max_output_tokens: int = Field(gt=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    parsed: dict[str, Any]
    output_hash: str = Field(min_length=64, max_length=64)
    provider_request_id: str | None
    provider: ModelVendor
    model: str
    prompt_name: str
    prompt_version: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: str
    latency_ms: int = Field(ge=0)


class ModelProvider(Protocol):
    def complete_json(self, request: ModelRequest) -> ModelResponse: ...


def quote_untrusted(block: UntrustedInput) -> str:
    return wrap_untrusted(block.name, UntrustedText(block.content))


def render_untrusted_user_message(request: ModelRequest) -> str:
    return "\n\n".join(quote_untrusted(block) for block in request.untrusted_inputs)


def model_call_ledger_fields(response: ModelResponse) -> dict[str, Any]:
    """Aggregates plus identifiers. Never a key, a prompt, or a raw request."""
    return {
        "provider": response.provider,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cost_usd": response.cost_usd,
        "latency_ms": response.latency_ms,
        "output_hash": response.output_hash,
        "provider_request_id": response.provider_request_id,
        "prompt_name": response.prompt_name,
        "prompt_version": response.prompt_version,
    }


def cost_usd_for(provider: str, model: str, input_tokens: int, output_tokens: int) -> str:
    prices = _PRICE_PER_MILLION.get((provider, model))
    if prices is None:
        raise ModelProviderFailure(f"unknown model {provider}/{model}")
    input_price, output_price = prices
    million = Decimal("1000000")
    total = (Decimal(input_tokens) / million * input_price) + (
        Decimal(output_tokens) / million * output_price
    )
    text = format(total, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text else "0"


def finish_completion(
    *,
    vendor: ModelVendor,
    request: ModelRequest,
    content: str,
    input_tokens: int,
    output_tokens: int,
    provider_request_id: str | None,
    latency_ms: int,
) -> ModelResponse:
    try:
        parsed: object = json.loads(content)
    except (TypeError, json.JSONDecodeError) as exc:
        raise InvalidModelJson() from exc
    if not isinstance(parsed, dict):
        raise InvalidModelJson()
    if request.schema_name == "FindingCandidate":
        try:
            FindingCandidate.model_validate(parsed)
        except ValidationError as exc:
            raise ModelSchemaMismatch() from exc
    elif request.schema_name == "ReviewFindingsDraft":
        findings = parsed.get("findings")
        if not isinstance(findings, list):
            raise ModelSchemaMismatch()
    else:
        raise ModelSchemaMismatch()
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return ModelResponse(
        parsed=parsed,
        output_hash=digest,
        provider_request_id=provider_request_id,
        provider=vendor,
        model=request.model,
        prompt_name=request.prompt_name,
        prompt_version=request.prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd_for(vendor, request.model, input_tokens, output_tokens),
        latency_ms=latency_ms,
    )


def verify_provider_api_key(
    provider_id: ModelVendor,
    api_key: str,
    *,
    http: httpx.Client | None = None,
) -> None:
    """Probe the provider with a lightweight models listing call."""
    if provider_id == "openai":
        client = http if http is not None else httpx.Client(base_url="https://api.openai.com")
        response = client.get(
            "/v1/models",
            headers=provider_auth_headers("openai", api_key),
            timeout=10.0,
        )
    else:
        client = http if http is not None else httpx.Client(base_url="https://api.anthropic.com")
        response = client.get(
            "/v1/models",
            headers=provider_auth_headers("anthropic", api_key),
            timeout=10.0,
        )
    if response.status_code in {401, 403}:
        raise ModelKeyInvalid()
    if response.status_code != 200:
        raise ModelProviderFailure()


def raise_for_provider_status(response: httpx.Response) -> None:
    if response.status_code == 200:
        return
    if response.status_code == 429:
        raise ModelRateLimit()
    payload: Any
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    code = ""
    message = ""
    if isinstance(error, dict):
        code = str(error.get("code") or "")
        message = str(error.get("message") or "").lower()
    if response.status_code == 400 and (
        code == "context_length_exceeded" or "too long" in message
    ):
        raise ModelContextLimit()
    raise ModelProviderFailure()
