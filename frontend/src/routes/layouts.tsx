import { Link, Outlet, useLocation } from "react-router";
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

const PAGE_NAMES: Record<string, string> = {
  "/internships": "Internships",
  "/internships/history": "Run history",
  "/account": "Account",
};

// Home › current page. Not shown on home itself.
function Breadcrumbs() {
  const name = PAGE_NAMES[useLocation().pathname];
  if (!name) return null;
  return (
    <Breadcrumb className="mb-6">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink asChild>
            <Link to="/">Home</Link>
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <BreadcrumbPage>{name}</BreadcrumbPage>
        </BreadcrumbItem>
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
