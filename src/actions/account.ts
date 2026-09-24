"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { ChangeEmailBody, ChangePasswordBody, UpdateUserBody } from "@/lib/api/contracts";
import { fromZodError, pick, type FormState } from "@/lib/forms";
import * as account from "@/lib/services/account";
import { clearSessionCookie, requireSession, setSessionCookie } from "@/lib/session";

const success = (message: string) => ({ message, at: Date.now() });

export async function updateProfileAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const { user } = await requireSession();
  const input = pick(formData, ["username", "firstName", "lastName"]);
  const values = {
    username: input.username ?? "",
    firstName: input.firstName ?? "",
    lastName: input.lastName ?? "",
  };

  const parsed = UpdateUserBody.safeParse(input);
  if (!parsed.success) return { ...fromZodError(parsed.error), values };

  const result = await account.updateProfile(user.id, parsed.data);
  if (!result.ok) {
    switch (result.code) {
      case "USERNAME_TAKEN":
        return { fieldErrors: { username: ["Username already taken"] }, values };
      case "NOT_FOUND":
        redirect("/login");
    }
  }

  revalidatePath("/", "layout");
  const { username, firstName, lastName } = result.user;
  return { values: { username, firstName, lastName }, success: success("Profile updated") };
}

export async function changeEmailAction(_prev: FormState, formData: FormData): Promise<FormState> {
  const { user } = await requireSession();
  const input = pick(formData, ["newEmail", "currentPassword"]);
  const values = { newEmail: input.newEmail ?? "" };

  const parsed = ChangeEmailBody.safeParse(input);
  if (!parsed.success) return { ...fromZodError(parsed.error), values };

  const result = await account.changeEmail(user.id, parsed.data);
  if (!result.ok) {
    switch (result.code) {
      case "INVALID_PASSWORD":
        return { fieldErrors: { currentPassword: ["Incorrect password"] }, values };
      case "EMAIL_TAKEN":
        return { fieldErrors: { newEmail: ["Email already registered"] }, values };
      case "NOT_FOUND":
        redirect("/login");
    }
  }

  revalidatePath("/", "layout");
  return { success: success("Email updated") };
}

export async function changePasswordAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const { session } = await requireSession();
  const input = pick(formData, ["currentPassword", "newPassword"]);
  const confirmPassword = formData.get("confirmPassword");

  const parsed = ChangePasswordBody.safeParse(input);
  const errors = parsed.success ? {} : fromZodError(parsed.error);
  if (input.newPassword && confirmPassword !== input.newPassword) {
    errors.fieldErrors = { ...errors.fieldErrors, confirmPassword: ["Passwords don't match"] };
  }
  if (!parsed.success || errors.fieldErrors?.confirmPassword) return errors;

  const result = await account.changePassword(session.token, parsed.data);
  if (!result.ok) return { fieldErrors: { currentPassword: ["Incorrect password"] } };

  // Every old session is revoked; keep this browser signed in with the new one.
  await setSessionCookie(result.token, result.expiresAt);
  revalidatePath("/", "layout");
  return { success: success("Password changed. Other devices have been signed out.") };
}

export async function deleteAccountAction(): Promise<void> {
  const { user } = await requireSession();
  await account.deleteAccount(user.id);
  await clearSessionCookie();
  redirect("/login");
}
