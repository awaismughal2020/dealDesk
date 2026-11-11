import { NextResponse, type NextRequest } from "next/server";
import { codeChallenge, randomToken, safeNext } from "@/lib/pkce";

export const dynamic = "force-dynamic";
const FLOW_COOKIE_PATH = "/auth/oidc";
const FLOW_MAX_AGE = 600;

/** Start Authorization Code + PKCE. The verifier and state live in short-lived HttpOnly cookies. */
export async function GET(request: NextRequest) {
  const authorize = process.env.OIDC_AUTHORIZE_URL;
  const clientId = process.env.OIDC_CLIENT_ID;
  if (process.env.AUTH_MODE !== "oidc" || !authorize || !clientId) {
    return NextResponse.json({ title: "OIDC is not configured" }, { status: 404 });
  }
  const verifier = randomToken();
  const state = randomToken(16);
  const url = new URL(authorize);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", clientId);
  url.searchParams.set("redirect_uri", new URL("/auth/oidc/callback", request.url).toString());
  url.searchParams.set("scope", "openid email profile");
  url.searchParams.set("state", state);
  url.searchParams.set("code_challenge", await codeChallenge(verifier));
  url.searchParams.set("code_challenge_method", "S256");
  const response = NextResponse.redirect(url);
  const secure = process.env.APP_ENV !== "local";
  const options = {
    httpOnly: true,
    sameSite: "lax" as const,
    secure,
    path: FLOW_COOKIE_PATH,
    maxAge: FLOW_MAX_AGE,
  };
  response.cookies.set("dd_pkce", verifier, options);
  response.cookies.set("dd_state", state, options);
  response.cookies.set("dd_next", safeNext(request.nextUrl.searchParams.get("next")), options);
  return response;
}
