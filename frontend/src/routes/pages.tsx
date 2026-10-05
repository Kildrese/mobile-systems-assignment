import { BookOpen, Briefcase, History, UserRound, type LucideIcon } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { DeleteAccount } from "@/components/account/delete-account";
import { PasswordForm } from "@/components/account/password-form";
import { ProfileForm } from "@/components/account/profile-form";
import { LoginForm } from "@/components/auth/login-form";
import { SignupForm } from "@/components/auth/signup-form";
import { RunArticles, RunHistory } from "@/components/internships/history";
import { InternshipReport } from "@/components/internships/report";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { API_URL, APP_NAME } from "@/lib/app";
import { runLabel } from "@/lib/run-id";
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
    description: "Today's NYC startup internships, the run history and what each run read.",
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
        {TILES.map(({ to, icon: Icon, title, description, external }) => (
          <Link
            key={to}
            to={to}
            target={external ? "_blank" : undefined}
            rel="noreferrer"
            className="rounded-[min(var(--radius-4xl),24px)] outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
          >
            <Card className="h-full transition-colors hover:bg-muted">
              <CardHeader>
                <Icon className="mb-2 size-5 text-muted-foreground" />
                <CardTitle>{title}</CardTitle>
                <CardDescription>{description}</CardDescription>
              </CardHeader>
            </Card>
            {external && <span className="sr-only"> (opens in a new tab)</span>}
          </Link>
        ))}
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

function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  );
}

export function InternshipsPage() {
  useTitle("Internships");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Internships"
        description="The internship tracker's latest report, updated every morning."
        action={
          <Button asChild variant="outline" size="sm">
            <Link to="/internships/history">
              <History data-icon="inline-start" />
              Run history
            </Link>
          </Button>
        }
      />
      <InternshipReport />
    </div>
  );
}

export function InternshipHistoryPage() {
  useTitle("Run history");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Run history"
        description="Every published run, newest first: what changed and what it read."
      />
      <RunHistory />
    </div>
  );
}

export function InternshipRunPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "articles" ? "articles" : "report";
  useTitle(`Run of ${runLabel(id)}`);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={`Run of ${runLabel(id)}`}
        description="The report this run published, and every page, job board and posting it tried to read."
      />
      <Tabs
        value={tab}
        onValueChange={(value) =>
          setParams(value === "articles" ? { tab: value } : {}, { replace: true })
        }
        className="gap-6"
      >
        <TabsList>
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="articles">Articles</TabsTrigger>
        </TabsList>
        <TabsContent value="report">
          <InternshipReport runId={id} />
        </TabsContent>
        <TabsContent value="articles">
          <RunArticles runId={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
