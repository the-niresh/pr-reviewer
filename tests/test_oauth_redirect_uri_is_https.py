"""The redirect_uri handed to GitHub must be the https hosted origin.

Traefik terminates TLS and forwards plain HTTP, so request.base_url reports
http://reviewer.niresh.tech and the sign-in redirect carried an http redirect_uri that
does not match the App's https callback. GitHub rejects that mismatch, so sign-in could
never complete. The hosted origin is read from configuration instead, which is also not
spoofable through a Host header.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from pr_reviewer.control_plane.app import app


def _redirect_uri(client: TestClient) -> str:
    response = client.get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )
    assert response.status_code == 302, response.text
    query = parse_qs(urlsplit(response.headers["location"]).query)
    return query["redirect_uri"][0]


def test_redirect_uri_uses_the_https_hosted_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PR_REVIEWER_HOSTED_ORIGIN", "https://reviewer.example.test")
    uri = _redirect_uri(TestClient(app))
    assert uri == "https://reviewer.example.test/api/auth/github/callback"


def test_a_plain_http_request_still_produces_an_https_redirect_uri(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This is the actual production shape: the proxy speaks http to the app."""
    monkeypatch.setenv("PR_REVIEWER_HOSTED_ORIGIN", "https://reviewer.example.test")
    client = TestClient(app, base_url="http://reviewer.example.test")
    assert _redirect_uri(client).startswith("https://")


def test_an_unset_hosted_origin_refuses_rather_than_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset origin must not fall back to the request host or to http."""
    monkeypatch.setenv("PR_REVIEWER_HOSTED_ORIGIN", "")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/auth/github/sign-in", params={"return_to": "/dashboard"}, follow_redirects=False
    )
    assert response.status_code == 500
