"use client";

import { useActionState } from "react";
import { changeEmailAction } from "@/app/(app)/account/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { asErrors, initialFormState } from "@/lib/forms";
import { useFormToast } from "./use-form-toast";

export function EmailForm({ email }: { email: string }) {
  const [state, action, pending] = useActionState(changeEmailAction, initialFormState);
  useFormToast(state);
  const errors = state.fieldErrors ?? {};

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email</CardTitle>
        <CardDescription>
          Currently <span className="font-medium text-foreground">{email}</span>. The change takes
          effect immediately.
        </CardDescription>
      </CardHeader>
      <form action={action} className="contents">
        <CardContent>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field data-invalid={!!errors.newEmail}>
              <FieldLabel htmlFor="newEmail">New email</FieldLabel>
              <Input
                id="newEmail"
                name="newEmail"
                type="email"
                autoComplete="email"
                defaultValue={state.values?.newEmail}
                aria-invalid={!!errors.newEmail}
                maxLength={254}
                required
              />
              <FieldError errors={asErrors(errors.newEmail)} />
            </Field>
            <Field data-invalid={!!errors.currentPassword}>
              <FieldLabel htmlFor="emailCurrentPassword">Current password</FieldLabel>
              <Input
                id="emailCurrentPassword"
                name="currentPassword"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!errors.currentPassword}
                required
              />
              <FieldError errors={asErrors(errors.currentPassword)} />
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Change email"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
