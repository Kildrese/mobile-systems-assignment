"use server";

import { redirect } from "next/navigation";
import { LoginBody, RegisterBody } from "@/lib/api/contracts";
import { fromZodError, pick, type FormState } from "@/lib/forms";
import { registerUser, signIn } from "@/lib/services/account";
import { safeNext, setSessionCookie } from "@/lib/session";

export async function signInAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const input = pick(formData, ["identifier", "password"]);
  const values = { identifier: input.identifier ?? "" };

  const parsed = LoginBody.safeParse(input);
  if (!parsed.success) return { ...fromZodError(parsed.error), values };

  const result = await signIn(parsed.data);
  if (!result.ok) return { formError: "Invalid email, username or password", values };

  await setSessionCookie(result.token, result.expiresAt);
  redirect(safeNext(formData.get("next")));
}

export async function registerAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const input = pick(formData, ["firstName", "lastName", "username", "email", "password"]);
  const confirmPassword = formData.get("confirmPassword");
  const values = {
    firstName: input.firstName ?? "",
    lastName: input.lastName ?? "",
    username: input.username ?? "",
    email: input.email ?? "",
  };

  const parsed = RegisterBody.safeParse(input);
  const errors = parsed.success ? { fieldErrors: {} } : fromZodError(parsed.error);
  if (input.password && confirmPassword !== input.password) {
    errors.fieldErrors = { ...errors.fieldErrors, confirmPassword: ["Passwords don't match"] };
  }
  if (!parsed.success || errors.fieldErrors?.confirmPassword) return { ...errors, values };

  const created = await registerUser(parsed.data);
  if (!created.ok) {
    return created.code === "EMAIL_TAKEN"
      ? { fieldErrors: { email: ["Email already registered"] }, values }
      : { fieldErrors: { username: ["Username already taken"] }, values };
  }

  const { username, password } = parsed.data;
  const session = await signIn({ identifier: username, password });
  if (!session.ok) throw new Error("Sign-in failed right after registration");

  await setSessionCookie(session.token, session.expiresAt);
  redirect(safeNext(formData.get("next")));
}
