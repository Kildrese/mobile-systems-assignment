import { useEffect } from "react";
import { Link, useSearchParams } from "react-router";
import { DeleteAccount } from "@/components/account/delete-account";
import { PasswordForm } from "@/components/account/password-form";
import { ProfileForm } from "@/components/account/profile-form";
import { LoginForm } from "@/components/auth/login-form";
import { SignupForm } from "@/components/auth/signup-form";
import { InternshipReport } from "@/components/internships/report";
import { Button } from "@/components/ui/button";
import { API_URL, APP_NAME } from "@/lib/app";
import { useUser } from "@/lib/use-auth";
import { safeNext } from "@/lib/safe-next";

function useTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME;
  }, [title]);
}

function useNext(): string {
  const [params] = useSearchParams();
  return safeNext(params.get("next"));
}

export function LoginPage() {
  useTitle("Sign in");
  return <LoginForm next={useNext()} />;
}

export function RegisterPage() {
  useTitle("Create account");
  return <SignupForm next={useNext()} />;
}

export function HomePage() {
  useTitle();
  const user = useUser();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Hello, {user.firstName}!</h1>
      <p className="text-muted-foreground">
        You&apos;re signed in as @{user.username}.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link to="/internships">Internship report</Link>
        </Button>
        <Button asChild variant="outline">
          <Link to="/account">Manage your account</Link>
        </Button>
        <Button asChild variant="outline">
          <a href={`${API_URL}/docs`}>API reference</a>
        </Button>
      </div>
    </div>
  );
}

export function AccountPage() {
  useTitle("Account");
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold">Account</h1>
      <ProfileForm />
      <PasswordForm />
      <DeleteAccount />
    </div>
  );
}

export function InternshipsPage() {
  useTitle("Internships");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Internships</h1>
      <InternshipReport />
    </div>
  );
}
