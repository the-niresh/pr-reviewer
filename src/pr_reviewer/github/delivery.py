"""Build a complete GitHubDelivery from a webhook body.

The fixture was wrong, not the contract. A partial payload must fail here so the
webhook can return 400. This module must not import db, control_plane, runner,
or local_store.
"""

from __future__ import annotations

from pr_reviewer.contracts.github import GitHubDelivery, PullRequestRef, RepositoryIdentity


def delivery_from_webhook(
    delivery_id: str,
    event_name: str,
    payload: object,
) -> GitHubDelivery:
    if not isinstance(payload, dict):
        raise TypeError("webhook payload must be an object")
    action = payload.get("action")
    if not isinstance(action, str) or not action:
        raise ValueError("missing action")
    installation = payload.get("installation")
    repository = payload.get("repository")
    pull_request = payload.get("pull_request")
    if not isinstance(installation, dict):
        raise ValueError("missing installation")
    if not isinstance(repository, dict):
        raise ValueError("missing repository")
    if not isinstance(pull_request, dict):
        raise ValueError("missing pull_request")
    owner_obj = repository.get("owner")
    if not isinstance(owner_obj, dict):
        raise ValueError("missing repository owner")
    owner = owner_obj.get("login")
    name = repository.get("name")
    if not isinstance(owner, str) or not owner:
        raise ValueError("missing repository owner login")
    if not isinstance(name, str) or not name:
        raise ValueError("missing repository name")
    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict):
        raise ValueError("missing pull_request shas")
    draft = pull_request.get("draft", False)
    if not isinstance(draft, bool):
        raise ValueError("draft must be a bool")
    identity = RepositoryIdentity(
        installation_id=int(installation["id"]),
        repository_id=int(repository["id"]),
        owner=owner,
        name=name,
    )
    return GitHubDelivery(
        delivery_id=delivery_id,
        event=event_name,
        action=action,
        repository_identity=identity,
        pull_request=PullRequestRef(
            owner=owner,
            repository=name,
            number=int(pull_request["number"]),
        ),
        draft=draft,
        base_sha=str(base["sha"]),
        head_sha=str(head["sha"]),
    )
