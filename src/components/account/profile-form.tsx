"use client";

import { useActionState } from "react";
import { updateNameAction } from "@/app/(app)/account/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { asErrors, initialFormState } from "@/lib/forms";
import { useFormToast } from "./use-form-toast";

export function ProfileForm({ firstName, lastName }: { firstName: string; lastName: string }) {
  const [state, action, pending] = useActionState(updateNameAction, initialFormState);
  useFormToast(state);
  const errors = state.fieldErrors ?? {};
  const values = state.values ?? { firstName, lastName };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your name as shown in the app.</CardDescription>
      </CardHeader>
      <form action={action} className="contents">
        <CardContent>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={!!errors.firstName}>
                <FieldLabel htmlFor="firstName">First name</FieldLabel>
                <Input
                  id="firstName"
                  name="firstName"
                  autoComplete="given-name"
                  defaultValue={values.firstName}
                  aria-invalid={!!errors.firstName}
                  maxLength={100}
                  required
                />
                <FieldError errors={asErrors(errors.firstName)} />
              </Field>
              <Field data-invalid={!!errors.lastName}>
                <FieldLabel htmlFor="lastName">Last name</FieldLabel>
                <Input
                  id="lastName"
                  name="lastName"
                  autoComplete="family-name"
                  defaultValue={values.lastName}
                  aria-invalid={!!errors.lastName}
                  maxLength={100}
                  required
                />
                <FieldError errors={asErrors(errors.lastName)} />
              </Field>
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Save"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
