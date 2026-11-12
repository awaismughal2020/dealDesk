import AxeBuilder from "@axe-core/playwright";
import {
  expect,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from "@playwright/test";

export type Role = "admin" | "estimator" | "approver" | "viewer";
export const STATE_DIR = "test-results/.auth";

export function credentials(role: Role): { email: string; password: string } {
  const prefix = `DEMO_${role.toUpperCase()}`;
  const email = process.env[`${prefix}_EMAIL`];
  const password = process.env[`${prefix}_PASSWORD`];
  if (!email || !password) throw new Error(`${prefix}_EMAIL/_PASSWORD missing; run make init`);
  return { email, password };
}

export async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function asRole(
  browser: Browser,
  role: Role,
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ storageState: `${STATE_DIR}/${role}.json` });
  return { context, page: await context.newPage() };
}

/** Same-origin API call from inside a signed-in context, with the CSRF header the UI would send. */
export async function apiCall(
  request: APIRequestContext,
  method: "GET" | "POST" | "PATCH",
  path: string,
  options: { data?: unknown; multipart?: Record<string, string> } = {},
) {
  const csrf = await request.get("/v1/auth/csrf");
  const { csrf_token: token } = (await csrf.json()) as { csrf_token: string };
  return request.fetch(path, {
    method,
    headers: { "X-CSRF-Token": token, Origin: process.env.BASE_URL ?? "http://localhost:3000" },
    ...(options.data !== undefined ? { data: options.data } : {}),
    ...(options.multipart ? { multipart: options.multipart } : {}),
  });
}

export type SampleId = "clean_brief" | "ambiguous_brief" | "injection_brief";

export async function startSampleRun(
  page: Page,
  sample: SampleId = "clean_brief",
): Promise<string> {
  await page.goto("/runs/new");
  await page.getByRole("button", { name: `Use ${sample.replace(/_/g, " ")}` }).click();
  await page.waitForURL(/\/runs\/[0-9a-f-]{36}$/);
  return page.url().split("/").at(-1) ?? "";
}

export async function waitForStatus(page: Page, status: string): Promise<void> {
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.locator("main").getByText(status, { exact: true }).first()).toBeVisible({
    timeout: 30_000,
  });
}

export async function expectAccessible(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const summary = results.violations.map(
    (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`,
  );
  expect(summary, "axe violations").toEqual([]);
}
