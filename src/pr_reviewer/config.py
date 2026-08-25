from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import certifi
from dotenv import load_dotenv

load_dotenv()

LOCAL_DATABASE_URL = "postgresql://pr_reviewer:pr_reviewer@localhost:54329/pr_reviewer"


@dataclass(frozen=True)
class Settings:
    database_url: str
    github_webhook_secret: str


def get_settings() -> Settings:
    return Settings(
        database_url=normalize_database_url(os.environ.get("DATABASE_URL", LOCAL_DATABASE_URL)),
        github_webhook_secret=os.environ.get("GITHUB_WEBHOOK_SECRET", ""),
    )


def normalize_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("sslmode") == "verify-full" and "sslrootcert" not in query:
        query["sslrootcert"] = certifi.where()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
