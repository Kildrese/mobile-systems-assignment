// Run history and the documents each run tried to read. Titles, URLs and reasons came
// from the web: they are rendered as text, and a URL is a link only when it is http(s).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import {
  listInternshipRunArticlesOptions,
  listInternshipRunsOptions,
} from "@/api/@tanstack/react-query.gen";
import type { TrackerArticle } from "@/api/types.gen";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { webUrl } from "@/lib/web-url";

const SECTION_NAMES: Record<string, string> = {
  new: "new",
  top_k: "still in top K",
  dropped: "dropped",
  open: "still open",
};

const STATUS_NAMES: Record<TrackerArticle["status"], string> = {
  fetched: "fetched",
  skipped: "skipped (already seen)",
  rejected: "rejected by guardrail",
  failed: "failed",
};

const STATUS_STYLES: Record<TrackerArticle["status"], string> = {
  fetched: "bg-primary text-primary-foreground",
  skipped: "bg-muted text-muted-foreground",
  rejected: "bg-destructive/10 text-destructive",
  failed: "bg-destructive/10 text-destructive",
};

function counts(values: Record<string, number>, names: Record<string, string>): string {
  const parts = Object.entries(values).map(([key, n]) => `${n} ${names[key] ?? key}`);
  return parts.length ? parts.join(", ") : "none";
}

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
          <p className="text-muted-foreground">No runs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-4 font-medium">Run</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 font-medium">What changed</th>
                  <th className="py-2 font-medium">Articles</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b align-top">
                    <td className="py-2 pr-4">
                      <Link
                        to={`/internships/runs/${encodeURIComponent(run.id)}`}
                        className="underline-offset-4 hover:underline"
                      >
                        {new Date(run.startedAt).toLocaleString()}
                      </Link>
                    </td>
                    <td className="py-2 pr-4">
                      {run.status}
                      {run.stopReason && (
                        <span className="block text-muted-foreground">{run.stopReason}</span>
                      )}
                    </td>
                    <td className="py-2 pr-4">{counts(run.sections, SECTION_NAMES)}</td>
                    <td className="py-2">{counts(run.articles, STATUS_NAMES)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </Loaded>
  );
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

export function RunArticles({ runId }: { runId: string }) {
  const query = useQuery(listInternshipRunArticlesOptions({ path: { id: runId } }));
  return (
    <Loaded query={query} what="articles">
      {({ articles }) =>
        articles.length === 0 ? (
          <p className="text-muted-foreground">No articles were recorded for this run.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-4 font-medium">Title and URL</th>
                  <th className="py-2 pr-4 font-medium">Kind</th>
                  <th className="py-2 pr-4 font-medium">Fetched</th>
                  <th className="py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {articles.map((a, i) => (
                  <tr key={i} className="border-b align-top">
                    <td className="py-2 pr-4">
                      {a.title && <span className="block">{a.title}</span>}
                      <span className="block text-muted-foreground">
                        <ArticleUrl url={a.url} />
                      </span>
                    </td>
                    <td className="py-2 pr-4">
                      {a.kind}
                      <span className="block text-muted-foreground">{a.stage}</span>
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap">
                      {new Date(a.fetchedAt).toLocaleTimeString()}
                    </td>
                    <td className="py-2">
                      <span
                        className={cn(
                          "rounded-md px-1.5 py-0.5 text-xs whitespace-nowrap",
                          STATUS_STYLES[a.status],
                        )}
                      >
                        {STATUS_NAMES[a.status]}
                      </span>
                      {a.reason && <span className="block text-muted-foreground">{a.reason}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      }
    </Loaded>
  );
}
