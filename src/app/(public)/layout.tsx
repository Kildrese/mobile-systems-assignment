// Layout for the signed-out pages (`/login`, `/register`). `(public)` is a
// route group: the folder name isn't part of the URL.
import { GalleryVerticalEndIcon } from "lucide-react";
import Link from "next/link";
import { APP_NAME } from "@/lib/app";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Link href="/" className="flex items-center gap-2 self-center font-medium">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <GalleryVerticalEndIcon className="size-4" />
          </div>
          {APP_NAME}
        </Link>
        {children}
      </div>
    </div>
  );
}
