import { createAuthFetch, loginUrl, problemMessage, readCookie } from "./client";

function respond(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("authFetch", () => {
  beforeEach(() => {
    document.cookie = "dd_csrf=csrf-123; path=/";
  });

  test("adds the CSRF header to writes only", async () => {
    const seen: Request[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      seen.push(input as Request);
      return respond(200);
    });
    const authFetch = createAuthFetch(fetcher as typeof fetch, vi.fn());
    await authFetch("http://localhost/v1/runs");
    await authFetch("http://localhost/v1/runs", { method: "POST", body: "{}" });
    expect(seen[0]?.headers.get("X-CSRF-Token")).toBeNull();
    expect(seen[1]?.headers.get("X-CSRF-Token")).toBe("csrf-123");
  });

  test("refreshes once on 401 and retries the original request", async () => {
    const statuses = [401, 200, 200];
    const urls: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      urls.push(new URL((input as Request).url).pathname);
      return respond(statuses.shift() ?? 500);
    });
    const expired = vi.fn();
    const response = await createAuthFetch(
      fetcher as typeof fetch,
      expired,
    )("http://localhost/v1/runs");
    expect(response.status).toBe(200);
    expect(urls).toEqual(["/v1/runs", "/v1/auth/refresh", "/v1/runs"]);
    expect(expired).not.toHaveBeenCalled();
  });

  test("sends the user to sign-in, remembering the page, when refresh fails", async () => {
    window.history.pushState({}, "", "/runs/abc?tab=quote");
    const fetcher = vi.fn(async () => respond(401));
    const expired = vi.fn();
    const response = await createAuthFetch(
      fetcher as typeof fetch,
      expired,
    )("http://localhost/v1/runs");
    expect(response.status).toBe(401);
    expect(expired).toHaveBeenCalledWith("/login?next=%2Fruns%2Fabc%3Ftab%3Dquote");
  });

  test("never retries the sign-in endpoints", async () => {
    const fetcher = vi.fn(async () => respond(401));
    await createAuthFetch(fetcher as typeof fetch, vi.fn())("http://localhost/v1/auth/login", {
      method: "POST",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  test("fetches a CSRF token when the cookie is missing", async () => {
    document.cookie = "dd_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
    const fetcher = vi.fn(async (input: RequestInfo | URL) =>
      String(input).includes("/v1/auth/csrf")
        ? respond(200, { csrf_token: "fresh" })
        : respond(200),
    );
    await createAuthFetch(fetcher as typeof fetch, vi.fn())(
      "http://localhost/v1/impact/calculate",
      { method: "POST" },
    );
    const last = fetcher.mock.calls.at(-1)?.[0] as Request;
    expect(last.headers.get("X-CSRF-Token")).toBe("fresh");
  });
});

test("helpers", () => {
  expect(readCookie("b", "a=1; b=two%20words")).toBe("two words");
  expect(readCookie("c", "a=1")).toBeNull();
  expect(loginUrl("/x?y=1")).toBe("/login?next=%2Fx%3Fy%3D1");
  expect(problemMessage({ detail: "Nope" })).toBe("Nope");
  expect(problemMessage({ title: "Conflict" })).toBe("Conflict");
  expect(problemMessage(null, "fallback")).toBe("fallback");
});
