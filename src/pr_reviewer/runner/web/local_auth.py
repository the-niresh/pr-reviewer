"""Loopback onboarding app (Runtime Task 8).

Binds 127.0.0.1 only and signs its own session. The model API key is written to SecretStore and
never logged, never put in os.environ, and never returned in a response body.

Pairing exchange and pairing status go through an injectable client. This module does not import
the hosted pairing or OAuth packages. Production status polls the hosted
/api/runner/pairing-codes/status route with the pairing code and the PKCE challenge.

The one origin crossing is sending the browser to the hosted GitHub sign-in URL. return_to is an
allowlisted hosted path (/dashboard), not a loopback URL. The local app never receives an OAuth
token or installation-access proof; it only learns, via status(), whether a code is exchangeable.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets as secrets_lib
from typing import Literal, Protocol
from urllib.parse import urlencode

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pr_reviewer.containers.runtime import ContainerProbe
from pr_reviewer.contracts.runner import PairingDenied, RunnerCredential
from pr_reviewer.runner.modes import RuntimeMode, select_runtime_mode
from pr_reviewer.runner.secrets import SecretStore

LOCAL_MODEL_KEY_SECRET_NAME = "model_key"
_CSRF_COOKIE = "pr_reviewer_csrf"
# Matches the hosted sign-in allowlist without importing that module.
_ALLOWED_HOSTED_RETURN_TO_PATHS = frozenset({"/dashboard"})
_LOOPBACK_UI_ORIGINS = ("http://127.0.0.1:3000",)
PairingStatus = Literal["pending", "exchangeable", "invalid_or_expired"]


class LocalAuthError(RuntimeError):
    """The loopback onboarding app cannot start or cannot accept the requested bind."""


class PairingClient(Protocol):
    def exchange(self, code: str, proof: str) -> RunnerCredential | PairingDenied: ...

    def status(self, code: str, challenge: str) -> PairingStatus: ...


class ModelKeyBody(BaseModel):
    provider: str = Field(min_length=1)
    key: str = Field(min_length=1)


class ExchangeBody(BaseModel):
    code: str = Field(min_length=1)
    proof: str = Field(min_length=1)


class PendingPairingClient:
    """Hosted pairing over HTTPS. exchange and status are both outbound polls."""

    def __init__(self, hosted_origin: str) -> None:
        self._hosted_origin = hosted_origin.rstrip("/")

    def exchange(self, code: str, proof: str) -> RunnerCredential | PairingDenied:
        import httpx

        response = httpx.post(
            f"{self._hosted_origin}/api/runner/pairing-codes/exchange",
            json={"code": code, "proof": proof},
            timeout=30.0,
        )
        payload = response.json()
        if response.status_code == 400:
            reason = payload.get("detail", "invalid_or_expired_code")
            if reason not in (
                "invalid_or_expired_code",
                "repository_not_in_installation",
                "revoked_installation",
                "unknown_installation",
            ):
                reason = "invalid_or_expired_code"
            return PairingDenied(reason=reason)
        return RunnerCredential.model_validate(payload)

    def status(self, code: str, challenge: str) -> PairingStatus:
        import httpx

        response = httpx.get(
            f"{self._hosted_origin}/api/runner/pairing-codes/status",
            params={"code": code, "challenge": challenge},
            timeout=30.0,
        )
        payload = response.json()
        raw_state = payload.get("state")
        result: PairingStatus
        if raw_state == "pending":
            result = "pending"
        elif raw_state == "exchangeable":
            result = "exchangeable"
        else:
            result = "invalid_or_expired"
        return result


def create_local_onboarding_app(
    *,
    host: str,
    session_secret: str,
    secrets: SecretStore,
    pairing_client: PairingClient,
    probe: ContainerProbe,
    requested_mode: RuntimeMode = "full",
    hosted_origin: str,
    return_to: str = "/dashboard",
) -> FastAPI:
    if host != "127.0.0.1":
        raise LocalAuthError(f"onboarding binds 127.0.0.1 only, not {host!r}")
    if not session_secret:
        raise LocalAuthError("a random local session secret is required")
    origin = _hosted_origin(hosted_origin)
    if return_to not in _ALLOWED_HOSTED_RETURN_TO_PATHS:
        raise LocalAuthError(f"return_to {return_to!r} is not an allowlisted hosted path")

    decision = select_runtime_mode(probe, requested_mode)
    app = FastAPI(title="PR Reviewer local onboarding")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_LOOPBACK_UI_ORIGINS),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-CSRF-Token", "Content-Type"],
    )
    secret_bytes = session_secret.encode("utf-8")

    @app.get("/onboarding/session")
    def session() -> JSONResponse:
        token = secrets_lib.token_urlsafe(32)
        response = JSONResponse({"csrf_token": token})
        response.set_cookie(
            key=_CSRF_COOKIE,
            value=_sign(secret_bytes, token),
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/onboarding/pairing/sign-in")
    def pairing_sign_in() -> dict[str, str]:
        query = urlencode({"return_to": return_to})
        return {"url": f"{origin}/api/auth/github/sign-in?{query}"}

    @app.get("/onboarding/pairing/status")
    def pairing_status(code: str, challenge: str) -> dict[str, str]:
        state = pairing_client.status(code, challenge)
        return {"state": state}

    @app.get("/onboarding/mode")
    def mode_preview() -> dict[str, object]:
        return {
            "granted_mode": decision.granted_mode,
            "requested_mode": decision.requested_mode,
            "downgraded": decision.downgraded,
            "disabled_features": list(decision.disabled_features),
            "forces_human_approval": decision.forces_human_approval,
        }

    @app.post("/onboarding/model-key")
    def store_model_key(
        body: ModelKeyBody,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        if not _csrf_ok(secret_bytes, request, x_csrf_token):
            return JSONResponse({"error": "csrf"}, status_code=403)
        del body.provider
        secrets.set(LOCAL_MODEL_KEY_SECRET_NAME, body.key)
        return JSONResponse({"stored": True})

    @app.post("/onboarding/pairing/exchange")
    def exchange_pairing(
        body: ExchangeBody,
        request: Request,
        x_csrf_token: str | None = Header(default=None),
    ) -> JSONResponse:
        if not _csrf_ok(secret_bytes, request, x_csrf_token):
            return JSONResponse({"error": "csrf"}, status_code=403)
        result = pairing_client.exchange(body.code, body.proof)
        if isinstance(result, PairingDenied):
            return JSONResponse({"reason": result.reason}, status_code=400)
        secrets.set("runner_credential", result.credential)
        return JSONResponse({"exchanged": True, "runner_id": str(result.runner_id)})

    return app


def _hosted_origin(origin: str) -> str:
    cleaned = origin.rstrip("/")
    if not cleaned.startswith("https://"):
        raise LocalAuthError("hosted_origin must be an https URL")
    if "127.0.0.1" in cleaned or "localhost" in cleaned:
        raise LocalAuthError("hosted_origin must not be loopback")
    return cleaned


def _sign(secret: bytes, token: str) -> str:
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{token}.{digest}"


def _csrf_ok(secret: bytes, request: Request, header: str | None) -> bool:
    if not header:
        return False
    cookie = request.cookies.get(_CSRF_COOKIE, "")
    if "." not in cookie:
        return False
    token, digest = cookie.rsplit(".", 1)
    expected = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(token, header) and hmac.compare_digest(digest, expected)
