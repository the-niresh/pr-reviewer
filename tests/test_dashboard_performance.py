"""Task 27.5: the dashboard routes ship a bounded, non-blocking JS bundle.

No Lighthouse and no Lighthouse score here, same rule as test_landing_performance.py: this
measures the real `next build` output. /dashboard/reviews is server-rendered per request (it
reads the viewer's session cookie), so it has no prerendered HTML to inspect; its JS budget is
still checked from the real build manifest, and the script/image checks that need real HTML are
refused for it with a reason, not skipped silently and not asserted as a guess.
"""

from __future__ import annotations

import gzip
import json
import re
import subprocess
from pathlib import Path
from typing import cast

import pytest

REPO = Path(__file__).resolve().parent.parent
WEB = REPO / "apps" / "web"
NEXT_DIR = WEB / ".next"
APP_PAGE_JS_BUDGET_BYTES = 300 * 1024  # web/performance.md: app page JS budget, gzipped.

EXTERNAL_SCRIPT_TAG = re.compile(r'<script\b[^>]*\bsrc="[^"]+"[^>]*>', re.IGNORECASE)
IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
BLOCKING_EXEMPT_SUBSTRINGS = ("async", "defer", "module")

# manifest key -> static HTML file relative to .next/server/app, or None if server-rendered
# per request and therefore has no prerendered HTML to inspect.
DASHBOARD_ROUTES: dict[str, str | None] = {
    "/dashboard/page": "dashboard.html",
    "/dashboard/connectors/page": "dashboard/connectors.html",
    "/dashboard/evals/page": "dashboard/evals.html",
    "/dashboard/reviews/page": None,
}


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


def _manifest() -> dict[str, list[str]]:
    data = json.loads((NEXT_DIR / "app-build-manifest.json").read_text(encoding="utf-8"))
    return cast(dict[str, list[str]], data["pages"])


@pytest.mark.parametrize("route", sorted(DASHBOARD_ROUTES))
def test_dashboard_route_js_is_under_the_gzipped_budget(built: None, route: str) -> None:
    chunk_paths = _manifest()[route]
    js_files = [path for path in chunk_paths if path.endswith(".js")]
    assert js_files, f"no JS chunks found for {route}"

    total_gzipped = sum(_gzip_size(NEXT_DIR / path) for path in js_files)
    assert total_gzipped < APP_PAGE_JS_BUDGET_BYTES, (
        f"{route} ships {total_gzipped} gzipped bytes of JS, "
        f"over the {APP_PAGE_JS_BUDGET_BYTES} byte app-page budget"
    )


@pytest.mark.parametrize(
    "route,html_file", [(route, html) for route, html in DASHBOARD_ROUTES.items() if html]
)
def test_static_dashboard_route_has_no_render_blocking_script(
    built: None, route: str, html_file: str
) -> None:
    html = (NEXT_DIR / "server" / "app" / html_file).read_text(encoding="utf-8")
    offenders = [
        tag
        for tag in EXTERNAL_SCRIPT_TAG.findall(html)
        if not any(substring in tag.lower() for substring in BLOCKING_EXEMPT_SUBSTRINGS)
    ]
    assert offenders == [], f"render-blocking script tag(s) found on {route}: {offenders}"


@pytest.mark.parametrize(
    "route,html_file", [(route, html) for route, html in DASHBOARD_ROUTES.items() if html]
)
def test_static_dashboard_route_images_have_explicit_dimensions(
    built: None, route: str, html_file: str
) -> None:
    html = (NEXT_DIR / "server" / "app" / html_file).read_text(encoding="utf-8")
    images = IMG_TAG.findall(html)
    missing = [
        img for img in images if "width=" not in img.lower() or "height=" not in img.lower()
    ]
    assert missing == [], f"img tag(s) missing explicit width/height on {route}: {missing}"


def test_dashboard_reviews_html_checks_are_refused_not_guessed(built: None) -> None:
    # /dashboard/reviews reads next/headers cookies() and fetches per-viewer data with
    # cache: "no-store", which makes it a real dynamic route with no prerendered HTML for this
    # build to inspect (confirmed: no .html file exists next to its compiled page.js). Its JS
    # budget is still checked above; the render-blocking-script and image-dimension checks that
    # need real HTML need a live request against a running control plane and Postgres session,
    # which this test suite does not stand up. Refusing this explicitly, not asserting a guess.
    static_html = NEXT_DIR / "server" / "app" / "dashboard" / "reviews.html"
    assert not static_html.exists(), (
        "dashboard/reviews now has prerendered HTML; add it to DASHBOARD_ROUTES above with a "
        "real html_file so its script/image checks run for real instead of being refused"
    )
    pytest.skip(
        "refusing to guess: dashboard/reviews is server-rendered per request behind a session "
        "cookie, so no build-time HTML exists to check for render-blocking scripts or image "
        "dimensions without standing up a live control plane and Postgres session"
    )
