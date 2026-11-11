import { expect, test } from "@playwright/test";
import { asRole, startSampleRun, waitForStatus } from "./helpers";

test("a SAMPLE brief goes from upload to approval, records and a final proposal", async ({
  browser,
}) => {
  const estimator = await asRole(browser, "estimator");
  const runId = await startSampleRun(estimator.page);
  await waitForStatus(estimator.page, "Awaiting approval");
  const quote = estimator.page.getByRole("region", { name: "Quote (computed by code)" });
  await expect(quote.getByText("£137,830.00").first()).toBeVisible();
  await expect(quote.getByText("33.76%")).toBeVisible();
  await expect(estimator.page.getByText("To reach the target margin")).toBeVisible();
  await expect(
    estimator.page.getByRole("table", { name: "Hours per person per week" }),
  ).toBeVisible();
  await expect(estimator.page.getByText("DRAFT, requires approval")).toBeVisible();
  await expect(
    estimator.page.getByText("Only approvers can approve or reject runs."),
  ).toBeVisible();
  await estimator.context.close();

  const approver = await asRole(browser, "approver");
  await approver.page.goto(`/runs/${runId}`);
  await approver.page.getByRole("button", { name: "Approve…" }).click();
  const dialog = approver.page.getByRole("dialog", { name: "Approve this quote" });
  await expect(dialog.getByText("£137,830.00")).toBeVisible();
  await dialog.getByLabel(/Comment/).fill("Within policy for a SAMPLE demo.");
  await dialog.getByRole("button", { name: "Confirm approval" }).click();
  await waitForStatus(approver.page, "Approved");
  await expect(
    approver.page.getByText(/Pipeline record “Tenant self-service portal”/),
  ).toBeVisible();
  await expect(approver.page.getByText("Within policy for a SAMPLE demo.")).toBeVisible();

  const download = approver.page.waitForEvent("download");
  await approver.page.getByRole("link", { name: "Download .docx" }).click();
  expect((await download).suggestedFilename()).toMatch(/FINAL\.docx$/);
  await approver.context.close();
});

test("rejecting needs a comment and sends the draft back for revision", async ({ browser }) => {
  const estimator = await asRole(browser, "estimator");
  const runId = await startSampleRun(estimator.page);
  await waitForStatus(estimator.page, "Awaiting approval");
  await estimator.context.close();

  const approver = await asRole(browser, "approver");
  await approver.page.goto(`/runs/${runId}`);
  await approver.page.getByRole("button", { name: "Reject…" }).click();
  const dialog = approver.page.getByRole("dialog", { name: "Reject this draft" });
  await dialog.getByRole("button", { name: "Confirm rejection" }).click();
  await expect(dialog.getByText(/Say why you are rejecting/)).toBeVisible();
  await dialog.getByLabel(/Comment/).fill("Add an accessibility audit to the scope.");
  await dialog.getByRole("button", { name: "Confirm rejection" }).click();
  await waitForStatus(approver.page, "Awaiting approval");
  await expect(
    approver.page.getByText(/addressing reviewer feedback|address reviewer feedback/),
  ).toBeVisible();
  await expect(approver.page.getByText("“Add an accessibility audit to the scope.”")).toBeVisible();
  await approver.context.close();
});

test("the injection brief is flagged and quarantined", async ({ browser }) => {
  const estimator = await asRole(browser, "estimator");
  await startSampleRun(estimator.page, "injection_brief");
  await waitForStatus(estimator.page, "Awaiting approval");
  await expect(estimator.page.getByText("Possible prompt injection").first()).toBeVisible();
  await expect(estimator.page.getByText(/Quarantined as possible prompt injection/)).toBeVisible();
  await expect(estimator.page.getByText("£137,830.00").first()).toBeVisible(); // unchanged price
  await estimator.context.close();
});
