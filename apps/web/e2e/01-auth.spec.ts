import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, PASSWORD, uiLogin } from "./helpers";

test.describe("Authentication", () => {
  test("login page renders a password input", async ({ page }) => {
    await page.goto("/login");
    await expect(page.locator('input[type="password"]').first()).toBeVisible();
  });

  test("wrong password does not reach the dashboard", async ({ page }) => {
    await page.goto("/login");
    await page
      .locator('input[type="email"], input[name="email"], input[name="username"]')
      .first()
      .fill(ADMIN_EMAIL);
    await page.locator('input[type="password"]').first().fill("wrong-password-xyz");
    await page
      .getByRole("button")
      .filter({ hasText: /sign in|log in|login/i })
      .first()
      .click();
    await page.waitForTimeout(1500);
    expect(page.url()).toMatch(/\/login/);
  });

  test("correct login reaches the dashboard", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await expect(page).toHaveURL(/\/dashboard/);
  });
});