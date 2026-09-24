// Layout for every signed-in page. `(protected)` is a route group: the folder
// name isn't part of the URL, so `(protected)/account` is served at `/account`.
import { Brand } from "@/components/layout/brand";
import { UserMenu } from "@/components/layout/user-menu";
import { Toaster } from "@/components/ui/sonner";
import { requireSession } from "@/lib/session";

export default async function ProtectedLayout({ children }: LayoutProps<"/">) {
  const { user } = await requireSession();

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-4xl items-center justify-between px-4">
          <Brand />
          <UserMenu firstName={user.firstName} lastName={user.lastName} email={user.email} />
        </div>
      </header>
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">{children}</main>
      <Toaster />
    </div>
  );
}
