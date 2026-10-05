import { describe, expect, it } from "vitest";
import { webUrl } from "@/lib/web-url";

describe("webUrl", () => {
  it.each(["https://jobs.lever.co/acme/1", "http://example.com/a?b=c"])("keeps %s", (value) =>
    expect(webUrl(value)).toBe(value),
  );

  it.each([
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    " javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "/relative/path",
    "//example.com/",
    "not a url",
    "",
  ])("rejects %s", (value) => expect(webUrl(value)).toBeNull());
});
