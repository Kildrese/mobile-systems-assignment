// What a query shows until it has data: a loading line, or an error with a retry.
//   if (!query.isSuccess) return <QueryFallback query={query} what="report" />;
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

export function QueryFallback({
  query,
  what,
}: {
  query: { isError: boolean; refetch: () => unknown };
  what: string;
}) {
  if (!query.isError) return <p className="text-muted-foreground">Loading…</p>;
  return (
    <Alert variant="destructive">
      <AlertTitle>The {what} couldn&apos;t be loaded.</AlertTitle>
      <AlertDescription>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          Try again
        </Button>
      </AlertDescription>
    </Alert>
  );
}
