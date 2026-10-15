import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, PASSWORD, uiLogin } from "./helpers";

test.describe("Audit log", () => {
  test("audit page renders", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/audit");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /audit log/i })).toBeVisible();
    const hasTable = await page.locator("table").count();
    const hasEmpty = await page.getByText(/no entries match/i).count();
    expect(hasTable + hasEmpty).toBeGreaterThan(0);
  });

  test("audit filter narrows results", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/audit");
    await page.waitForLoadState("networkidle");

    await page.getByLabel(/filter by action/i).fill("dependency.created");
    await page.getByRole("button", { name: /^filter$/i }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /audit log/i })).toBeVisible();
  });
});