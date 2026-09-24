// Layout for the signed-out pages (`/login`, `/register`). `(public)` is a
// route group: the folder name isn't part of the URL.
import { Brand } from "@/components/layout/brand";

export default function PublicLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted p-6 md:p-10">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Brand className="self-center" />
        {children}
      </div>
    </div>
  );
}
