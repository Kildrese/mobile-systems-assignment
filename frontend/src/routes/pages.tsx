import { BookOpen, Briefcase, UserRound, type LucideIcon } from "lucide-react";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router";
import { DeleteAccount } from "@/components/account/delete-account";
import { PasswordForm } from "@/components/account/password-form";
import { ProfileForm } from "@/components/account/profile-form";
import { LoginForm } from "@/components/auth/login-form";
import { SignupForm } from "@/components/auth/signup-form";
import { InternshipReport } from "@/components/internships/report";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

const TILES: {
  to: string;
  icon: LucideIcon;
  title: string;
  description: string;
  external?: boolean;
}[] = [
  {
    to: "/internships",
    icon: Briefcase,
    title: "Internship report",
    description: "Today's NYC startup internships: new, still open and closed.",
  },
  {
    to: "/account",
    icon: UserRound,
    title: "Account",
    description: "Change your username, name or password.",
  },
  {
    to: `${API_URL}/docs`,
    icon: BookOpen,
    title: "API reference",
    description: "Every endpoint, with a console to try them.",
    external: true,
  },
];

export function HomePage() {
  useTitle();
  const user = useUser();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Hello, {user.firstName}!</h1>
        <p className="text-muted-foreground">
          You&apos;re signed in as @{user.username}.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map(({ to, icon: Icon, title, description, external }) => {
          const card = (
            <Card className="h-full transition-colors hover:bg-muted">
              <CardHeader>
                <Icon className="mb-2 size-5 text-muted-foreground" />
                <CardTitle>{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
            </Card>
          );
          const className =
            "rounded-[min(var(--radius-4xl),24px)] outline-none focus-visible:ring-3 focus-visible:ring-ring/30";
          return external ? (
            <a key={to} href={to} className={className}>
              {card}
            </a>
          ) : (
            <Link key={to} to={to} className={className}>
              {card}
            </Link>
          );
        })}
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
