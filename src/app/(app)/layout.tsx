import { GalleryVerticalEndIcon } from "lucide-react";
import Link from "next/link";
import { UserMenu } from "@/components/app/user-menu";
import { Toaster } from "@/components/ui/sonner";
import { APP_NAME } from "@/lib/app";
import { requireSession } from "@/lib/session";

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const { user } = await requireSession();

  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex h-14 w-full max-w-4xl items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2 font-medium">
            <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GalleryVerticalEndIcon className="size-4" />
            </div>
            {APP_NAME}
          </Link>
          <UserMenu firstName={user.firstName} lastName={user.lastName} email={user.email} />
        </div>
      </header>
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-8">{children}</main>
      <Toaster />
    </div>
  );
}
