import { cookies } from "next/headers";
import type { Me } from "@/lib/api/types";

/** Ask the API who the cookie belongs to. Server-side check; the API remains the authority. */
export async function currentUser(): Promise<Me | null> {
  const jar = await cookies();
  const access = jar.get("dd_access");
  if (!access) return null;
  const response = await fetch(
    `${process.env.API_INTERNAL_URL ?? "http://localhost:8000"}/v1/auth/me`,
    {
      headers: { cookie: `dd_access=${access.value}` },
      cache: "no-store",
    },
  );
  if (!response.ok) return null;
  return (await response.json()) as Me;
}
