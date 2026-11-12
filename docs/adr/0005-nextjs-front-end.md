# ADR 0005: Next.js (App Router) for the front end

Status: accepted

## Decision
Next.js 16 with TypeScript strict, Tailwind, Radix-based shadcn-style components, TanStack Query,
React Hook Form with Zod and Recharts. The browser talks only to Next.js; a runtime route handler
proxies `/v1/*` to the API's internal address, so cookies are first-party and the API is never
exposed. `proxy.ts` (Next 16's renamed middleware) sets a per-request nonce CSP and guards pages;
server components re-check the session. The API client is generated from OpenAPI.

## Consequences
All pages render dynamically (nonces need a request). No business logic or money arithmetic runs in
the browser: amounts are decimal strings formatted as strings.
