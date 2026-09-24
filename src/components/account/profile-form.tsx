"use client";

import { useActionState } from "react";
import { updateProfileAction } from "@/actions/account";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { asErrors, initialFormState } from "@/lib/forms";
import { useFormToast } from "./use-form-toast";

type Props = { username: string; firstName: string; lastName: string };

export function ProfileForm({ username, firstName, lastName }: Props) {
  const [state, action, pending] = useActionState(updateProfileAction, initialFormState);
  useFormToast(state);
  const errors = state.fieldErrors ?? {};
  const values = state.values ?? { username, firstName, lastName };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your username and your name as shown in the app.</CardDescription>
      </CardHeader>
      <form action={action} className="contents">
        <CardContent>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field data-invalid={!!errors.username}>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                defaultValue={values.username}
                aria-invalid={!!errors.username}
                minLength={3}
                maxLength={30}
                pattern="[a-zA-Z0-9_.]+"
                required
              />
              <FieldDescription>3-30 letters, digits, _ or . You can sign in with it.</FieldDescription>
              <FieldError errors={asErrors(errors.username)} />
            </Field>
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
