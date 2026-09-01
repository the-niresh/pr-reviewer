"""Proves no pricing, billing, or paid-tier surface exists anywhere in the web UI (Task 21.1)."""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

FORBIDDEN = re.compile(
    r"pricing|billing|subscription|paid (tier|plan)|upgrade to pro|premium|credit card|\$\d",
    re.IGNORECASE,
)


def test_no_billing_surface_in_web_source() -> None:
    offenders = []
    for path in WEB_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        if FORBIDDEN.search(text):
            offenders.append(str(path.relative_to(WEB_SRC)))
    assert offenders == [], f"billing/pricing language found in: {offenders}"
