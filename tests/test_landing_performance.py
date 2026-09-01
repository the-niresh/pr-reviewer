"""Task 21.4: the landing route ships a bounded, non-blocking JS bundle.

No Lighthouse and no Lighthouse score here, on explicit instruction: this measures the real
`next build` output instead of a browser metric this environment cannot run. Anything that
would need a real browser (paint timing, CLS) is out of scope for this test and is not
asserted as a number.
"""

from __future__ import annotations

import gzip
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "apps" / "web"
NEXT_DIR = WEB / ".next"
JS_BUDGET_BYTES = 150 * 1024  # web/performance.md: landing page JS budget, gzipped.

EXTERNAL_SCRIPT_TAG = re.compile(r'<script\b[^>]*\bsrc="[^"]+"[^>]*>', re.IGNORECASE)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
# "module" is deliberately a substring match, not a \b-bounded word: nomodule="" (the legacy
# polyfill fallback, gated on the browser NOT supporting ES modules) is one camelCase token
# with no word boundary before "Module", the same reason async/defer stay substring checks too.
BLOCKING_EXEMPT_SUBSTRINGS = ("async", "defer", "module")


@pytest.fixture(scope="module")
def built() -> None:
    result = subprocess.run(
        ["bun", "run", "build"],
        cwd=WEB,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"next build failed:\n{result.stdout}\n{result.stderr}"


def _gzip_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9))


def _landing_html() -> str:
    return (NEXT_DIR / "server" / "app" / "index.html").read_text(encoding="utf-8")


def test_landing_route_js_is_under_the_gzipped_budget(built: None) -> None:
    manifest = json.loads((NEXT_DIR / "app-build-manifest.json").read_text(encoding="utf-8"))
    chunk_paths = manifest["pages"]["/page"]
    js_files = [path for path in chunk_paths if path.endswith(".js")]
    assert js_files, "no JS chunks found for the landing route"

    total_gzipped = sum(_gzip_size(NEXT_DIR / path) for path in js_files)
    assert total_gzipped < JS_BUDGET_BYTES, (
        f"landing route ships {total_gzipped} gzipped bytes of JS, "
        f"over the {JS_BUDGET_BYTES} byte budget"
    )


def test_landing_route_has_no_render_blocking_script(built: None) -> None:
    offenders = [
        tag
        for tag in EXTERNAL_SCRIPT_TAG.findall(_landing_html())
        if not any(substring in tag.lower() for substring in BLOCKING_EXEMPT_SUBSTRINGS)
    ]
    assert offenders == [], f"render-blocking script tag(s) found: {offenders}"


def test_landing_route_images_have_explicit_dimensions(built: None) -> None:
    images = IMG_TAG.findall(_landing_html())
    missing = [img for img in images if "width=" not in img.lower() or "height=" not in img.lower()]
    assert missing == [], f"img tag(s) missing explicit width/height: {missing}"
