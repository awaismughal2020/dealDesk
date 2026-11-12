import { NextResponse, type NextRequest } from "next/server";
import { safeNext } from "@/lib/pkce";

export const dynamic = "force-dynamic";

/** Finish Authorization Code + PKCE: check state, exchange the code server-side, set the cookie. */
export async function GET(request: NextRequest) {
  const tokenUrl = process.env.OIDC_TOKEN_URL;
  const clientId = process.env.OIDC_CLIENT_ID;
  const code = request.nextUrl.searchParams.get("code");
  const state = request.nextUrl.searchParams.get("state");
  const verifier = request.cookies.get("dd_pkce")?.value;
  if (
    !tokenUrl ||
    !clientId ||
    !code ||
    !verifier ||
    state !== request.cookies.get("dd_state")?.value
  ) {
    return NextResponse.redirect(new URL("/login?error=oidc", request.url));
  }
  const exchange = await fetch(tokenUrl, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      code_verifier: verifier,
      client_id: clientId,
      redirect_uri: new URL("/auth/oidc/callback", request.url).toString(),
    }),
    cache: "no-store",
  });
  if (!exchange.ok) return NextResponse.redirect(new URL("/login?error=oidc", request.url));
  const tokens = (await exchange.json()) as { access_token: string; expires_in?: number };
  const response = NextResponse.redirect(
    new URL(safeNext(request.cookies.get("dd_next")?.value), request.url),
  );
  response.cookies.set("dd_access", tokens.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.APP_ENV !== "local",
    path: "/",
    maxAge: tokens.expires_in ?? 300,
  });
  for (const name of ["dd_pkce", "dd_state", "dd_next"])
    response.cookies.delete({ name, path: "/auth/oidc" });
  return response;
}
