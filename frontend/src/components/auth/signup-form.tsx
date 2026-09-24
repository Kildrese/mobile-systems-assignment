import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { loginMutation, registerMutation } from "@/api/@tanstack/react-query.gen";
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

export function SignupForm({ next }: { next: string }) {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState<FormErrors>({});
  const register = useMutation(registerMutation());
  const login = useMutation(loginMutation());
  const pending = register.isPending || login.isPending;
  const errors = state.fieldErrors ?? {};

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { firstName, lastName, username, email, password, confirmPassword } = formValues(
      event.currentTarget,
    );
    if (password !== confirmPassword) {
      setState({ fieldErrors: { confirmPassword: ["Passwords don't match"] } });
      return;
    }
    setState({});

    try {
      const user = await register.mutateAsync({
        body: { firstName, lastName, username, email, password },
      });
      // Registration returns no token: sign in right away.
      const session = await login.mutateAsync({ body: { username: user.username, password } });
      signIn(session.token, session.user);
      navigate(next, { replace: true });
    } catch (error) {
      switch (errorCode(error)) {
        case "EMAIL_TAKEN":
          return setState({ fieldErrors: { email: ["Email already registered"] } });
        case "USERNAME_TAKEN":
          return setState({ fieldErrors: { username: ["Username already taken"] } });
        default:
          return setState(fromApiError(error) ?? { formError: SOMETHING_WENT_WRONG });
      }
    }
  }

  return (
    <Card>
      <CardHeader className="text-center">
        <CardTitle className="text-xl">Create your account</CardTitle>
        <CardDescription>Enter your details below to create your account</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit}>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field className="grid grid-cols-2 gap-4">
              <Field data-invalid={!!errors.firstName}>
                <FieldLabel htmlFor="firstName">First name</FieldLabel>
                <Input
                  id="firstName"
                  name="firstName"
                  autoComplete="given-name"
                  aria-invalid={!!errors.firstName}
                  maxLength={100}
                  required
                />
                <FieldError errors={asErrors(errors.firstName)} />
              </Field>
              <Field data-invalid={!!errors.lastName}>
                <FieldLabel htmlFor="lastName">Last name (optional)</FieldLabel>
                <Input
                  id="lastName"
                  name="lastName"
                  autoComplete="family-name"
                  aria-invalid={!!errors.lastName}
                  maxLength={100}
                />
                <FieldError errors={asErrors(errors.lastName)} />
              </Field>
            </Field>
            <Field data-invalid={!!errors.username}>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                aria-invalid={!!errors.username}
                minLength={3}
                maxLength={30}
                pattern="[a-zA-Z0-9_.]+"
                required
              />
              <FieldDescription>3-30 letters, digits, _ or . You can sign in with it.</FieldDescription>
              <FieldError errors={asErrors(errors.username)} />
            </Field>
            <Field data-invalid={!!errors.email}>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="m@example.com"
                aria-invalid={!!errors.email}
                maxLength={254}
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
                Already have an account? <Link to={authHref("/login", next)}>Sign in</Link>
              </FieldDescription>
            </Field>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  );
}
