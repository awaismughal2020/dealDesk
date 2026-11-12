import { chromium, type FullConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { credentials, signIn, STATE_DIR, type Role } from "./helpers";

/** Sign in once per role through the real UI and save the cookies for the tests. */
export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  mkdirSync(STATE_DIR, { recursive: true });
  const browser = await chromium.launch();
  for (const role of ["admin", "estimator", "approver", "viewer"] as Role[]) {
    const context = await browser.newContext({ baseURL });
    const page = await context.newPage();
    await page.goto("/login");
    const { email, password } = credentials(role);
    await signIn(page, email, password);
    await page.waitForURL(`${baseURL}/`);
    await context.storageState({ path: `${STATE_DIR}/${role}.json` });
    await context.close();
  }
  await browser.close();
}
