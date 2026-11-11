import { expect, test } from "@playwright/test";

test("pages carry a nonce CSP and security headers; the API carries its own", async ({
  page,
  request,
}) => {
  const response = await page.goto("/login");
  const headers = response?.headers() ?? {};
  const csp = headers["content-security-policy"] ?? "";
  const scriptSrc = csp.split(";").find((d) => d.trim().startsWith("script-src")) ?? "";
  expect(scriptSrc).toMatch(/'nonce-[A-Za-z0-9+/=]+'/);
  expect(scriptSrc).not.toContain("unsafe-inline");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["referrer-policy"]).toBeTruthy();

  const api = await request.get("/v1/auth/me");
  expect(api.status()).toBe(401);
  expect(api.headers()["content-type"]).toBe("application/problem+json");
  expect(api.headers()["x-request-id"]).toBeTruthy();
});

test("cookies are HttpOnly and tokens are not readable by page scripts", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.DEMO_VIEWER_EMAIL ?? "");
  await page.getByLabel("Password").fill(process.env.DEMO_VIEWER_PASSWORD ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/$/);
  const visible = await page.evaluate(() => document.cookie);
  expect(visible).not.toContain("dd_access");
  expect(visible).not.toContain("dd_refresh");
  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "dd_access");
  expect(access?.httpOnly).toBe(true);
  expect(access?.sameSite).toBe("Lax");
  const storage = await page.evaluate(
    () => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }),
  );
  expect(storage).not.toMatch(/eyJ/); // no JWTs in web storage
});
