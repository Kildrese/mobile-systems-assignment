// A daily internship report: the latest, or one run's. Read-only: the tracker runs
// on a schedule (.github/workflows/tracker.yml), never from the app.
import { useQuery } from "@tanstack/react-query";
import { Download, ExternalLink, FileSearch } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import {
  getInternshipRunOptions,
  getLatestInternshipReportOptions,
} from "@/api/@tanstack/react-query.gen";
import { exportInternshipReport } from "@/api/sdk.gen";
import type { InternshipOffer, TrackerRun } from "@/api/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatRunTime } from "@/lib/run-id";
import { webUrl } from "@/lib/web-url";

const NO_PREVIOUS = "No earlier run to compare with yet.";

const SECTIONS: {
  key: InternshipOffer["section"];
  title: string;
  empty: string;
  comparesRuns?: boolean;
}[] = [
  {
    key: "new",
    title: "New since last run",
    empty: "Nothing new in this run.",
  },
  {
    key: "top_k",
    title: "Still in top K",
    empty: "No earlier offer is in the top K.",
    comparesRuns: true,
  },
  {
    key: "dropped",
    title: "Dropped",
    empty: "Nothing dropped out of the top K or closed in this run.",
    comparesRuns: true,
  },
  {
    key: "open",
    title: "Also open",
    empty: "No other earlier offers are still open.",
  },
];

function where(offer: InternshipOffer): string {
  const places = offer.locations.length
    ? offer.locations.join(", ")
    : "Location unknown";
  return offer.remote === "unknown" || offer.remote === "onsite"
    ? places
    : `${places} (${offer.remote})`;
}

function Offer({ offer }: { offer: InternshipOffer }) {
  const closed = offer.status === "closed";
  const href = webUrl(offer.url);
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
          {offer.rank && (
            <span className="text-muted-foreground">#{offer.rank} </span>
          )}
          {offer.title}
          {offer.topK && (
            <Badge className="ml-2 align-middle">Top pick</Badge>
          )}
          {offer.section === "top_k" && (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {offer.previousRank === null
                ? "entered the top K"
                : `was #${offer.previousRank}`}
            </span>
          )}
        </CardTitle>
        <CardDescription>
          {offer.company} · {facts.join(" · ")}
        </CardDescription>
        <CardAction>
          {closed ? (
            <Badge variant="secondary">Closed</Badge>
          ) : (
            href && (
              <Button asChild size="sm">
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`Apply to ${offer.title} at ${offer.company} (opens in a new tab)`}
                >
                  Apply
                  <ExternalLink data-icon="inline-end" />
                </a>
              </Button>
            )
          )}
        </CardAction>
      </CardHeader>
      {(offer.summary ||
        offer.fitScore !== null ||
        offer.workAuthorizationQuote ||
        offer.dropReason ||
        !offer.verified) && (
        <CardContent className="flex flex-col gap-2">
          {offer.summary && <p>{offer.summary}</p>}
          {offer.fitScore !== null && (
            <p>
              <span className="font-medium">Fit {offer.fitScore}/3</span>
              {offer.fitReason && (
                <span className="text-muted-foreground">
                  {" "}
                  · {offer.fitReason}
                </span>
              )}
            </p>
          )}
          {offer.workAuthorizationQuote && (
            <p className="text-muted-foreground">
              Work authorization (quoted): “{offer.workAuthorizationQuote}”
            </p>
          )}
          {offer.dropReason === "closed" && (
            <p className="text-muted-foreground">
              Closed{offer.statusEvidence && `: ${offer.statusEvidence}`}
            </p>
          )}
          {offer.dropReason === "outranked" && (
            <p className="text-muted-foreground">
              Outranked, now #{offer.rank}
            </p>
          )}
          {!closed && !offer.verified && (
            <p className="text-muted-foreground">
              Could not be checked in this run.
            </p>
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

const STATUS_VARIANTS = {
  complete: "secondary",
  partial: "outline",
  failed: "destructive",
} as const;

// "Partial", with why the run stopped as a tooltip.
export function RunStatus({ run }: { run: Pick<TrackerRun, "status" | "stopReason"> }) {
  return (
    <Badge
      variant={STATUS_VARIANTS[run.status]}
      title={run.stopReason ? `Stopped: ${run.stopReason}` : undefined}
    >
      {run.status[0].toUpperCase() + run.status.slice(1)}
    </Badge>
  );
}

// The latest report, or the report of run `runId`.
export function InternshipReport({ runId }: { runId?: string }) {
  const latest = useQuery({
    ...getLatestInternshipReportOptions(),
    enabled: !runId,
  });
  const one = useQuery({
    ...getInternshipRunOptions({ path: { id: runId ?? "" } }),
    enabled: !!runId,
  });
  const query = runId ? one : latest;

  if (query.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (query.isError)
    return (
      <Alert variant="destructive">
        <AlertTitle>The report couldn&apos;t be loaded.</AlertTitle>
        <AlertDescription>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void query.refetch()}
          >
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

  // ponytail: inferred, the API has no "last run" field. Every offer listed after a first
  // run but a new one was ranked last run; add the field if this misleads.
  const firstRun = offers.every((o) => o.previousRank === null);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border px-4 py-3">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">
            {runId ? "Started" : "Updated"} {formatRunTime(new Date(run.startedAt))}
          </span>
          <RunStatus run={run} />
          {run.stopReason && (
            <span className="text-muted-foreground">stopped at {run.stopReason}</span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!runId && (
            <Button asChild variant="ghost" size="sm">
              <Link to={`/internships/runs/${encodeURIComponent(run.id)}?tab=articles`}>
                <FileSearch data-icon="inline-start" />
                Articles
              </Link>
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="cursor-pointer"
            onClick={() => void downloadReport(run.id)}
          >
            <Download data-icon="inline-start" />
            Export
          </Button>
        </div>
      </div>
      {SECTIONS.map(({ key, title, empty, comparesRuns }) => {
        const list = offers.filter((o) => o.section === key);
        return (
          <section key={key} className="flex flex-col gap-3">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              {title}
              <Badge variant="secondary">{list.length}</Badge>
            </h2>
            {list.length === 0 ? (
              <p className="text-muted-foreground">
                {comparesRuns && firstRun ? NO_PREVIOUS : empty}
              </p>
            ) : (
              list.map((o) => <Offer key={o.opportunityId} offer={o} />)
            )}
          </section>
        );
      })}
    </div>
  );
}
