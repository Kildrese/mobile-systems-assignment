"use client";

import { useActionState } from "react";
import { changePasswordAction } from "@/app/(app)/account/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { asErrors, initialFormState } from "@/lib/forms";
import { useFormToast } from "./use-form-toast";

export function PasswordForm() {
  const [state, action, pending] = useActionState(changePasswordAction, initialFormState);
  useFormToast(state);
  const errors = state.fieldErrors ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
        <CardDescription>
          Changing your password signs you out on all other devices.
        </CardDescription>
      </CardHeader>
      <form action={action} className="contents">
        <CardContent>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field data-invalid={!!errors.currentPassword}>
              <FieldLabel htmlFor="currentPassword">Current password</FieldLabel>
              <Input
                id="currentPassword"
                name="currentPassword"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!errors.currentPassword}
                required
              />
              <FieldError errors={asErrors(errors.currentPassword)} />
            </Field>
            <Field>
              <Field className="grid gap-4 sm:grid-cols-2">
                <Field data-invalid={!!errors.newPassword}>
                  <FieldLabel htmlFor="newPassword">New password</FieldLabel>
                  <Input
                    id="newPassword"
                    name="newPassword"
                    type="password"
                    autoComplete="new-password"
                    aria-invalid={!!errors.newPassword}
                    minLength={8}
                    maxLength={128}
                    required
                  />
                  <FieldError errors={asErrors(errors.newPassword)} />
                </Field>
                <Field data-invalid={!!errors.confirmPassword}>
                  <FieldLabel htmlFor="confirmPassword">Confirm new password</FieldLabel>
                  <Input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    autoComplete="new-password"
                    aria-invalid={!!errors.confirmPassword}
                    required
                  />
                  <FieldError errors={asErrors(errors.confirmPassword)} />
                </Field>
              </Field>
              <FieldDescription>Must be at least 8 characters long.</FieldDescription>
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Change password"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
