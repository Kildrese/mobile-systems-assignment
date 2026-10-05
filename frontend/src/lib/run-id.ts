// Tracker run ids start with their UTC start time: `20261004T173811Z-d334`.
const RUN_ID = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z/;

export function runDate(id: string): Date | null {
  const m = RUN_ID.exec(id);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m.map(Number);
  return new Date(Date.UTC(y, mo - 1, d, h, mi, s));
}

export function formatRunTime(date: Date): string {
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

// "Oct 4, 2026, 1:38 PM" for a run id, or the id itself if it has no time.
export function runLabel(id: string): string {
  const date = runDate(id);
  return date ? formatRunTime(date) : id;
}
