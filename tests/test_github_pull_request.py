from __future__ import annotations

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from pr_reviewer.contracts import PullRequestRef
from pr_reviewer.github.pull_request import (
    GitHubPullRequestFile,
    GitHubPullRequestResponse,
    fetch_pull_request,
    normalize_github_pull_request,
)
from pr_reviewer.github.tokens import GitHubAppSettings, build_app_jwt


def test_normalizes_changed_files_into_snapshot() -> None:
    response = GitHubPullRequestResponse(
        pull_request={
            "base": {"sha": "base-sha"},
            "head": {"sha": "head-sha"},
            "title": "Add auth guard",
            "body": "Protect private routes",
        },
        files=[
            GitHubPullRequestFile(
                filename="src/auth.py",
                status="modified",
                patch="@@ -1 +1 @@\n-old\n+new",
            ),
            GitHubPullRequestFile(
                filename="src/old.py",
                status="renamed",
                patch=None,
                previous_filename="src/legacy.py",
            ),
        ],
    )

    snapshot = normalize_github_pull_request(
        PullRequestRef(owner="foodspector", repository="api", number=42),
        response,
    )

    assert snapshot.repo_owner == "foodspector"
    assert snapshot.repo_name == "api"
    assert snapshot.number == 42
    assert snapshot.base_sha == "base-sha"
    assert snapshot.head_sha == "head-sha"
    assert snapshot.title == "Add auth guard"
    assert snapshot.body == "Protect private routes"
    assert snapshot.files[0].path == "src/auth.py"
    assert snapshot.files[0].status == "modified"
    assert snapshot.files[0].patch == "@@ -1 +1 @@\n-old\n+new"
    assert snapshot.files[1].previous_path == "src/legacy.py"


def test_rejects_unknown_file_status() -> None:
    response = GitHubPullRequestResponse(
        pull_request={
            "base": {"sha": "base-sha"},
            "head": {"sha": "head-sha"},
            "title": "Bad status",
            "body": None,
        },
        files=[
            GitHubPullRequestFile(
                filename="src/auth.py",
                status="unchanged",
                patch="@@ -1 +1 @@\n-old\n+new",
            )
        ],
    )

    with pytest.raises(ValueError, match="Unsupported GitHub file status"):
        normalize_github_pull_request(
            PullRequestRef(owner="foodspector", repository="api", number=42),
            response,
        )


def test_build_app_jwt_uses_rs256_header_and_claims() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    settings = GitHubAppSettings(app_id="123", private_key=private_key)

    token = build_app_jwt(settings, now_seconds=1_700_000_000)

    header, payload, signature = token.split(".")
    assert header
    assert payload
    assert signature


def test_fetch_pull_request_reads_all_file_pages() -> None:
    class TokenProvider:
        def create_installation_token(self, installation_id: int) -> str:
            assert installation_id == 99
            return "installation-token"

    class FakeClient:
        def __init__(self) -> None:
            self.urls: list[str] = []

        def get(
            self,
            url: str,
            *,
            headers: dict[str, str],
            timeout: float,
        ) -> httpx.Response:
            del timeout
            self.urls.append(url)
            assert headers["authorization"] == "Bearer installation-token"
            if url.endswith("/pulls/42"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json={
                        "base": {"sha": "base-sha"},
                        "head": {"sha": "head-sha"},
                        "title": "Paged files",
                        "body": None,
                    },
                )
            if url.endswith("/pulls/42/files"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    headers={
                        "link": (
                            "<https://api.example.test/repos/foodspector/api/"
                            'pulls/42/files?page=2>; rel="next"'
                        )
                    },
                    json=[
                        {
                            "filename": "src/one.py",
                            "status": "modified",
                            "patch": "@@ one",
                        }
                    ],
                )
            if url.endswith("/pulls/42/files?page=2"):
                return httpx.Response(
                    200,
                    request=httpx.Request("GET", url),
                    json=[
                        {
                            "filename": "src/two.py",
                            "status": "added",
                            "patch": "@@ two",
                        }
                    ],
                )
            raise AssertionError(f"Unexpected URL: {url}")

    client = FakeClient()
    snapshot = fetch_pull_request(
        PullRequestRef(owner="foodspector", repository="api", number=42),
        installation_id=99,
        token_provider=TokenProvider(),
        client=client,
        api_base_url="https://api.example.test",
    )

    assert [file.path for file in snapshot.files] == ["src/one.py", "src/two.py"]
