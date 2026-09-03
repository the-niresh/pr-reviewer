from __future__ import annotations

import httpx

from pr_reviewer.control_plane.installation_lifecycle import (
    handle_installation_event,
    handle_installation_repositories_event,
)
from pr_reviewer.db.client import connection

FAKE_API_BASE_URL = "https://api.github.test"


def _fake_http_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(
                201, json={"token": "installation-token", "expires_at": "2099-01-01T00:00:00Z"}
            )
        return httpx.Response(
            200,
            json={"repositories": [{"id": 11, "full_name": "acme/api", "private": False}]},
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def _installation_row(installation_id: int) -> dict[str, object] | None:
    with connection() as conn:
        row = conn.execute(
            "select account_login, revoked_at from installations where id = %s",
            (installation_id,),
        ).fetchone()
    return dict(row) if row is not None else None


def test_installation_created_registers_installation_and_its_repositories() -> None:
    payload = {"action": "created", "installation": {"id": 5001, "account": {"login": "acme"}}}

    handle_installation_event(
        payload, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )

    assert _installation_row(5001) == {"account_login": "acme", "revoked_at": None}
    with connection() as conn:
        repo = conn.execute(
            "select github_repository_id, name from repositories where installation_id = %s",
            (5001,),
        ).fetchone()
    assert repo is not None
    assert repo["github_repository_id"] == 11
    assert repo["name"] == "acme/api"


def test_installation_created_is_redelivery_safe() -> None:
    payload = {"action": "created", "installation": {"id": 5002, "account": {"login": "acme"}}}

    handle_installation_event(
        payload, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )
    handle_installation_event(
        payload, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )

    assert _installation_row(5002) == {"account_login": "acme", "revoked_at": None}


def test_installation_deleted_revokes_a_registered_installation() -> None:
    created = {"action": "created", "installation": {"id": 5003, "account": {"login": "acme"}}}
    handle_installation_event(
        created, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )

    deleted = {"action": "deleted", "installation": {"id": 5003, "account": {"login": "acme"}}}
    handle_installation_event(
        deleted, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )

    row = _installation_row(5003)
    assert row is not None
    assert row["revoked_at"] is not None


def test_installation_repositories_added_registers_the_named_repositories() -> None:
    created = {"action": "created", "installation": {"id": 5004, "account": {"login": "acme"}}}
    handle_installation_event(
        created, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )

    payload = {
        "installation": {"id": 5004},
        "repositories_added": [{"id": 22, "full_name": "acme/widgets"}],
    }
    handle_installation_repositories_event(payload)

    with connection() as conn:
        repo = conn.execute(
            "select name from repositories"
            " where installation_id = %s and github_repository_id = %s",
            (5004, 22),
        ).fetchone()
    assert repo is not None
    assert repo["name"] == "acme/widgets"


def test_unrecognized_action_is_ignored_without_error() -> None:
    payload = {
        "action": "some_future_action",
        "installation": {"id": 5005, "account": {"login": "acme"}},
    }

    handle_installation_event(
        payload, http_client=_fake_http_client(), api_base_url=FAKE_API_BASE_URL
    )

    assert _installation_row(5005) is None
