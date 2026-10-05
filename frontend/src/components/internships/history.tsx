// Run history and the documents each run tried to read. Titles, URLs and reasons came
// from the web: they are rendered as text, and a URL is a link only when it is http(s).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";
import {
  listInternshipRunArticlesOptions,
  listInternshipRunsOptions,
} from "@/api/@tanstack/react-query.gen";
import type { TrackerArticle } from "@/api/types.gen";
import { RunStatus } from "@/components/internships/report";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { formatRunTime } from "@/lib/run-id";
import { webUrl } from "@/lib/web-url";

const SECTIONS: [string, string][] = [
  ["new", "new"],
  ["top_k", "still in top K"],
  ["dropped", "dropped"],
  ["open", "also open"],
];

type Status = TrackerArticle["status"];

const STATUSES: {
  key: Status;
  label: string;
  variant: "default" | "secondary" | "destructive" | "outline";
}[] = [
  { key: "fetched", label: "Fetched", variant: "secondary" },
  { key: "skipped", label: "Already seen", variant: "outline" },
  { key: "rejected", label: "Rejected by guardrail", variant: "destructive" },
  { key: "failed", label: "Failed", variant: "destructive" },
];

const STATUS = Object.fromEntries(STATUSES.map((s) => [s.key, s])) as Record<
  Status,
  (typeof STATUSES)[number]
>;

function Loaded<T, E>({
  query,
  what,
  children,
}: {
  query: UseQueryResult<T, E>;
  what: string;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <p className="text-muted-foreground">Loading…</p>;
  if (query.isError)
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
  return children(query.data);
}

export function RunHistory() {
  const query = useQuery(listInternshipRunsOptions());
  return (
    <Loaded query={query} what="run history">
      {({ runs }) =>
        runs.length === 0 ? (
          <p className="text-muted-foreground">
            No runs yet. The tracker runs every morning; check back tomorrow.
          </p>
        ) : (
          <ol className="flex flex-col gap-3">
            {runs.map((run, i) => {
              const changes = SECTIONS.filter(([key]) => run.sections[key]);
              const read = STATUSES.filter(({ key }) => run.articles[key]);
              return (
                <li key={run.id}>
                  <Link
                    to={`/internships/runs/${encodeURIComponent(run.id)}`}
                    className="group block rounded-[min(var(--radius-4xl),24px)] outline-none focus-visible:ring-3 focus-visible:ring-ring/30"
                  >
                    <Card size="sm" className="px-4 transition-colors group-hover:bg-muted">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 flex-col gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">
                              {formatRunTime(new Date(run.startedAt))}
                            </span>
                            <RunStatus run={run} />
                            {i === 0 && <Badge variant="outline">Latest</Badge>}
                          </div>
                          <p className="text-muted-foreground">
                            {changes.length
                              ? changes
                                  .map(([key, label]) => `${run.sections[key]} ${label}`)
                                  .join(" · ")
                              : "No offers reported"}
                          </p>
                          <p className="text-muted-foreground">
                            {read.length
                              ? read
                                  .map(
                                    ({ key, label }) =>
                                      `${run.articles[key]} ${label.toLowerCase()}`,
                                  )
                                  .join(" · ")
                              : "No articles recorded"}
                          </p>
                        </div>
                        <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                      </div>
                    </Card>
                  </Link>
                </li>
              );
            })}
          </ol>
        )
      }
    </Loaded>
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
  const status = STATUS[article.status];
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
        <Badge variant={status.variant}>{status.label}</Badge>
        {article.reason && <span className="text-xs text-muted-foreground">{article.reason}</span>}
      </div>
    </li>
  );
}

export function RunArticles({ runId }: { runId: string }) {
  const query = useQuery(listInternshipRunArticlesOptions({ path: { id: runId } }));
  const [shown, setShown] = useState<Status | "all">("all");
  return (
    <Loaded query={query} what="articles">
      {({ articles }) => {
        if (articles.length === 0)
          return <p className="text-muted-foreground">No articles were recorded for this run.</p>;
        const count = (key: Status) => articles.filter((a) => a.status === key).length;
        const filters = [
          { key: "all" as const, label: "All", n: articles.length },
          ...STATUSES.map(({ key, label }) => ({ key, label, n: count(key) })).filter((f) => f.n),
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
                {list.map((a, i) => (
                  <Article key={i} article={a} />
                ))}
              </ul>
            </Card>
          </div>
        );
      }}
    </Loaded>
  );
}
