import Link from "next/link";
import { Button } from "@/components/ui/button";
import { requireSession } from "@/lib/session";

export default async function HomePage() {
  // Layouts don't re-run on client navigation, so every page checks too.
  const { user } = await requireSession();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Hello, {user.firstName}!</h1>
      <p className="text-muted-foreground">
        You&apos;re signed in as @{user.username} ({user.email}).
      </p>
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link href="/account">Manage your account</Link>
        </Button>
        <Button asChild variant="outline">
          <a href="/docs">API reference</a>
        </Button>
      </div>
    </div>
  );
}
