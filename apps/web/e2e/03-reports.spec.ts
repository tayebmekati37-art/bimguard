import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, PASSWORD, apiLogin, apiPost, uniqueName, uiLogin } from "./helpers";

test.describe("Reports page", () => {
  test("reports page renders summary and download buttons", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const project = await apiPost(token, "/projects", {
      name: uniqueName("E2E Reports"), client: "E2E", description: "",
    });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto(`/projects/${project.id}/reports`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /reports/i }).first()).toBeVisible();
    await expect(page.getByText(/NOT_VALIDATED|READY|BLOCKED/).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: /download json/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /download csv/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /download pdf/i })).toBeVisible();
  });

  test("download JSON produces a .json file", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const project = await apiPost(token, "/projects", {
      name: uniqueName("E2E Download"), client: "E2E", description: "",
    });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto(`/projects/${project.id}/reports`);
    await page.waitForLoadState("networkidle");

    const [ download ] = await Promise.all([
      page.waitForEvent("download", { timeout: 15_000 }),
      page.getByRole("button", { name: /download json/i }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });
});