import { Fragment } from "react";
import { Link, matchPath, Outlet, useLocation } from "react-router";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Brand } from "@/components/layout/brand";
import { UserMenu } from "@/components/layout/user-menu";
import { Toaster } from "@/components/ui/sonner";
import { runLabel } from "@/lib/run-id";

type Crumb = { label: string; to?: string };

const INTERNSHIPS: Crumb = { label: "Internships", to: "/internships" };
const HISTORY: Crumb = { label: "Run history", to: "/internships/history" };

// The trail after Home for a page, ending with the page itself (no link).
// Null on home and unknown paths.
function trail(pathname: string): Crumb[] | null {
  const path = pathname.replace(/\/+$/, "");
  if (path === "/account") return [{ label: "Account" }];
  if (path === "/internships") return [{ label: INTERNSHIPS.label }];
  if (path === "/internships/history") return [INTERNSHIPS, { label: HISTORY.label }];
  const run = matchPath("/internships/runs/:id", path);
  if (run?.params.id) return [INTERNSHIPS, HISTORY, { label: runLabel(run.params.id) }];
  return null;
}

// Home › … › current page. Not shown on home itself.
function Breadcrumbs() {
  const crumbs = trail(useLocation().pathname);
  if (!crumbs) return null;
  return (
    <Breadcrumb className="mb-6">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink asChild>
            <Link to="/">Home</Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        {crumbs.map(({ label, to }) => (
          <Fragment key={label}>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              {to ? (
                <BreadcrumbLink asChild>
                  <Link to={to}>{label}</Link>
                </BreadcrumbLink>
              ) : (
                <BreadcrumbPage>{label}</BreadcrumbPage>
              )}
            </BreadcrumbItem>
          </Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

// Every signed-in page.
export function AppLayout() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-4xl items-center justify-between px-4">
          <Brand />
          <UserMenu />
        </div>
      </header>
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">
        <Breadcrumbs />
        <Outlet />
      </main>
      <Toaster />
    </div>
  );
}

// The signed-out pages (/login, /register).
export function PublicLayout() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Brand className="self-center" />
        <Outlet />
      </div>
    </div>
  );
}
