"""Build hosted GitHub App install and authorize URLs for the TUI."""

from __future__ import annotations

import os
from urllib.parse import urlencode

ALLOWED_RETURN_TO_PATHS = frozenset({"/dashboard"})
GITHUB_APP_INSTALL_URL = "https://github.com/apps/{app_slug}/installations/new"
GITHUB_SIGN_IN_PATH = "/api/auth/github/sign-in"


class HostedOriginError(ValueError):
    """The hosted origin or connect parameters are invalid."""


def normalize_hosted_origin(origin: str) -> str:
    cleaned = origin.rstrip("/")
    if not cleaned.startswith("https://"):
        raise HostedOriginError("hosted_origin must be an https URL")
    lowered = cleaned.lower()
    if "127.0.0.1" in lowered or "localhost" in lowered:
        raise HostedOriginError("hosted_origin must not be loopback")
    return cleaned


def build_github_sign_in_url(hosted_origin: str, *, return_to: str = "/dashboard") -> str:
    if return_to not in ALLOWED_RETURN_TO_PATHS:
        raise HostedOriginError(f"return_to {return_to!r} is not allowlisted")
    origin = normalize_hosted_origin(hosted_origin)
    query = urlencode({"return_to": return_to})
    return f"{origin}{GITHUB_SIGN_IN_PATH}?{query}"


def build_github_app_install_url(app_slug: str) -> str:
    slug = app_slug.strip()
    if not slug or "/" in slug or " " in slug:
        raise HostedOriginError("app_slug must be a single non-empty path segment")
    return GITHUB_APP_INSTALL_URL.format(app_slug=slug)


def build_github_connect_urls(
    hosted_origin: str,
    *,
    app_slug: str,
    return_to: str = "/dashboard",
) -> tuple[str, str]:
    """Return (app_install_url, authorize_url) for the TUI connect step."""

    install_url = build_github_app_install_url(app_slug)
    authorize_url = build_github_sign_in_url(hosted_origin, return_to=return_to)
    return install_url, authorize_url


def hosted_origin_from_env() -> str:
    origin = os.environ.get("PR_REVIEWER_HOSTED_ORIGIN", "").strip()
    if not origin:
        raise HostedOriginError("PR_REVIEWER_HOSTED_ORIGIN is not set")
    return normalize_hosted_origin(origin)


def app_slug_from_env() -> str:
    slug = os.environ.get("GITHUB_APP_SLUG", "").strip()
    if not slug:
        raise HostedOriginError("GITHUB_APP_SLUG is not set")
    return slug
