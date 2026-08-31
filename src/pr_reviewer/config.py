from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import certifi
from dotenv import load_dotenv

LOCAL_DATABASE_HOST = "postgresql://pr_reviewer:pr_reviewer@localhost:54329"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def database_name_for_root(root: Path) -> str:
    raw = root.name.replace("-", "_")
    name = re.sub(r"[^A-Za-z0-9_]", "_", raw).lower()
    if not name or not name[0].isalpha():
        name = f"db_{name}" if name else "pr_reviewer"
    return name


def default_database_url(root: Path | None = None) -> str:
    return f"{LOCAL_DATABASE_HOST}/{database_name_for_root(root or _REPO_ROOT)}"


@dataclass(frozen=True)
class Settings:
    database_url: str
    github_webhook_secret: str
    github_oauth_client_id: str
    github_oauth_client_secret: str
    github_app_id: str
    github_app_private_key: str


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        database_url=normalize_database_url(
            os.environ.get("DATABASE_URL", default_database_url())
        ),
        github_webhook_secret=os.environ.get("GITHUB_WEBHOOK_SECRET", ""),
        github_oauth_client_id=os.environ.get("GITHUB_OAUTH_CLIENT_ID", ""),
        github_oauth_client_secret=os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", ""),
        github_app_id=os.environ.get("GITHUB_APP_ID", ""),
        github_app_private_key=os.environ.get("GITHUB_APP_PRIVATE_KEY", ""),
    )


def normalize_database_url(database_url: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("sslmode") == "verify-full" and "sslrootcert" not in query:
        query["sslrootcert"] = certifi.where()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
