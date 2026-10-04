// The latest daily internship report. Read-only: the tracker runs on a schedule
// (.github/workflows/tracker.yml), never from the app.
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { getLatestInternshipReportOptions } from "@/api/@tanstack/react-query.gen";
import { exportInternshipReport } from "@/api/sdk.gen";
import type { InternshipOffer } from "@/api/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const SECTIONS: { key: InternshipOffer["section"]; title: string; empty: string }[] = [
  { key: "new", title: "New since last run", empty: "Nothing new in this run." },
  { key: "open", title: "Still open", empty: "No earlier offers are still open." },
  { key: "closed", title: "Closed since last run", empty: "Nothing closed in this run." },
];

function where(offer: InternshipOffer): string {
  const places = offer.locations.length ? offer.locations.join(", ") : "Location unknown";
  return offer.remote === "unknown" || offer.remote === "onsite"
    ? places
    : `${places} (${offer.remote})`;
}

function Offer({ offer }: { offer: InternshipOffer }) {
  const facts = [
    where(offer),
    offer.term !== "unknown" && offer.term,
    offer.compensation,
    offer.deadline && `Apply by ${offer.deadline}`,
  ].filter(Boolean);
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>
          {offer.rank && <span className="text-muted-foreground">#{offer.rank} </span>}
          <a href={offer.url} target="_blank" rel="noreferrer" className="hover:underline">
            {offer.title}
          </a>
          {offer.topK && (
            <span className="ml-2 rounded-md bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
              Top pick
            </span>
          )}
        </CardTitle>
        <CardDescription>
          {offer.company} · {facts.join(" · ")}
        </CardDescription>
      </CardHeader>
      {(offer.summary ||
        offer.workAuthorizationQuote ||
        offer.section === "closed" ||
        !offer.verified) && (
        <CardContent className="flex flex-col gap-2">
          {offer.summary && <p>{offer.summary}</p>}
          {offer.workAuthorizationQuote && (
            <p className="text-muted-foreground">
              Work authorization (quoted): “{offer.workAuthorizationQuote}”
            </p>
          )}
          {offer.section === "closed" && offer.statusEvidence && (
            <p className="text-muted-foreground">Closed: {offer.statusEvidence}</p>
          )}
          {offer.section !== "closed" && !offer.verified && (
            <p className="text-muted-foreground">Could not be checked in this run.</p>
          )}
        </CardContent>
      )}
    </Card>
  );
}

// Fetched through the client (it needs the bearer header), then saved as a file.
async function downloadReport(runId: string) {
  const { data, error } = await exportInternshipReport({
    path: { id: runId },
    parseAs: "text",
  });
  if (error || typeof data !== "string") {
    toast.error("The report couldn't be exported.");
    return;
  }
  const url = URL.createObjectURL(new Blob([data], { type: "text/markdown" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `internships-${runId}.md`;
  link.click();
  URL.revokeObjectURL(url);
}

export function InternshipReport() {
  const query = useQuery(getLatestInternshipReportOptions());

  if (query.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (query.isError)
    return (
      <Alert variant="destructive">
        <AlertTitle>The report couldn&apos;t be loaded.</AlertTitle>
        <AlertDescription>
          <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );

  const { run, offers } = query.data;
  if (!run)
    return (
      <p className="text-muted-foreground">
        No report yet. The tracker runs every morning; check back tomorrow.
      </p>
    );

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {run.topic} · updated {new Date(run.startedAt).toLocaleString()}
          {run.status !== "complete" && ` · ${run.status} run`}
        </p>
        <Button variant="outline" size="sm" onClick={() => void downloadReport(run.id)}>
          Export .md
        </Button>
      </div>
      {SECTIONS.map(({ key, title, empty }) => {
        const list = offers.filter((o) => o.section === key);
        return (
          <section key={key} className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">
              {title} ({list.length})
            </h2>
            {list.length === 0 ? (
              <p className="text-muted-foreground">{empty}</p>
            ) : (
              list.map((o) => <Offer key={o.opportunityId} offer={o} />)
            )}
          </section>
        );
      })}
    </div>
  );
}
