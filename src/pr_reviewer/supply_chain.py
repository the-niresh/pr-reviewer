"""Local-and-CI supply-chain checks: lock, secrets, container pins, generated docs."""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]

PEM_RE = re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")
TOKEN_RE = re.compile(r"(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}")
POSTGRES_RE = re.compile(r"postgres(?:ql)?://[^\s'\"\\]+")
OPENAI_RE = re.compile(r"\bsk-[A-Za-z0-9]{20,}")
FROM_RE = re.compile(r"^\s*FROM\s+(\S+)", re.IGNORECASE)
IMAGE_RE = re.compile(r"^\s+image:\s+(\S+)", re.IGNORECASE)
PINNED_RE = re.compile(r"@sha256:[a-fA-F0-9]{64}$")
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "example.com"})
CONTAINER_FILES = (
    "Dockerfile",
    "compose.release.yml",
    "docker-compose.ci.yml",
    ".github/workflows/ci.yml",
)
REGEX_SOURCE_FILES = frozenset({"src/pr_reviewer/connectors/audit.py"})
COMMANDS = ("lock", "secrets", "containers", "generated")


def _git_tracked_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def _is_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return True


def _postgres_host_ok(match: str) -> bool:
    cleaned = match.rstrip(").,;\"'")
    host = urlsplit(cleaned).hostname
    if host in LOCAL_DB_HOSTS:
        return True
    return "127.0.0.1" in cleaned or "localhost" in cleaned


def secret_refusals(relative: str, text: str) -> list[str]:
    if relative.endswith(".md") or relative.startswith("tests/"):
        return []
    hits: list[str] = []
    allow_regex_source = relative in REGEX_SOURCE_FILES
    for line_no, line in enumerate(text.splitlines(), start=1):
        if PEM_RE.search(line) and not allow_regex_source:
            hits.append(f"{relative}:{line_no}: private-key header")
        if TOKEN_RE.search(line) and not allow_regex_source:
            hits.append(f"{relative}:{line_no}: github token")
        if OPENAI_RE.search(line) and not allow_regex_source:
            hits.append(f"{relative}:{line_no}: sk- token")
        for url in POSTGRES_RE.findall(line):
            if not _postgres_host_ok(url):
                hits.append(f"{relative}:{line_no}: remote postgres url")
    return hits


def unpinned_image_refs(relative: str, text: str) -> list[str]:
    hits: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        refs = FROM_RE.findall(line) + IMAGE_RE.findall(line)
        for ref in refs:
            cleaned = ref.strip("\"'")
            if cleaned.startswith("#"):
                continue
            if not PINNED_RE.search(cleaned) or ":latest" in cleaned:
                hits.append(f"{relative}:{line_no}: unpinned {cleaned}")
    return hits


def check_lock(root: Path) -> int:
    result = subprocess.run(["uv", "lock", "--check"], cwd=root)
    if result.returncode == 0:
        print("lock: uv.lock matches the project", flush=True)
    return result.returncode


def check_secrets(root: Path) -> int:
    hits: list[str] = []
    for relative in _git_tracked_files(root):
        path = root / relative
        if not path.is_file() or not _is_text(path):
            continue
        hits.extend(secret_refusals(relative, path.read_text(encoding="utf-8")))
    if hits:
        print("secret scan refused:", file=sys.stderr, flush=True)
        for hit in hits:
            print(hit, file=sys.stderr, flush=True)
        return 1
    print("secret scan: no refused hits in tracked files", flush=True)
    return 0


def check_containers(root: Path) -> int:
    hits: list[str] = []
    scanned: list[str] = []
    for relative in CONTAINER_FILES:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        scanned.append(relative)
        hits.extend(unpinned_image_refs(relative, text))
    if hits:
        print("container scan refused:", file=sys.stderr, flush=True)
        for hit in hits:
            print(hit, file=sys.stderr, flush=True)
        return 1
    print("container scan: digest-pinned images in " + ", ".join(scanned), flush=True)
    return 0


def check_generated(root: Path) -> int:
    script = root / "scripts" / "generate_data_boundaries_doc.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=root,
    )
    return result.returncode


def run_command(name: str, root: Path) -> int:
    if name == "lock":
        return check_lock(root)
    if name == "secrets":
        return check_secrets(root)
    if name == "containers":
        return check_containers(root)
    if name == "generated":
        return check_generated(root)
    print(f"unknown check {name}", file=sys.stderr, flush=True)
    return 2


def main(argv: Sequence[str] | None = None, root: Path | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    target = root if root is not None else REPO
    names = list(COMMANDS) if not args or args == ["all"] else args
    worst = 0
    for name in names:
        code = run_command(name, target)
        if code != 0:
            worst = code
    return worst
