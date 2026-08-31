from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import certifi
from dotenv import load_dotenv

from pr_reviewer.contracts.review_context import ContextBudget

load_dotenv()

LOCAL_DATABASE_URL = "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer"


@dataclass(frozen=True)
class Settings:
    database_url: str
    github_webhook_secret: str
    github_oauth_client_id: str
    github_oauth_client_secret: str
    github_app_id: str
    github_app_private_key: str


def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL)),
        github_webhook_secret=os.environ.get("GITHUB_WEBHOOK_SECRET", ""),
        github_oauth_client_id=os.environ.get("GITHUB_OAUTH_CLIENT_ID", ""),
        github_oauth_client_secret=os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", ""),
        github_app_id=os.environ.get("GITHUB_APP_ID", ""),
        github_app_private_key=os.environ.get("GITHUB_APP_PRIVATE_KEY", ""),
    )


# (context_window, output_allowance). The packer only ever sees window minus allowance.
MODEL_CONTEXT_WINDOWS: dict[str, tuple[int, int]] = {
    "gpt-4o-mini": (128_000, 16_384),
    "claude-3-5-haiku-latest": (200_000, 8_192),
}


def context_budget_for_model(model: str) -> ContextBudget:
    try:
        context_window, output_allowance = MODEL_CONTEXT_WINDOWS[model]
    except KeyError as exc:
        raise KeyError(model) from exc
    return ContextBudget.from_window(context_window, output_allowance)


def normalize_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("sslmode") == "verify-full" and "sslrootcert" not in query:
        query["sslrootcert"] = certifi.where()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
