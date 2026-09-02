"""Task 33.C8: /api/profile carries the signed-in viewer's own GitHub identity, and the
live-sign-in cookie's login field must survive a real seal/read round trip.

Follows tests/test_web_reviews.py's harness (TestClient against the real control plane app,
a real sealed cookie via issue_live_sign_in).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pr_reviewer.control_plane.app import app
from pr_reviewer.control_plane.github_auth import LiveInstallationAssertion
from pr_reviewer.control_plane.github_oauth import (
    LIVE_SIGN_IN_COOKIE_NAME,
    issue_live_sign_in,
    read_live_sign_in,
)

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
PROFILE_PAGE = WEB_SRC / "app" / "dashboard" / "profile" / "page.tsx"
SETTINGS_PAGE = WEB_SRC / "app" / "dashboard" / "settings" / "page.tsx"
DASHBOARD_SHELL = WEB_SRC / "components" / "DashboardShell.tsx"


def _client(cookie: str | None = None) -> TestClient:
    cookies = {LIVE_SIGN_IN_COOKIE_NAME: cookie} if cookie is not None else {}
    return TestClient(app, cookies=cookies)


def _signed_in_cookie(github_user_id: int = 1, login: str | None = "octocat") -> str:
    assertion = LiveInstallationAssertion(
        github_user_id=github_user_id, login=login, installations={}, expires_at=2_000_000_000
    )
    return issue_live_sign_in(assertion)


def test_no_cookie_is_401() -> None:
    response = _client().get("/api/profile")
    assert response.status_code == 401


def test_signed_in_viewer_gets_their_own_identity() -> None:
    cookie = _signed_in_cookie(github_user_id=42, login="octocat")
    response = _client(cookie).get("/api/profile")
    assert response.status_code == 200
    body = response.json()
    assert body == {"github_user_id": 42, "login": "octocat"}


def test_a_cookie_sealed_without_login_still_decodes_with_login_none() -> None:
    """The guard this task needs: login must be additive, never a hard requirement that
    locks out every session sealed before this field existed."""
    assertion = LiveInstallationAssertion(
        github_user_id=7, installations={}, expires_at=2_000_000_000
    )
    assert assertion.login is None
    cookie = issue_live_sign_in(assertion)

    read_back = read_live_sign_in(cookie)
    assert read_back is not None
    assert read_back.login is None
    assert read_back.github_user_id == 7

    response = _client(cookie).get("/api/profile")
    assert response.status_code == 200
    assert response.json() == {"github_user_id": 7, "login": None}


def test_login_survives_a_real_seal_and_read_round_trip() -> None:
    cookie = _signed_in_cookie(github_user_id=9, login="niresh")
    read_back = read_live_sign_in(cookie)
    assert read_back is not None
    assert read_back.login == "niresh"


def test_profile_page_exists() -> None:
    assert PROFILE_PAGE.is_file(), f"missing {PROFILE_PAGE}"


def test_settings_page_exists() -> None:
    assert SETTINGS_PAGE.is_file(), f"missing {SETTINGS_PAGE}"


def test_settings_page_links_to_github_never_a_local_permission_editor() -> None:
    source = SETTINGS_PAGE.read_text(encoding="utf-8")
    assert "github.com/apps/" in source, (
        "settings must link to GitHub to change permission -- only GitHub can grant it"
    )


def test_dashboard_shell_links_profile_and_settings_with_current_page_marking() -> None:
    source = DASHBOARD_SHELL.read_text(encoding="utf-8")
    assert '"/dashboard/profile"' in source
    assert '"/dashboard/settings"' in source
    assert "aria-current" in source
