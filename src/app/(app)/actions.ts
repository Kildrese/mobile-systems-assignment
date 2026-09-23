"use server";

import { redirect } from "next/navigation";
import { signOut } from "@/lib/services/account";
import { clearSessionCookie, getSessionToken } from "@/lib/session";

// Revokes this browser's session, clears the cookie and goes to /login, even
// when the session was already gone.
export async function signOutAction(): Promise<void> {
  const token = await getSessionToken();
  if (token) {
    try {
      await signOut(token);
    } catch (err) {
      console.error("[web] sign-out failed to revoke the session:", err);
    }
  }
  await clearSessionCookie();
  redirect("/login");
}
