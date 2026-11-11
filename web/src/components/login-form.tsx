"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { FieldError, Input, Label } from "@/components/ui/input";
import { api, problemMessage } from "@/lib/api/client";
import { safeNext } from "@/lib/pkce";

export const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(3, "Enter your email address.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginForm({
  next,
  oidc,
  oidcError,
}: {
  next: string;
  oidc: boolean;
  oidcError?: boolean;
}) {
  const router = useRouter();
  const destination = safeNext(next);
  const [error, setError] = useState<string | null>(
    oidcError ? "Single sign-on failed. Try again." : null,
  );
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const { errors, isSubmitting } = form.formState;

  // A session may still be refreshable (the access cookie expired but the refresh cookie did not).
  useEffect(() => {
    if (oidc) return;
    let cancelled = false;
    void api.POST("/v1/auth/refresh").then(({ response }) => {
      if (!cancelled && response.ok) router.replace(destination);
    });
    return () => {
      cancelled = true;
    };
  }, [destination, oidc, router]);

  if (oidc) {
    return (
      <div className="space-y-4">
        {error ? <Alert tone="danger">{error}</Alert> : null}
        <Button asChild className="w-full">
          <a href={`/auth/oidc/login?next=${encodeURIComponent(destination)}`}>
            Sign in with single sign-on
          </a>
        </Button>
      </div>
    );
  }

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    const { error: problem } = await api.POST("/v1/auth/login", { body: values });
    if (problem) {
      setError(problemMessage(problem, "Sign-in failed."));
      return;
    }
    router.replace(destination);
    router.refresh();
  });

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="space-y-4"
      aria-describedby={error ? "login-error" : undefined}
    >
      {error ? (
        <div id="login-error">
          <Alert tone="danger">{error}</Alert>
        </div>
      ) : null}
      <div>
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? "email-error" : undefined}
          {...form.register("email")}
        />
        <FieldError id="email-error" message={errors.email?.message} />
      </div>
      <div>
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...form.register("password")}
        />
        <FieldError id="password-error" message={errors.password?.message} />
      </div>
      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
