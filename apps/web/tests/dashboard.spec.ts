import { expect, test, type APIRequestContext, type Page, type Response } from "@playwright/test";

const DASHBOARD_API = process.env.NEXT_PUBLIC_DASHBOARD_API_ORIGIN ?? "http://127.0.0.1:8742";
const TITLE_APPROVE = "Null check on widget.value";
const TITLE_REJECT = "Reject this queued finding";
const CONTEXT_SNIPPET = "widget.py:14 retrieved from memory-v1";
const FOREIGN_JOB = "job-foreign-99";
const SECRET_TITLE = /hmac|webhook secret|private key|github app/i;

test.describe.configure({ mode: "serial" });

async function requireLiveDashboard(request: APIRequestContext) {
  const response = await request.get(`${DASHBOARD_API}/dashboard/health`);
  expect(response.ok(), "Task 21 dashboard API must be running").toBeTruthy();
  expect(await response.json()).toEqual({ status: "ok" });
}

function waitForDashboard(page: Page, path: string, method = "GET") {
  return page.waitForResponse(
    (response: Response) =>
      response.url().startsWith(`${DASHBOARD_API}${path}`) && response.request().method() === method,
  );
}

test("session login shows the runner id the live account endpoint returned", async ({
  page,
  request,
}) => {
  await requireLiveDashboard(request);
  const session = waitForDashboard(page, "/dashboard/session");
  const account = waitForDashboard(page, "/dashboard/account");
  await page.goto("/dashboard");
  const sessionBody = (await (await session).json()) as { csrf_token: string };
  const accountBody = (await (await account).json()) as { runner_id: string };
  expect(sessionBody.csrf_token.length).toBeGreaterThan(8);
  await expect(page.getByTestId("dashboard-account")).toHaveText(accountBody.runner_id);
  await expect(page).not.toHaveTitle(SECRET_TITLE);
});

test("repository scope hides jobs the live jobs list omitted", async ({ page, request }) => {
  await requireLiveDashboard(request);
  const jobs = waitForDashboard(page, "/dashboard/jobs");
  await page.goto("/dashboard");
  const body = (await (await jobs).json()) as { items: Array<{ job_id: string }> };
  const ids = body.items.map((item) => item.job_id);
  expect(ids).not.toContain(FOREIGN_JOB);
  await expect(page.getByTestId("job-list")).not.toContainText(FOREIGN_JOB);
  for (const id of ids) {
    await expect(page.getByTestId("job-list")).toContainText(id);
  }
});

test("approval queue matches the live approvals list", async ({ page, request }) => {
  await requireLiveDashboard(request);
  const approvals = waitForDashboard(page, "/dashboard/approvals");
  await page.goto("/dashboard");
  const body = (await (await approvals).json()) as {
    items: Array<{ id: string; title: string }>;
  };
  expect(body.items.map((item) => item.title)).toEqual([TITLE_APPROVE, TITLE_REJECT]);
  const queue = page.getByTestId("approval-queue");
  await expect(queue.getByRole("listitem")).toHaveCount(body.items.length);
  for (const item of body.items) {
    await expect(queue).toContainText(item.title);
  }
});

test("finding detail, retrieved context, costs, and trace come from the live job routes", async ({
  page,
  request,
}) => {
  await requireLiveDashboard(request);
  const findings = waitForDashboard(page, "/dashboard/jobs/job-dash-1/findings");
  const events = waitForDashboard(page, "/dashboard/jobs/job-dash-1/events");
  const costs = waitForDashboard(page, "/dashboard/jobs/job-dash-1/costs");
  const trace = waitForDashboard(page, "/dashboard/jobs/job-dash-1/trace");
  await page.goto("/dashboard/jobs/job-dash-1");
  const findingBody = (await (await findings).json()) as {
    items: Array<{ id: string; title: string }>;
  };
  const eventBody = (await (await events).json()) as {
    items: Array<{ snippet?: string }>;
  };
  const costBody = (await (await costs).json()) as { cost_usd: number };
  const traceBody = (await (await trace).json()) as {
    segments: Array<{ origin: string; kind: string }>;
  };
  await expect(page.getByTestId("finding-detail")).toContainText(findingBody.items[0].title);
  expect(eventBody.items.some((item) => item.snippet === CONTEXT_SNIPPET)).toBeTruthy();
  await expect(page.getByTestId("retrieved-context")).toContainText(CONTEXT_SNIPPET);
  await expect(page.getByTestId("job-costs")).toContainText(String(costBody.cost_usd));
  const origins = new Set(traceBody.segments.map((item) => item.origin));
  expect(origins.has("hosted")).toBeTruthy();
  expect(origins.has("local")).toBeTruthy();
  for (const segment of traceBody.segments) {
    await expect(page.getByTestId("workflow-trace")).toContainText(segment.kind);
  }
});

test("eval comparison and connectors render the live API payloads", async ({ page, request }) => {
  await requireLiveDashboard(request);
  const evals = waitForDashboard(page, "/dashboard/evals");
  await page.goto("/dashboard/evals");
  const evalBody = (await (await evals).json()) as {
    items: Array<{ id: string; reason: string }>;
  };
  await expect(page.getByTestId("eval-comparison")).toContainText(evalBody.items[0].id);
  await expect(page.getByTestId("eval-comparison")).toContainText(evalBody.items[0].reason);

  const connectors = waitForDashboard(page, "/dashboard/connectors");
  await page.goto("/dashboard/connectors");
  const connectorBody = (await (await connectors).json()) as Record<string, string>;
  for (const [name, status] of Object.entries(connectorBody)) {
    await expect(page.getByTestId("connector-status")).toContainText(name);
    await expect(page.getByTestId("connector-status")).toContainText(status);
  }
});

test("loading is visible until the live approvals response arrives", async ({ page, request }) => {
  await requireLiveDashboard(request);
  await page.route("**/dashboard/approvals", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await route.continue();
  });
  const pending = page.goto("/dashboard");
  await expect(page.getByTestId("dashboard-loading")).toBeVisible();
  await pending;
  await expect(page.getByTestId("approval-queue")).toContainText(TITLE_APPROVE);
  await expect(page.getByTestId("dashboard-loading")).toHaveCount(0);
});

test("empty job findings show the empty state from a live empty list", async ({
  page,
  request,
}) => {
  await requireLiveDashboard(request);
  const findings = waitForDashboard(page, "/dashboard/jobs/job-empty-1/findings");
  await page.goto("/dashboard/jobs/job-empty-1");
  const body = (await (await findings).json()) as { items: unknown[] };
  expect(body.items).toEqual([]);
  await expect(page.getByTestId("dashboard-empty")).toBeVisible();
  await expect(page.getByTestId("finding-detail")).toHaveCount(0);
});

test("partial failure keeps live findings when costs fail", async ({ page, request }) => {
  await requireLiveDashboard(request);
  await page.route("**/dashboard/jobs/job-dash-1/costs", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "store_failed" }),
    }),
  );
  const findings = waitForDashboard(page, "/dashboard/jobs/job-dash-1/findings");
  await page.goto("/dashboard/jobs/job-dash-1");
  const body = (await (await findings).json()) as { items: Array<{ title: string }> };
  expect(body.items[0].title).toBe(TITLE_APPROVE);
  await expect(page.getByTestId("finding-detail")).toContainText(TITLE_APPROVE);
  await expect(page.getByTestId("dashboard-partial-failure")).toBeVisible();
});

test("stale refresh keeps the last live approvals list", async ({ page, request }) => {
  await requireLiveDashboard(request);
  const first = waitForDashboard(page, "/dashboard/approvals");
  await page.goto("/dashboard");
  const body = (await (await first).json()) as { items: Array<{ title: string }> };
  await expect(page.getByTestId("approval-queue")).toContainText(body.items[0].title);
  await page.route("**/dashboard/approvals", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "unavailable" }),
    }),
  );
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByTestId("dashboard-stale")).toBeVisible();
  await expect(page.getByTestId("approval-queue")).toContainText(body.items[0].title);
});

test("permission denied is shown when the live API returns 401", async ({ page, request }) => {
  await requireLiveDashboard(request);
  await page.route("**/dashboard/approvals", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: "unauthenticated" }),
    }),
  );
  await page.goto("/dashboard");
  await expect(page.getByTestId("dashboard-permission-denied")).toBeVisible();
  await expect(page).not.toHaveTitle(SECRET_TITLE);
});

test("desktop and mobile screenshots still show live approval titles", async ({
  page,
  request,
}) => {
  await requireLiveDashboard(request);
  const approvals = waitForDashboard(page, "/dashboard/approvals");
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/dashboard");
  const body = (await (await approvals).json()) as { items: Array<{ title: string }> };
  await expect(page.getByTestId("approval-queue")).toContainText(body.items[0].title);
  await page.screenshot({ path: "test-results/dashboard-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("approval-queue")).toContainText(body.items[0].title);
  await page.screenshot({ path: "test-results/dashboard-mobile.png", fullPage: true });
});

test("approving a finding posts the live decision and drops it from the queue", async ({
  page,
  request,
}) => {
  await requireLiveDashboard(request);
  await page.goto("/dashboard");
  await expect(page.getByTestId("approval-queue")).toContainText(TITLE_APPROVE);
  const posted = waitForDashboard(page, "/dashboard/approvals/f-dash-approve", "POST");
  await page.getByRole("button", { name: "Approve Null check on widget.value" }).click();
  const response = await posted;
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ status: "ok" });
  await expect(page.getByTestId("approval-queue")).not.toContainText(TITLE_APPROVE);
});

test("rejecting a finding posts rejected to the live API", async ({ page, request }) => {
  await requireLiveDashboard(request);
  await page.goto("/dashboard");
  await expect(page.getByTestId("approval-queue")).toContainText(TITLE_REJECT);
  const posted = waitForDashboard(page, "/dashboard/approvals/f-dash-reject", "POST");
  await page.getByRole("button", { name: "Reject Reject this queued finding" }).click();
  const response = await posted;
  expect(response.ok()).toBeTruthy();
  expect(await response.json()).toEqual({ status: "ok" });
  await expect(page.getByTestId("approval-queue")).not.toContainText(TITLE_REJECT);
});
