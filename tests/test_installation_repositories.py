from __future__ import annotations

import httpx


def test_lists_every_repository_permitted_to_an_installation() -> None:
    from pr_reviewer.github.installation_repositories import list_installation_repositories

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.params.get("page") == "2":
            return httpx.Response(
                200,
                json={
                    "repositories": [
                        {"id": 22, "full_name": "acme/widgets", "private": True},
                    ]
                },
            )
        return httpx.Response(
            200,
            headers={
                "link": (
                    "<https://api.github.test/installation/repositories?per_page=100&page=2>; "
                    'rel="next"'
                )
            },
            json={
                "repositories": [
                    {"id": 11, "full_name": "acme/api", "private": False},
                ]
            },
        )

    repositories = list_installation_repositories(
        701,
        token_provider=lambda installation_id: "installation-token"
        if installation_id == 701
        else "",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        api_base_url="https://api.github.test",
    )

    actual = [
        (repository.id, repository.full_name, repository.private)
        for repository in repositories
    ]
    assert actual == [
        (11, "acme/api", False),
        (22, "acme/widgets", True),
    ]
    assert all(request.headers["authorization"] == "Bearer installation-token" for request in calls)
