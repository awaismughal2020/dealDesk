"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import type { Me } from "@/lib/api/types";
import { useLogout } from "@/lib/hooks";
import { cn } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  permission?: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/runs/new", label: "New run", permission: "run:create" },
  { href: "/impact", label: "Impact" },
  { href: "/admin", label: "Admin", permission: "user:manage" },
];

export function AppHeader({ me }: { me: Me }) {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useLogout();
  const items = NAV.filter((item) => !item.permission || me.permissions.includes(item.permission));

  async function signOut() {
    await logout.mutateAsync();
    router.replace("/login");
    router.refresh();
  }

  return (
    <header className="border-border border-b bg-white">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-4 py-3">
        <Link href="/" className="text-lg font-bold">
          Deal Desk
        </Link>
        <nav aria-label="Main" className="flex flex-1 flex-wrap gap-1">
          {items.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "hover:bg-muted rounded-md px-3 py-2 text-sm font-medium",
                  active && "bg-muted text-brand",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-3 text-sm">
          <span>
            <span className="font-medium">{me.display_name}</span>{" "}
            <span className="text-muted-foreground">({me.role})</span>
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void signOut()}
            disabled={logout.isPending}
          >
            Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}
