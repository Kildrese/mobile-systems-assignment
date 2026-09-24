import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { changeEmailMutation } from "@/api/@tanstack/react-query.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useAuth, useUser } from "@/lib/use-auth";
import {
  asErrors,
  errorCode,
  formValues,
  fromApiError,
  SOMETHING_WENT_WRONG,
  type FormErrors,
} from "@/lib/forms";

export function EmailForm() {
  const { email } = useUser();
  const { setUser } = useAuth();
  const [state, setState] = useState<FormErrors>({});
  const change = useMutation(changeEmailMutation());
  const errors = state.fieldErrors ?? {};

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const { newEmail, currentPassword } = formValues(form);
    setState({});
    change.mutate(
      { body: { newEmail, currentPassword } },
      {
        onSuccess: (user) => {
          setUser(user);
          form.reset();
          toast.success("Email updated");
        },
        onError: (error) => {
          switch (errorCode(error)) {
            case "INVALID_PASSWORD":
              return setState({ fieldErrors: { currentPassword: ["Incorrect password"] } });
            case "EMAIL_TAKEN":
              return setState({ fieldErrors: { newEmail: ["Email already registered"] } });
            default:
              return setState(fromApiError(error) ?? { formError: SOMETHING_WENT_WRONG });
          }
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Email</CardTitle>
        <CardDescription>
          {email ? (
            <>
              Currently <span className="font-medium text-foreground">{email}</span>.
            </>
          ) : (
            "You haven't added an email yet."
          )}{" "}
          The change takes effect immediately.
        </CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit} className="contents">
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
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? "Saving…" : "Change email"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
