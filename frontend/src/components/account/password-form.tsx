import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { changePasswordMutation } from "@/api/@tanstack/react-query.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  asErrors,
  errorCode,
  formValues,
  fromApiError,
  SOMETHING_WENT_WRONG,
  type FormErrors,
} from "@/lib/forms";
import { setToken } from "@/lib/token";

export function PasswordForm() {
  const [state, setState] = useState<FormErrors>({});
  const change = useMutation(changePasswordMutation());
  const errors = state.fieldErrors ?? {};

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const { currentPassword, newPassword, confirmPassword } = formValues(form);
    if (newPassword !== confirmPassword) {
      setState({ fieldErrors: { confirmPassword: ["Passwords don't match"] } });
      return;
    }
    setState({});
    change.mutate(
      { body: { currentPassword, newPassword } },
      {
        onSuccess: ({ token }) => {
          // Every old token is revoked; this browser continues with the new one.
          setToken(token);
          form.reset();
          toast.success("Password changed. Other devices have been signed out.");
        },
        onError: (error) => {
          if (errorCode(error) === "INVALID_PASSWORD") {
            setState({ fieldErrors: { currentPassword: ["Incorrect password"] } });
          } else {
            setState(fromApiError(error) ?? { formError: SOMETHING_WENT_WRONG });
          }
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
        <CardDescription>Changing your password signs you out on all other devices.</CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit} className="contents">
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
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? "Saving…" : "Change password"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
