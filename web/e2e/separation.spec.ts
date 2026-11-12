import { expect, test } from "@playwright/test";
import { apiCall, asRole, signIn, startSampleRun, waitForStatus } from "./helpers";

test("an approver can never approve a run they created", async ({ browser }) => {
  const admin = await asRole(browser, "admin");
  const email = `e2e-sod-${Date.now()}@dealdesk.example`;
  const password = `e2e-${crypto.randomUUID()}`;
  const created = await apiCall(admin.page.request, "POST", "/v1/admin/users", {
    data: { email, display_name: "E2E Estimator (SAMPLE)", role: "estimator", password },
  });
  expect(created.status()).toBe(201);
  const { id } = (await created.json()) as { id: string };

  const creator = await browser.newContext();
  const page = await creator.newPage();
  await page.goto("/login");
  await signIn(page, email, password);
  await page.waitForURL(/\/$/);
  const runId = await startSampleRun(page);
  await waitForStatus(page, "Awaiting approval");

  // The admin promotes the creator to approver (their sessions are revoked by the server).
  expect(
    (
      await apiCall(admin.page.request, "PATCH", `/v1/admin/users/${id}`, {
        data: { role: "approver" },
      })
    ).status(),
  ).toBe(200);
  await admin.context.close();

  await creator.clearCookies();
  await page.goto(`/runs/${runId}`);
  await signIn(page, email, password);
  await expect(page.getByText(/separation of duties/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve…" })).toHaveCount(0);
  const direct = await apiCall(page.request, "POST", `/v1/runs/${runId}/approve`, {
    data: { comment: "self" },
  });
  expect(direct.status()).toBe(403);
  expect(((await direct.json()) as { title: string }).title).toBe("Separation of duties");
  await creator.close();
});
