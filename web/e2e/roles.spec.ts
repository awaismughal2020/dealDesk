import { expect, test } from "@playwright/test";
import { asRole, type Role } from "./helpers";

const NAV: Record<Role, string[]> = {
  viewer: ["Dashboard", "Impact"],
  estimator: ["Dashboard", "New run", "Impact"],
  approver: ["Dashboard", "Impact"],
  admin: ["Dashboard", "New run", "Impact", "Admin"],
};

for (const role of Object.keys(NAV) as Role[]) {
  test(`navigation shows only what a ${role} can use`, async ({ browser }) => {
    const { context, page } = await asRole(browser, role);
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link")).toHaveText(NAV[role]);
    await context.close();
  });
}

test("hiding is only usability: the server refuses what the role cannot do", async ({
  browser,
}) => {
  const { context, page } = await asRole(browser, "viewer");
  await page.goto("/admin");
  await expect(page.getByText("Admins only")).toBeVisible();
  await page.goto("/runs/new");
  await expect(page.getByText("Not available for your role")).toBeVisible();
  const forbidden = await page.request.get("/v1/admin/users");
  expect(forbidden.status()).toBe(403);
  await context.close();
});
