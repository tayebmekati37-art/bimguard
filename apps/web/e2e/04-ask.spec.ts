import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, PASSWORD, apiLogin, apiPost, uniqueName, uiLogin } from "./helpers";

test.describe("Ask page", () => {
  test("ask page returns a template answer", async ({ page }) => {
    const token = await apiLogin(ADMIN_EMAIL, PASSWORD);
    const project = await apiPost(token, "/projects", {
      name: uniqueName("E2E Ask"), client: "E2E", description: "",
    });

    await uiLogin(page, ADMIN_EMAIL, PASSWORD);
    await page.goto(`/projects/${project.id}/ask`);
    await page.waitForLoadState("networkidle");

    await expect(
      page.getByRole("heading", { name: /ask about this project/i })
    ).toBeVisible();

    await page.locator("textarea").first().fill("status of A-101");
    await page.getByRole("button", { name: /^ask$/i }).click();

    await expect(page.getByText(/template/i).first()).toBeVisible({ timeout: 15_000 });
  });
});