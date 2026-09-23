import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/auth/login-form";
import { getCurrentSession, safeNext } from "@/lib/session";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const next = safeNext((await searchParams).next);
  // A real check, not just cookie presence: a stale cookie shows the form
  // instead of looping between here and the app layout.
  if (await getCurrentSession()) redirect(next);
  return <LoginForm next={next} />;
}
