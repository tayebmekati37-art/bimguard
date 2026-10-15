import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, PASSWORD, uiLogin } from "./helpers";

test.describe("Notifications", () => {
  test("notifications page renders", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/notifications");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /notifications/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /mark all read/i })).toBeVisible();
  });

  test("notification bell is in the header", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await expect(page.locator("header")).toContainText(/notifications/i);
  });
});