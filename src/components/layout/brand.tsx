import { GalleryVerticalEndIcon } from "lucide-react";
import Link from "next/link";
import { APP_NAME } from "@/lib/app";
import { cn } from "@/lib/utils";

// The app's logo and name, linking home.
export function Brand({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("flex items-center gap-2 font-medium", className)}>
      <div className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
        <GalleryVerticalEndIcon className="size-4" />
      </div>
      {APP_NAME}
    </Link>
  );
}
