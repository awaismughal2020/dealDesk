import { codeChallenge, randomToken, safeNext } from "./pkce";

test("RFC 7636 appendix B example", async () => {
  expect(await codeChallenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")).toBe(
    "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
  );
});

test("random tokens are url-safe and unique", () => {
  const a = randomToken();
  expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/);
  expect(randomToken()).not.toBe(a);
});

test.each([
  ["/runs/1", "/runs/1"],
  ["https://evil.example", "/"],
  ["//evil.example", "/"],
  ["/\\evil.example", "/"],
  [null, "/"],
])("safeNext(%s) prevents open redirects", (input, expected) => {
  expect(safeNext(input)).toBe(expected);
});
