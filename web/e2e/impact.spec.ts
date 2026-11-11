import { expect, test } from "@playwright/test";
import { asRole } from "./helpers";

test("the impact calculator recalculates from the user's assumptions", async ({ browser }) => {
  const { context, page } = await asRole(browser, "viewer");
  await page.goto("/impact");
  await expect(page.getByText("Assumptions, not measurements.")).toBeVisible();
  const annual = page.locator("dd").nth(1);
  const before = await annual.textContent();
  await page.getByLabel("Bids per year").fill("120");
  await expect(annual).not.toHaveText(before ?? "");
  await expect(page.getByText("Hours per bid by step, by hand versus assisted")).toBeVisible();
  await page.getByLabel("Share of saved time that becomes cash (0 to 1)").fill("1.5");
  await expect(page.getByText("Enter a share between 0 and 1")).toBeVisible();
  await context.close();
});
