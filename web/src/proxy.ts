import { NextResponse, type NextRequest } from "next/server";
import { contentSecurityPolicy, isPublicPath, securityHeaders } from "@/lib/security-headers";

const ACCESS_COOKIE = "dd_access";

/**
 * Runs before every page: adds a nonce-based CSP and security headers, and sends anyone without a
 * session cookie to sign-in (remembering where they were). This is a usability guard; the API
 * enforces authentication and authorisation on every request regardless.
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const local = (process.env.APP_ENV ?? "local") === "local";

  if (!isPublicPath(pathname) && !request.cookies.has(ACCESS_COOKIE)) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = contentSecurityPolicy(nonce, { dev: process.env.NODE_ENV === "development", local });
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("x-pathname", `${pathname}${search}`);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  for (const [name, value] of Object.entries(securityHeaders(local)))
    response.headers.set(name, value);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!v1/|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
