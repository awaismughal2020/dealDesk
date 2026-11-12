import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const CSRF_COOKIE = "dd_csrf";
export const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const NO_RETRY_PATHS = ["/v1/auth/login", "/v1/auth/refresh", "/v1/auth/csrf"];

/** Read a cookie the server deliberately left readable (only the CSRF token is). */
export function readCookie(name: string, cookieString: string = document.cookie): string | null {
  for (const part of cookieString.split(";")) {
    const [key, ...rest] = part.trim().split("=");
    if (key === name) return decodeURIComponent(rest.join("="));
  }
  return null;
}

/** Ensure a CSRF token exists (fetching one if needed) and return it. */
export async function csrfToken(fetcher: typeof fetch = fetch): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  const response = await fetcher(absolute("/v1/auth/csrf"), { credentials: "same-origin" });
  const body = (await response.json()) as { csrf_token: string };
  return body.csrf_token;
}

/** Resolve a same-origin path against the page (needed outside real browsers, e.g. tests). */
function absolute(input: RequestInfo | URL): RequestInfo | URL {
  return typeof input === "string" && input.startsWith("/")
    ? new URL(input, window.location.origin)
    : input;
}

/** Where to send someone whose session cannot be refreshed. */
export function loginUrl(current: string): string {
  return `/login?next=${encodeURIComponent(current)}`;
}

/**
 * Same-origin fetch for the API: adds the CSRF header to writes and, on a 401, tries one silent
 * refresh before retrying. If that fails the user is sent to sign-in and returned here afterwards.
 * Tokens stay in HttpOnly cookies; nothing here can read them.
 */
export function createAuthFetch(
  fetcher: typeof fetch = (input, init) => fetch(input, init),
  onSessionExpired: (url: string) => void = (url) => window.location.assign(url),
): typeof fetch {
  async function send(request: Request): Promise<Response> {
    const headers = new Headers(request.headers);
    if (!SAFE_METHODS.has(request.method)) headers.set(CSRF_HEADER, await csrfToken(fetcher));
    return fetcher(new Request(request, { headers, credentials: "same-origin" }));
  }

  return async (input, init) => {
    const request = new Request(absolute(input), init);
    const retry = request.clone();
    const response = await send(request);
    const path = new URL(request.url, "http://local").pathname;
    if (response.status !== 401 || NO_RETRY_PATHS.includes(path)) return response;
    const refreshed = await send(new Request(absolute("/v1/auth/refresh"), { method: "POST" }));
    if (refreshed.ok) return send(retry);
    onSessionExpired(loginUrl(window.location.pathname + window.location.search));
    return response;
  };
}

export const authFetch = createAuthFetch();
export const api = createClient<paths>({ baseUrl: "", fetch: authFetch });

/** Turn an API problem response into a message for the user. */
export function problemMessage(error: unknown, fallback = "Something went wrong."): string {
  if (error && typeof error === "object" && "detail" in error && typeof error.detail === "string") {
    return error.detail;
  }
  if (error && typeof error === "object" && "title" in error && typeof error.title === "string") {
    return error.title;
  }
  return fallback;
}
