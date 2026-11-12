import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { AppHeader } from "@/components/app-header";
import { currentUser } from "@/lib/server-session";

/** Server-side check on every page in the app. The API still authorises every request itself. */
export default async function AppLayout({ children }: { children: ReactNode }) {
  const me = await currentUser();
  if (!me) {
    const path = (await headers()).get("x-pathname") ?? "/";
    redirect(`/login?next=${encodeURIComponent(path)}`);
  }
  return (
    <>
      <AppHeader me={me} />
      <main id="main" className="mx-auto max-w-7xl px-4 py-6">
        {children}
      </main>
    </>
  );
}
