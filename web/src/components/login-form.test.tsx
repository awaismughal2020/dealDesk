import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "@/components/login-form";
import type * as ClientModule from "@/lib/api/client";
import { renderWithClient } from "@/test/render";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, refresh: vi.fn() }) }));
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof ClientModule>();
  return {
    ...actual,
    api: {
      POST: vi.fn(async (path: string) =>
        path === "/v1/auth/refresh"
          ? { response: new Response(null, { status: 401 }) }
          : {
              error: {
                detail: "Incorrect email or password, or the account is temporarily locked.",
              },
              response: new Response(null, { status: 401 }),
            },
      ),
    },
  };
});

test("validates fields and shows the server's generic error", async () => {
  const user = userEvent.setup();
  renderWithClient(<LoginForm next="/runs/1" oidc={false} />);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Enter your email address.")).toBeInTheDocument();
  expect(screen.getByText("Enter your password.")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Email"), "someone@dealdesk.example");
  await user.type(screen.getByLabelText("Password"), "wrong-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password");
  expect(replace).not.toHaveBeenCalled();
});

test("OIDC mode offers single sign-on and keeps the destination", () => {
  renderWithClient(<LoginForm next="/admin" oidc />);
  expect(screen.getByRole("link", { name: "Sign in with single sign-on" })).toHaveAttribute(
    "href",
    "/auth/oidc/login?next=%2Fadmin",
  );
});
