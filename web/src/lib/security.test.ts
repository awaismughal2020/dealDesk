import { contentSecurityPolicy, isPublicPath, securityHeaders } from "./security-headers";
import { checkBriefFile } from "./upload";

test("CSP uses a nonce for scripts and never allows inline script", () => {
  const csp = contentSecurityPolicy("abc", { dev: false, local: false });
  const script = csp.split("; ").find((d) => d.startsWith("script-src")) ?? "";
  expect(script).toContain("'nonce-abc'");
  expect(script).not.toContain("unsafe-inline");
  expect(script).not.toContain("unsafe-eval");
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("upgrade-insecure-requests");
  expect(contentSecurityPolicy("n", { dev: true, local: true })).not.toContain(
    "upgrade-insecure-requests",
  );
});

test("HSTS only outside local", () => {
  expect(securityHeaders(true)["Strict-Transport-Security"]).toBeUndefined();
  expect(securityHeaders(false)["Strict-Transport-Security"]).toMatch(/^max-age=/);
  expect(securityHeaders(true)["X-Content-Type-Options"]).toBe("nosniff");
});

test("public paths", () => {
  expect(isPublicPath("/login")).toBe(true);
  expect(isPublicPath("/auth/oidc/callback")).toBe(true);
  expect(isPublicPath("/loginx")).toBe(false);
  expect(isPublicPath("/runs/1")).toBe(false);
});

test("client-side upload checks (the server re-checks by content)", () => {
  const file = (name: string, size: number) => new File([new Uint8Array(size)], name);
  expect(checkBriefFile(file("brief.pdf", 10))).toBeNull();
  expect(checkBriefFile(file("brief.TXT", 10))).toBeNull();
  expect(checkBriefFile(file("brief.docx", 10))).toMatch(/PDF or a plain-text/);
  expect(checkBriefFile(file("empty.txt", 0))).toMatch(/empty/);
  expect(checkBriefFile(file("big.pdf", 10 * 1024 * 1024 + 1))).toMatch(/10 MB/);
});
