"""Phase 23: the authorize URL is built from the hosted origin, never hardcoded, and a missing
or empty hosted origin refuses rather than falling back to a default host.

Fuller coverage of the same module already exists in test_tui_github_connect_url.py; this file
exists at the exact path the spec cites so its generator can find the proof.
"""

from __future__ import annotations

import pytest

from pr_reviewer.tui.github_connect import (
    HostedOriginError,
    build_github_sign_in_url,
    hosted_origin_from_env,
)


def test_authorize_url_is_built_from_the_given_hosted_origin_not_hardcoded() -> None:
    url = build_github_sign_in_url("https://reviewer.example.test", return_to="/dashboard")
    assert url.startswith("https://reviewer.example.test/api/auth/github/sign-in")

    other_url = build_github_sign_in_url("https://other-host.example.test", return_to="/dashboard")
    assert other_url.startswith("https://other-host.example.test/")
    assert other_url != url


def test_missing_hosted_origin_env_refuses_rather_than_defaulting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PR_REVIEWER_HOSTED_ORIGIN", raising=False)
    with pytest.raises(HostedOriginError):
        hosted_origin_from_env()


def test_empty_hosted_origin_refuses_rather_than_defaulting() -> None:
    with pytest.raises(HostedOriginError):
        build_github_sign_in_url("", return_to="/dashboard")
