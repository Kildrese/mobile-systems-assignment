import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { loginMutation } from "@/api/@tanstack/react-query.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/use-auth";
import {
  asErrors,
  errorCode,
  formValues,
  fromApiError,
  SOMETHING_WENT_WRONG,
  type FormErrors,
} from "@/lib/forms";
import { authHref } from "@/lib/safe-next";

export function LoginForm({ next }: { next: string }) {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<FormErrors>({});
  const login = useMutation(loginMutation());
  const errors = state.fieldErrors ?? {};

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { identifier, password } = formValues(event.currentTarget);
    setState({});
    login.mutate(
      { body: { identifier, password } },
      {
        onSuccess: ({ token, user }) => {
          signIn(token, user);
          navigate(next, { replace: true });
        },
        onError: (error) => {
          if (errorCode(error) === "INVALID_CREDENTIALS") {
            setState({ formError: "Invalid email, username or password" });
          } else {
            setState(fromApiError(error) ?? { formError: SOMETHING_WENT_WRONG });
          }
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-xl">Welcome back</CardTitle>
        <CardDescription>Sign in with your email or username</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit}>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field data-invalid={!!errors.identifier}>
              <FieldLabel htmlFor="identifier">Email or username</FieldLabel>
              <Input
                id="identifier"
                name="identifier"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                aria-invalid={!!errors.identifier}
                maxLength={254}
                required
              />
              <FieldError errors={asErrors(errors.identifier)} />
            </Field>
            <Field data-invalid={!!errors.password}>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                aria-invalid={!!errors.password}
                required
              />
              <FieldError errors={asErrors(errors.password)} />
            </Field>
            <Field>
              <Button type="submit" disabled={login.isPending}>
                {login.isPending ? "Signing in…" : "Sign in"}
              </Button>
              <FieldDescription className="text-center">
                Don&apos;t have an account? <Link to={authHref("/register", next)}>Sign up</Link>
              </FieldDescription>
            </Field>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
