import { expect, test } from "@playwright/test";

test("onboarding covers pairing, repositories, model key, doctor, and runtime mode", async ({
  page,
}) => {
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: /pair/i })).toBeVisible();
  await expect(page.getByText(/repositor/i)).toBeVisible();
  await expect(page.getByLabel(/api key|model key/i)).toBeVisible();
  await expect(page.getByText(/doctor|docker/i)).toBeVisible();
  await expect(page.getByText(/full|analysis-only/i)).toBeVisible();
});

test("model key is not echoed after submit", async ({ page }) => {
  const key = "sk-playwright-must-not-echo";
  await page.goto("/onboarding");
  await page.getByLabel(/api key|model key/i).fill(key);
  await page.getByRole("button", { name: /save|continue|submit/i }).click();
  await expect(page.locator("body")).not.toContainText(key);
});

test("analysis-only disabled features are shown before confirmation", async ({
  page,
}) => {
  await page.goto("/onboarding");
  await expect(page.getByText(/repository retrieval/i)).toBeVisible();
  await expect(page.getByText(/verification/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /confirm|continue/i })).toBeVisible();
});
