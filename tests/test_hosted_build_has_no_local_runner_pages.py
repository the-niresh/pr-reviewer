"""Task 33.C5: local runner pages are served by the runner, never by the hosted site.

Approvals, Evals, Connectors and the per-job trace view all called a hardcoded loopback
address (the local runner's own dashboard API on 127.0.0.1:8742), which can never resolve
from a hosted https origin - that is why they hung on "Loading" forever. They move off
apps/web entirely; /dashboard/reviews stays, because it is hosted and real: it reads the
signed-in viewer's session and calls the hosted control plane, never a loopback address.

Task 33.C3 later reintroduced apps/web/src/app/dashboard/page.tsx on purpose, as a real
overview of the viewer's own reviews. It is not the old Approvals page come back: it reads
GET /api/reviews through lib/reviews.ts's fetchReviews (the same hosted, server-side,
credentialed-cookie call dashboard/reviews/page.tsx already makes), never a browser-side
loopback fetch. It is therefore no longer in REMOVED_PAGES below, and is covered instead by
test_dashboard_overview_page_is_kept, the same way dashboard/reviews/page.tsx is covered by
test_dashboard_reviews_page_is_kept.

The loopback-address guard below is a standing one, not a one-time check: it walks every
page.tsx under apps/web/src/app and fails on any future page that hardcodes a loopback
address, with two named exceptions:

- apps/web/src/app/onboarding/page.tsx already does this today (it talks to a different
  local pairing daemon on port 8741) and is a separate, still-open cleanup outside this
  task's file list.
- apps/web/src/app/dashboard/reviews/page.tsx's loopback default is a control-plane
  origin fetched server-side, inside the Next.js server's own request handler, not a
  browser-side call to the viewer's machine. A hosted deployment sets
  NEXT_PUBLIC_CONTROL_PLANE_ORIGIN to the real origin; the loopback default is only a
  local-dev convenience for running the web app against a co-located control plane. That
  is a different failure mode from the four pages removed here, whose fetches ran in the
  browser with credentials: "include" against the *viewer's own machine*, which a hosted
  https origin can never reach no matter what env var is set.

Naming both explicitly means a regression on any OTHER page still fails loudly instead of
being masked by a blanket allowance.
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"
WEB_APP = WEB_SRC / "app"
DASHBOARD_DIR = WEB_APP / "dashboard"

LOOPBACK = re.compile(r"127\.0\.0\.1|\blocalhost\b", re.IGNORECASE)

REMOVED_PAGES = (
    DASHBOARD_DIR / "evals" / "page.tsx",
    DASHBOARD_DIR / "connectors" / "page.tsx",
    DASHBOARD_DIR / "jobs" / "[jobId]" / "page.tsx",
)

# See the module docstring for why each of these is not the bug this guard exists to catch.
KNOWN_PRE_EXISTING_LOOPBACK_PAGES = frozenset(
    {"onboarding/page.tsx", "dashboard/reviews/page.tsx"}
)


def _pages() -> list[Path]:
    return sorted(WEB_APP.rglob("page.tsx"))


def test_local_runner_pages_are_removed_from_the_hosted_build() -> None:
    present = [str(path.relative_to(WEB_SRC)) for path in REMOVED_PAGES if path.exists()]
    assert present == [], f"local runner page(s) still shipped from the hosted site: {present}"


def test_dashboard_reviews_page_is_kept() -> None:
    assert (DASHBOARD_DIR / "reviews" / "page.tsx").is_file(), (
        "dashboard/reviews is hosted and real; it must stay"
    )


def test_dashboard_overview_page_is_kept() -> None:
    assert (DASHBOARD_DIR / "page.tsx").is_file(), (
        "dashboard is hosted and real (task 33.C3's overview); it must stay"
    )


def test_the_shared_local_runner_api_client_is_removed() -> None:
    dashboard_api = WEB_SRC / "lib" / "dashboardApi.ts"
    assert not dashboard_api.exists(), (
        f"{dashboard_api} still exists; it is the loopback-only client the removed pages used"
    )


def test_no_remaining_file_imports_the_removed_local_runner_api_client() -> None:
    offenders = []
    for path in list(WEB_SRC.rglob("*.ts")) + list(WEB_SRC.rglob("*.tsx")):
        if "dashboardApi" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(WEB_SRC)))
    assert offenders == [], f"file(s) still reference the removed dashboardApi client: {offenders}"


def test_dashboard_shell_loses_the_three_removed_nav_entries() -> None:
    shell = (WEB_SRC / "components" / "DashboardShell.tsx").read_text(encoding="utf-8")
    for removed_href in ('href="/dashboard"', '"/dashboard/evals"', '"/dashboard/connectors"'):
        assert removed_href not in shell, f"DashboardShell still links to {removed_href}"


def test_no_page_under_apps_web_calls_a_loopback_address_except_the_known_ones() -> None:
    offenders = []
    for page in _pages():
        rel = str(page.relative_to(WEB_APP))
        if rel in KNOWN_PRE_EXISTING_LOOPBACK_PAGES:
            continue
        if LOOPBACK.search(page.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert offenders == [], f"page(s) call a loopback address: {offenders}"


def test_the_loopback_pattern_actually_catches_a_violation() -> None:
    assert LOOPBACK.search('fetch("http://127.0.0.1:8742/dashboard/jobs")')
    assert not LOOPBACK.search('fetch("https://reviewer.niresh.tech/api/reviews")')
