from __future__ import annotations

import hmac
from hashlib import sha256

from pr_reviewer.github import verify_github_signature


def test_verifies_github_signature() -> None:
    body = b'{"action":"opened"}'
    secret = "top-secret"
    digest = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()

    assert verify_github_signature(body, f"sha256={digest}", secret)


def test_rejects_invalid_signature() -> None:
    assert not verify_github_signature(b"{}", "sha256=bad", "top-secret")
    assert not verify_github_signature(b"{}", "sha256=" + "0" * 64, "")
