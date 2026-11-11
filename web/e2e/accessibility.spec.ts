import { expect, test } from "@playwright/test";
import { asRole, expectAccessible, startSampleRun, waitForStatus } from "./helpers";

test("sign-in page has no axe violations", async ({ page }) => {
  await page.goto("/login");
  await expectAccessible(page);
});

test("every signed-in page has no axe violations", async ({ browser }) => {
  const { context, page } = await asRole(browser, "admin");
  for (const path of ["/", "/runs/new", "/impact", "/admin"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expectAccessible(page);
  }
  await startSampleRun(page);
  await waitForStatus(page, "Awaiting approval");
  await expectAccessible(page);
  await context.close();
});

test("approval dialog is accessible and keyboard operable", async ({ browser }) => {
  const estimator = await asRole(browser, "estimator");
  const runId = await startSampleRun(estimator.page);
  await waitForStatus(estimator.page, "Awaiting approval");
  await estimator.context.close();
  const { context, page } = await asRole(browser, "approver");
  await page.goto(`/runs/${runId}`);
  await page.getByRole("button", { name: "Approve…" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await context.close();
});
