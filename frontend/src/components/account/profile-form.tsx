import { useMutation } from "@tanstack/react-query";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { toast } from "sonner";
import { updateUserMutation } from "@/api/@tanstack/react-query.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useAuth, useUser } from "@/lib/use-auth";
import { asErrors, errorCode, fromApiError, SOMETHING_WENT_WRONG, type FormErrors } from "@/lib/forms";

export function ProfileForm() {
  const user = useUser();
  const { setUser } = useAuth();
  const [values, setValues] = useState({
    username: user.username,
    firstName: user.firstName,
    lastName: user.lastName,
  });
  const [state, setState] = useState<FormErrors>({});
  const update = useMutation(updateUserMutation());
  const errors = state.fieldErrors ?? {};

  const bind = (name: keyof typeof values) => ({
    name,
    value: values[name],
    onChange: (event: ChangeEvent<HTMLInputElement>) =>
      setValues((v) => ({ ...v, [name]: event.target.value })),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setState({});
    update.mutate(
      { path: { id: user.id }, body: values },
      {
        onSuccess: (updated) => {
          setUser(updated);
          // Shows the stored form, e.g. the lowercased username.
          setValues({
            username: updated.username,
            firstName: updated.firstName,
            lastName: updated.lastName,
          });
          toast.success("Profile updated");
        },
        onError: (error) => {
          if (errorCode(error) === "USERNAME_TAKEN") {
            setState({ fieldErrors: { username: ["Username already taken"] } });
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
        <CardTitle>Profile</CardTitle>
        <CardDescription>Your username and your name as shown in the app.</CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit} className="contents">
        <CardContent>
          <FieldGroup>
            {state.formError && <FieldError>{state.formError}</FieldError>}
            <Field data-invalid={!!errors.username}>
              <FieldLabel htmlFor="username">Username</FieldLabel>
              <Input
                id="username"
                {...bind("username")}
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
            <Field className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={!!errors.firstName}>
                <FieldLabel htmlFor="firstName">First name</FieldLabel>
                <Input
                  id="firstName"
                  {...bind("firstName")}
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
                  {...bind("lastName")}
                  autoComplete="family-name"
                  aria-invalid={!!errors.lastName}
                  maxLength={100}
                />
                <FieldError errors={asErrors(errors.lastName)} />
              </Field>
            </Field>
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
