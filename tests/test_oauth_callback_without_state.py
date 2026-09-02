"""Reaching the callback without a state must refuse, and say so in words.

Installing the GitHub App redirects the user to the callback with a code and an
installation_id but no state, because that flow starts at GitHub rather than at our
/sign-in. State is CSRF protection, so the code must still be refused. What this
covers is that the refusal is legible: a person saw a raw FastAPI validation dump and
could not tell whether the product was broken or had rejected them on purpose.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from pr_reviewer.control_plane.app import app


def _client() -> TestClient:
    return TestClient(app, follow_redirects=False)


def test_callback_without_state_refuses_and_explains() -> None:
    response = _client().get("/api/auth/github/callback?code=abc123&installation_id=1")
    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Start sign-in" in body
    assert "/api/auth/github/sign-in" in body


def test_callback_without_state_never_sets_a_session_cookie() -> None:
    """The readable page must not become a way in. No state, no session."""
    response = _client().get("/api/auth/github/callback?code=abc123")
    assert response.status_code == 400
    assert response.cookies.get("pr_reviewer_live_sign_in") is None
    assert not any(
        "live_sign_in" in value for value in response.headers.get_list("set-cookie")
    )


def test_callback_still_requires_a_code() -> None:
    """Only state was relaxed to a readable refusal; code stays mandatory."""
    response = _client().get("/api/auth/github/callback")
    assert response.status_code == 422
