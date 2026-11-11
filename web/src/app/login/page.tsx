import type { Metadata } from "next";
import { LoginForm } from "@/components/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { next, error } = await searchParams;
  return (
    <main id="main" className="mx-auto mt-16 max-w-sm px-4">
      <h1 className="mb-2 text-2xl font-bold">Sign in to Deal Desk</h1>
      <p className="text-muted-foreground mb-6 text-sm">
        Demo accounts are created by <code>make init</code>; their passwords are in your local{" "}
        <code>.env</code>.
      </p>
      <LoginForm
        next={next ?? "/"}
        oidc={process.env.AUTH_MODE === "oidc"}
        oidcError={error === "oidc"}
      />
    </main>
  );
}
