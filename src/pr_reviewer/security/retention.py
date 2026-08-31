"""Retention scoped to one repository. Shared installation data stays.

Hosted deletes run through control_plane.retention. Local deletes run through
LocalJobStore.purge_repository. This module is the policy and the deadline.
It does not import pr_reviewer.db.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta
from typing import Any


class RetentionSweepTimedOut(RuntimeError):
    """The retention sweep would run after its hard deadline."""


def uninstall_repository(
    *,
    installation_id: int,
    github_repository_id: int,
    now: datetime,
    deadline: datetime,
) -> None:
    if now >= deadline:
        raise RetentionSweepTimedOut("retention sweep missed its deadline")
    hosted = importlib.import_module("pr_reviewer.control_plane.retention")
    hosted.purge_hosted_repository(installation_id, github_repository_id)


def purge_expired_local(
    store: Any,
    *,
    github_repository_id: int,
    now: datetime,
    deadline: datetime,
    snapshot_max_age: timedelta,
) -> None:
    del snapshot_max_age
    if now >= deadline:
        raise RetentionSweepTimedOut("retention sweep missed its deadline")
    store.jobs.purge_repository(github_repository_id)
