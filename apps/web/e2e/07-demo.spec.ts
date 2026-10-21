import { expect, test } from "@playwright/test";
import {
  ADMIN_EMAIL, PASSWORD, apiGet, apiLogin, apiPost, uiLogin, uniqueName,
} from "./helpers";

// Note: this spec asserts UI states on a fresh project, not the full demo
// dataset. The full pipeline verification lives in scripts/verify-demo.ps1
// (requires a running API but no browser). This spec confirms the UI side:
// pages load, demo-relevant controls exist, and the readiness badge
// reflects the state the API reports.

test.describe("Demo flow - UI", () => {
  test("project page shows health panel and validation link", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const project = await apiPost(token, "/projects", {
      name: uniqueName("E2E Demo"),
      client: "Demo",
      description: "",
    });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto(`/projects/${project.id}`);
    await page.waitForLoadState("networkidle");

    // Health panel is rendered above the documents table
    await expect(page.getByText(/project health/i).first()).toBeVisible({ timeout: 10_000 });

    // The main action links are present
    await expect(page.getByRole("link", { name: /validate for issue/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^impact$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^dependencies$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^reports$/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^ask$/i })).toBeVisible();
  });

  test("reports page renders a readiness badge and download buttons", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const project = await apiPost(token, "/projects", {
      name: uniqueName("E2E Demo Reports"),
      client: "Demo",
      description: "",
    });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto(`/projects/${project.id}/reports`);
    await page.waitForLoadState("networkidle");

    await expect(page.getByText(/NOT_VALIDATED|READY|BLOCKED/i).first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("button", { name: /download json/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /download csv/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /download pdf/i })).toBeVisible();
  });

  test("language switcher is in the header and changes nav labels", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/dashboard");

    // Header contains the switcher
    const switcher = page.locator('select[aria-label="Language"]');
    await expect(switcher).toBeVisible();

    // Default is English
    await expect(page.locator("header")).toContainText("Dashboard");

    // Switch to Japanese and assert the nav label changed
    await switcher.selectOption("ja");
    await page.waitForTimeout(200);
    await expect(page.locator("header")).toContainText("ダッシュボード");

    // Switch back so later tests see English
    await switcher.selectOption("en");
    await page.waitForTimeout(200);
    await expect(page.locator("header")).toContainText("Dashboard");
  });

  test("notifications page renders with unread filter", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/notifications");
    await page.waitForLoadState("networkidle");

    await expect(page.getByRole("heading", { name: /notifications/i }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /mark all read/i })).toBeVisible();
  });
});