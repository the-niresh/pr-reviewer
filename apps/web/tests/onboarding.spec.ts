import { expect, test } from "@playwright/test";

const LOCAL_API = process.env.NEXT_PUBLIC_LOCAL_API_ORIGIN ?? "http://127.0.0.1:8741";

test("onboarding covers pairing, repositories, model key, doctor, and runtime mode", async ({
  page,
}) => {
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: /pair/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /repositor/i })).toBeVisible();
  await expect(page.getByLabel(/api key|model key/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /doctor/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /runtime mode/i })).toBeVisible();
});

test("disabled features are the list GET /onboarding/mode returned", async ({ page }) => {
  const modeResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/onboarding/mode") && response.request().method() === "GET",
  );
  await page.goto("/onboarding");
  const body = (await (await modeResponse).json()) as { disabled_features: string[] };
  const items = page.getByTestId("disabled-features").getByRole("listitem");
  await expect(items).toHaveCount(body.disabled_features.length);
  for (const feature of body.disabled_features) {
    await expect(page.getByTestId("disabled-features")).toContainText(feature);
  }
});

test("model key POST success does not echo the key", async ({ page }) => {
  const key = "sk-playwright-must-not-echo";
  await page.goto("/onboarding");
  await expect(page.getByRole("button", { name: /save|continue|submit/i })).toBeEnabled();
  await page.getByLabel(/api key|model key/i).fill(key);
  const posted = page.waitForRequest(
    (request) => request.url().includes("/onboarding/model-key") && request.method() === "POST",
  );
  await page.getByRole("button", { name: /save|continue|submit/i }).click();
  const request = await posted;
  expect(request.url()).toContain(`${LOCAL_API}/onboarding/model-key`);
  await expect(page.getByText(/api key saved/i)).toBeVisible();
  await expect(page.locator("body")).not.toContainText(key);
});

test("a failed model-key save does not show the success message", async ({ page }) => {
  await page.route("**/onboarding/model-key", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "store_failed" }),
    }),
  );
  await page.goto("/onboarding");
  await expect(page.getByRole("button", { name: /save|continue|submit/i })).toBeEnabled();
  await page.getByLabel(/api key|model key/i).fill("sk-playwright-failed-save");
  const posted = page.waitForRequest(
    (request) => request.url().includes("/onboarding/model-key") && request.method() === "POST",
  );
  await page.getByRole("button", { name: /save|continue|submit/i }).click();
  await posted;
  await expect(page.getByText(/api key saved/i)).not.toBeVisible();
});
