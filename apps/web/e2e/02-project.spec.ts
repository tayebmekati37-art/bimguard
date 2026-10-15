import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, PASSWORD, apiLogin, apiPost, uniqueName, uiLogin } from "./helpers";

test.describe("Project flow", () => {
  test("dashboard loads with the app header", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.locator("header")).toContainText("BIMGuard");
  });

  test("projects list is reachable", async ({ page }) => {
    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/projects");
    await expect(page).toHaveURL(/\/projects/);
  });

  test("project created via API appears in the projects list", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const name = uniqueName("E2E Project");
    await apiPost(token, "/projects", { name, client: "E2E Client", description: "" });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto("/projects");
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(name, { exact: false }).first()).toBeVisible({ timeout: 15_000 });
  });

  test("project detail page opens", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const name = uniqueName("E2E Detail");
    const project = await apiPost(token, "/projects", {
      name, client: "E2E", description: "",
    });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto(`/projects/${project.id}`);
    await page.waitForLoadState("networkidle");
    await expect(page.getByText(name, { exact: false }).first()).toBeVisible({ timeout: 15_000 });
  });
});