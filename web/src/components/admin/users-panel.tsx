"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { QueryState } from "@/components/query-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { FieldError, Input, Label, Select } from "@/components/ui/input";
import { Table, Td, Th } from "@/components/ui/table";
import { problemMessage } from "@/lib/api/client";
import type { Role } from "@/lib/api/types";
import { useCreateUser, useUpdateUser, useUsers } from "@/lib/hooks";

const ROLES: Role[] = ["viewer", "estimator", "approver", "admin"];

export const newUserSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  display_name: z.string().trim().min(1, "Enter a name.").max(200),
  role: z.enum(["viewer", "estimator", "approver", "admin"]),
  password: z.string().min(12, "Use at least 12 characters.").max(128),
});
type NewUser = z.infer<typeof newUserSchema>;

function CreateUserForm() {
  const create = useCreateUser();
  const form = useForm<NewUser>({
    resolver: zodResolver(newUserSchema),
    defaultValues: { email: "", display_name: "", role: "viewer", password: "" },
  });
  const { errors } = form.formState;
  const submit = form.handleSubmit(async (values) => {
    try {
      await create.mutateAsync(values);
      toast.success("User created");
      form.reset();
    } catch (problem) {
      toast.error(problemMessage(problem, "Could not create the user."));
    }
  });
  return (
    <form
      onSubmit={submit}
      noValidate
      className="grid gap-3 md:grid-cols-5"
      aria-label="Create user"
    >
      <div>
        <Label htmlFor="new-email">Email</Label>
        <Input
          id="new-email"
          type="email"
          aria-invalid={errors.email ? true : undefined}
          aria-describedby="new-email-error"
          {...form.register("email")}
        />
        <FieldError id="new-email-error" message={errors.email?.message} />
      </div>
      <div>
        <Label htmlFor="new-name">Name</Label>
        <Input
          id="new-name"
          aria-invalid={errors.display_name ? true : undefined}
          aria-describedby="new-name-error"
          {...form.register("display_name")}
        />
        <FieldError id="new-name-error" message={errors.display_name?.message} />
      </div>
      <div>
        <Label htmlFor="new-role">Role</Label>
        <Select id="new-role" {...form.register("role")}>
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </Select>
      </div>
      <div>
        <Label htmlFor="new-password">Password</Label>
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby="new-password-error"
          {...form.register("password")}
        />
        <FieldError id="new-password-error" message={errors.password?.message} />
      </div>
      <div className="flex items-end">
        <Button type="submit" disabled={create.isPending} className="w-full">
          Create user
        </Button>
      </div>
    </form>
  );
}

export function UsersPanel({ currentUserId }: { currentUserId: string }) {
  const users = useUsers(true);
  const update = useUpdateUser();

  async function change(userId: string, body: { role?: Role; is_active?: boolean }) {
    try {
      await update.mutateAsync({ userId, ...body });
      toast.success("User updated; their sessions were revoked");
    } catch (problem) {
      toast.error(problemMessage(problem, "Could not update the user."));
    }
  }

  return (
    <Card aria-labelledby="users-heading">
      <CardTitle id="users-heading">Users</CardTitle>
      <CreateUserForm />
      <div className="mt-6">
        <QueryState
          isPending={users.isPending}
          error={users.error}
          retry={() => void users.refetch()}
        >
          <Table aria-label="Users">
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Email</Th>
                <Th>Role</Th>
                <Th>Status</Th>
                <Th>Actions</Th>
              </tr>
            </thead>
            <tbody>
              {users.data?.items.map((user) => {
                const self = user.id === currentUserId;
                return (
                  <tr key={user.id}>
                    <Td>{user.display_name}</Td>
                    <Td>{user.email}</Td>
                    <Td>
                      <label htmlFor={`role-${user.id}`} className="sr-only">
                        Role for {user.email}
                      </label>
                      <Select
                        id={`role-${user.id}`}
                        value={user.role}
                        disabled={self || update.isPending}
                        onChange={(event) =>
                          void change(user.id, { role: event.target.value as Role })
                        }
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </Select>
                    </Td>
                    <Td>
                      <Badge tone={user.is_active ? "success" : "neutral"}>
                        {user.is_active ? "Active" : "Deactivated"}
                      </Badge>
                    </Td>
                    <Td>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={self || update.isPending}
                        onClick={() => void change(user.id, { is_active: !user.is_active })}
                        aria-label={`${user.is_active ? "Deactivate" : "Activate"} ${user.email}`}
                      >
                        {user.is_active ? "Deactivate" : "Activate"}
                      </Button>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        </QueryState>
      </div>
    </Card>
  );
}
