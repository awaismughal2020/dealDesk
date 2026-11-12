/**
 * Same-origin proxy: the browser only ever talks to this Next.js server, which forwards /v1/* to
 * the API's internal address (never exposed to the browser). Cookies stay first-party.
 */
import type { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const FORWARD_REQUEST_HEADERS = [
  "accept",
  "content-type",
  "cookie",
  "origin",
  "referer",
  "x-csrf-token",
  "x-request-id",
];
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "cache-control",
  "retry-after",
  "x-request-id",
];

function apiBase(): string {
  return process.env.API_INTERNAL_URL ?? "http://localhost:8000";
}

async function forward(request: NextRequest): Promise<Response> {
  const target = new URL(request.nextUrl.pathname + request.nextUrl.search, apiBase());
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  headers.set("x-forwarded-for", clientIp || "127.0.0.1");
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    redirect: "manual",
    cache: "no-store",
    // Required by Node's fetch when streaming a request body.
    ...(hasBody ? { duplex: "half" } : {}),
  } as RequestInit);

  const responseHeaders = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  for (const cookie of upstream.headers.getSetCookie())
    responseHeaders.append("set-cookie", cookie);
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
