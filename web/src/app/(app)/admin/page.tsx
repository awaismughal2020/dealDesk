import type { Metadata } from "next";
import { AuditPanel } from "@/components/admin/audit-panel";
import { UsersPanel } from "@/components/admin/users-panel";
import { Alert } from "@/components/ui/alert";
import { currentUser } from "@/lib/server-session";

export const metadata: Metadata = { title: "Admin" };

export default async function AdminPage() {
  const me = await currentUser();
  if (!me?.permissions.includes("user:manage")) {
    return (
      <Alert tone="warning" title="Admins only">
        Your role cannot manage users or read the audit log.
      </Alert>
    );
  }
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Admin</h1>
      <UsersPanel currentUserId={me.id} />
      <AuditPanel />
    </div>
  );
}
