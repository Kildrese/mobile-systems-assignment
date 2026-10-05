// `value` if it is an absolute http(s) URL, else null. URLs from the tracker came from
// the web, and a rejected one can be `javascript:` or `data:`: only these may be links.
export function webUrl(value: string): string | null {
  try {
    const { protocol } = new URL(value);
    return protocol === "http:" || protocol === "https:" ? value : null;
  } catch {
    return null;
  }
}
