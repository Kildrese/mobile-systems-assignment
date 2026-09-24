"use client";

import Link from "next/link";
import { useActionState } from "react";
import { registerAction } from "@/actions/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { asErrors, initialFormState } from "@/lib/forms";

export function SignupForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState(registerAction, initialFormState);
  const errors = state.fieldErrors ?? {};
  const loginHref = next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`;

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-xl">Create your account</CardTitle>
        <CardDescription>Enter your details below to create your account</CardDescription>
      </CardHeader>
      <CardContent>
        <form action={action}>
          <input type="hidden" name="next" value={next} />
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field className="grid grid-cols-2 gap-4">
              <Field data-invalid={!!errors.firstName}>
                <FieldLabel htmlFor="firstName">First name</FieldLabel>
                <Input
                  id="firstName"
                  name="firstName"
                  autoComplete="given-name"
                  defaultValue={state.values?.firstName}
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
                  defaultValue={state.values?.lastName}
                  aria-invalid={!!errors.lastName}
                  maxLength={100}
                  required
                />
                <FieldError errors={asErrors(errors.lastName)} />
              </Field>
            </Field>
            <Field data-invalid={!!errors.email}>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="m@example.com"
                defaultValue={state.values?.email}
                aria-invalid={!!errors.email}
                required
              />
              <FieldError errors={asErrors(errors.email)} />
            </Field>
            <Field>
              <Field className="grid grid-cols-2 gap-4">
                <Field data-invalid={!!errors.password}>
                  <FieldLabel htmlFor="password">Password</FieldLabel>
                  <Input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    aria-invalid={!!errors.password}
                    minLength={8}
                    maxLength={128}
                    required
                  />
                  <FieldError errors={asErrors(errors.password)} />
                </Field>
                <Field data-invalid={!!errors.confirmPassword}>
                  <FieldLabel htmlFor="confirmPassword">Confirm password</FieldLabel>
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
            <Field>
              <Button type="submit" disabled={pending}>
                {pending ? "Creating account…" : "Create account"}
              </Button>
              <FieldDescription className="text-center">
                Already have an account? <Link href={loginHref}>Sign in</Link>
              </FieldDescription>
            </Field>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
