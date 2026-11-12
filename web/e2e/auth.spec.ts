import { expect, test } from "@playwright/test";
import { credentials, signIn } from "./helpers";

test("signing in, a generic error for bad credentials, and signing out", async ({ page }) => {
  await page.goto("/impact");
  await expect(page).toHaveURL(/\/login\?next=%2Fimpact$/);

  const { email, password } = credentials("viewer");
  await signIn(page, email, "definitely-not-the-password");
  await expect(page.getByText(/Incorrect email or password/)).toBeVisible();

  await signIn(page, email, password);
  await expect(page).toHaveURL(/\/impact$/); // back where they were going
  await expect(page.getByRole("heading", { name: "Impact" })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login\?next=%2F$/);
});

test("an expired session returns the user to the same page", async ({ page, context }) => {
  const { email, password } = credentials("estimator");
  await page.goto("/login?next=%2Fruns%2Fnew");
  await signIn(page, email, password);
  await expect(page).toHaveURL(/\/runs\/new$/);

  // The 15-minute access cookie expires; the refresh cookie silently renews the session.
  await context.clearCookies({ name: "dd_access" });
  await page.goto("/impact");
  await expect(page).toHaveURL(/\/impact$/);
  await expect(page.getByRole("heading", { name: "Impact" })).toBeVisible();

  // With no session at all, the user signs in again and lands on the page they asked for.
  await context.clearCookies();
  await page.goto("/runs/new");
  await expect(page).toHaveURL(/\/login\?next=%2Fruns%2Fnew$/);
  await signIn(page, email, password);
  await expect(page).toHaveURL(/\/runs\/new$/);
});
