// Run history and the documents each run tried to read. Titles, URLs and reasons came
// from the web: they are rendered as text, and a URL is a link only when it is http(s).
import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState, type ComponentProps } from "react";
import { Link } from "react-router";
import {
  listInternshipRunArticlesOptions,
  listInternshipRunsOptions,
} from "@/api/@tanstack/react-query.gen";
import type { TrackerArticle, TrackerRunSummary } from "@/api/types.gen";
import { QueryFallback } from "@/components/query-fallback";
import { RunStatus } from "@/components/internships/report";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatRunTime } from "@/lib/run-id";
import { webUrl } from "@/lib/web-url";

type Status = TrackerArticle["status"];
type BadgeVariant = ComponentProps<typeof Badge>["variant"];

// In display order.
const SECTION_LABELS: Record<string, string> = {
  new: "new",
  top_k: "still in top K",
  dropped: "dropped",
  open: "also open",
};

const STATUS: Record<Status, { label: string; variant: BadgeVariant }> = {
  fetched: { label: "Fetched", variant: "secondary" },
  skipped: { label: "Already seen", variant: "outline" },
  rejected: { label: "Rejected by guardrail", variant: "destructive" },
  failed: { label: "Failed", variant: "destructive" },
};

// "3 new · 2 dropped" for the labels with a count, or `empty`.
function summarize(counts: Record<string, number>, labels: Record<string, string>, empty: string) {
  const parts = Object.entries(labels)
    .filter(([key]) => counts[key])
    .map(([key, label]) => `${counts[key]} ${label}`);
  return parts.length ? parts.join(" · ") : empty;
}

const ARTICLE_LABELS = Object.fromEntries(
  Object.entries(STATUS).map(([key, { label }]) => [key, label.toLowerCase()]),
);

function RunCard({ run, latest }: { run: TrackerRunSummary; latest: boolean }) {
  return (
    <Link
      to={`/internships/runs/${encodeURIComponent(run.id)}`}
      className="group block rounded-[min(var(--radius-4xl),24px)] outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
    >
      <Card size="sm" className="px-4 transition-colors group-hover:bg-muted">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{formatRunTime(new Date(run.startedAt))}</span>
              <RunStatus status={run.status} />
              {latest && <Badge variant="outline">Latest</Badge>}
            </div>
            <p className="text-muted-foreground">
              {summarize(run.sections, SECTION_LABELS, "No offers reported")}
              {run.stopReason && ` · stopped at ${run.stopReason}`}
            </p>
            <p className="text-muted-foreground">
              {summarize(run.articles, ARTICLE_LABELS, "No articles recorded")}
            </p>
          </div>
          <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        </div>
      </Card>
    </Link>
  );
}

export function RunHistory() {
  const query = useQuery(listInternshipRunsOptions());
  if (!query.isSuccess) return <QueryFallback query={query} what="run history" />;

  const { runs } = query.data;
  if (runs.length === 0)
    return (
      <p className="text-muted-foreground">
        No runs yet. The tracker runs every morning; check back tomorrow.
      </p>
    );
  return (
    <ol className="flex flex-col gap-3">
      {runs.map((run, i) => (
        <li key={run.id}>
          <RunCard run={run} latest={i === 0} />
        </li>
      ))}
    </ol>
  );
}

function host(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

function ArticleUrl({ url }: { url: string }) {
  const href = webUrl(url);
  const text = <span className="break-all">{url}</span>;
  return href ? (
    <a href={href} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">
      {text}
    </a>
  ) : (
    text
  );
}

function Article({ article }: { article: TrackerArticle }) {
  const { label, variant } = STATUS[article.status];
  return (
    <li className="flex flex-col gap-1 border-b py-3 last:border-b-0 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="font-medium break-words">
          {article.title || host(article.url) || "Not fetched"}
        </span>
        <span className="text-xs text-muted-foreground">
          <ArticleUrl url={article.url} />
        </span>
        <span className="text-xs text-muted-foreground">
          {article.kind} · {article.stage} ·{" "}
          {new Date(article.fetchedAt).toLocaleTimeString(undefined, { timeStyle: "short" })}
        </span>
      </div>
      <div className="flex shrink-0 flex-col gap-1 sm:items-end">
        <Badge variant={variant}>{label}</Badge>
        {article.reason && <span className="text-xs text-muted-foreground">{article.reason}</span>}
      </div>
    </li>
  );
}

export function RunArticles({ runId }: { runId: string }) {
  const query = useQuery(listInternshipRunArticlesOptions({ path: { id: runId } }));
  const [shown, setShown] = useState<Status | "all">("all");
  if (!query.isSuccess) return <QueryFallback query={query} what="articles" />;

  const { articles } = query.data;
  if (articles.length === 0)
    return <p className="text-muted-foreground">No articles were recorded for this run.</p>;

  const count = (status: Status) => articles.filter((a) => a.status === status).length;
  const filters = [
    { key: "all" as const, label: "All", n: articles.length },
    ...(Object.keys(STATUS) as Status[])
      .map((key) => ({ key, label: STATUS[key].label, n: count(key) }))
      .filter(({ n }) => n > 0),
  ];
  const list = shown === "all" ? articles : articles.filter((a) => a.status === shown);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
        {filters.map(({ key, label, n }) => (
          <Button
            key={key}
            size="sm"
            variant={shown === key ? "default" : "outline"}
            aria-pressed={shown === key}
            className="cursor-pointer"
            onClick={() => setShown(key)}
          >
            {label}
            <span className="opacity-70">{n}</span>
          </Button>
        ))}
      </div>
      <Card size="sm" className="px-4 py-0">
        <ul>
          {list.map((article, i) => (
            <Article key={i} article={article} />
          ))}
        </ul>
      </Card>
    </div>
  );
}
