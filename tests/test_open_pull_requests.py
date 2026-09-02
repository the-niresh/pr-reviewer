from __future__ import annotations

import httpx


def test_lists_open_non_draft_pull_requests_newest_first() -> None:
    from pr_reviewer.github.open_pull_requests import list_open_pull_requests

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repositories/801/pulls"
        assert dict(request.url.params) == {
            "state": "open",
            "sort": "updated",
            "direction": "desc",
        }
        return httpx.Response(
            200,
            json=[
                {
                    "number": 14,
                    "title": "Fresh change",
                    "user": {"login": "sam"},
                    "head": {"sha": "b" * 40},
                    "updated_at": "2026-09-02T10:00:00Z",
                    "draft": False,
                },
                {
                    "number": 13,
                    "title": "Draft change",
                    "user": {"login": "pat"},
                    "head": {"sha": "a" * 40},
                    "updated_at": "2026-09-02T09:00:00Z",
                    "draft": True,
                },
            ],
        )

    pull_requests = list_open_pull_requests(
        801,
        token_provider=lambda installation_id: "installation-token"
        if installation_id == 701
        else "",
        installation_id=701,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api_base_url="https://api.github.test",
    )

    assert [
        (pull_request.number, pull_request.title, pull_request.author, pull_request.head_sha,
         pull_request.updated_at)
        for pull_request in pull_requests
    ] == [(14, "Fresh change", "sam", "b" * 40, "2026-09-02T10:00:00Z")]
