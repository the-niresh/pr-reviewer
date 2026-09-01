"""Hosted GitHub connect URL construction for the TUI."""

from __future__ import annotations

import pytest

from pr_reviewer.tui.github_connect import (
    HostedOriginError,
    app_slug_from_env,
    build_github_app_install_url,
    build_github_connect_urls,
    build_github_sign_in_url,
    hosted_origin_from_env,
    normalize_hosted_origin,
)


def test_normalize_hosted_origin_strips_trailing_slash() -> None:
    assert normalize_hosted_origin("https://reviewer.niresh.tech/") == "https://reviewer.niresh.tech"


def test_normalize_hosted_origin_rejects_loopback() -> None:
    with pytest.raises(HostedOriginError, match="loopback"):
        normalize_hosted_origin("https://127.0.0.1:8741")


def test_normalize_hosted_origin_rejects_http() -> None:
    with pytest.raises(HostedOriginError, match="https"):
        normalize_hosted_origin("http://reviewer.niresh.tech")


def test_build_github_sign_in_url_uses_hosted_origin() -> None:
    url = build_github_sign_in_url("https://reviewer.niresh.tech")
    assert url.startswith("https://reviewer.niresh.tech/api/auth/github/sign-in?")
    assert "return_to=%2Fdashboard" in url or "return_to=/dashboard" in url
    assert "127.0.0.1" not in url


def test_build_github_sign_in_url_rejects_unknown_return_to() -> None:
    with pytest.raises(HostedOriginError, match="allowlisted"):
        build_github_sign_in_url("https://reviewer.niresh.tech", return_to="/evil")


def test_build_github_app_install_url_uses_the_app_slug() -> None:
    assert (
        build_github_app_install_url("pr-reviewer")
        == "https://github.com/apps/pr-reviewer/installations/new"
    )


def test_build_github_connect_urls_returns_install_and_authorize() -> None:
    install_url, authorize_url = build_github_connect_urls(
        "https://reviewer.niresh.tech",
        app_slug="pr-reviewer",
    )
    assert install_url == "https://github.com/apps/pr-reviewer/installations/new"
    assert authorize_url.startswith("https://reviewer.niresh.tech/api/auth/github/sign-in?")


def test_hosted_origin_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PR_REVIEWER_HOSTED_ORIGIN", "https://reviewer.niresh.tech/")
    assert hosted_origin_from_env() == "https://reviewer.niresh.tech"


def test_app_slug_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_APP_SLUG", "pr-reviewer")
    assert app_slug_from_env() == "pr-reviewer"
