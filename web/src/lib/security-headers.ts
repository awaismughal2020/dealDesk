/** Content-Security-Policy and other headers for every page. Scripts need a per-request nonce. */

export function contentSecurityPolicy(
  nonce: string,
  { dev, local }: { dev: boolean; local: boolean },
): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Inline style attributes are used by Radix and Recharts; scripts stay nonce-only.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (!local) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

export function securityHeaders(local: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
  };
  if (!local) headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains";
  return headers;
}

export const PUBLIC_PATHS = ["/login", "/healthz", "/auth/oidc"];

export function isPublicPath(pathname: string): boolean {
  return PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}
