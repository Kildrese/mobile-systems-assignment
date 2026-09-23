import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { SignupForm } from "@/components/auth/signup-form";
import { getCurrentSession, safeNext } from "@/lib/session";

export const metadata: Metadata = { title: "Create account" };

export default async function RegisterPage({ searchParams }: PageProps<"/register">) {
  const next = safeNext((await searchParams).next);
  // See the login page: a real session check, so a stale cookie can't loop.
  if (await getCurrentSession()) redirect(next);
  return <SignupForm next={next} />;
}
