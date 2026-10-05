// Web text in the articles table stays text: no markup, and no link unless http(s).
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ArticleUrl } from "@/components/internships/history";

const render = (url: string) => renderToStaticMarkup(createElement(ArticleUrl, { url }));

describe("ArticleUrl", () => {
  it("links an https URL", () => {
    expect(render("https://news.example.com/1")).toContain('href="https://news.example.com/1"');
  });

  it("shows a rejected javascript: URL as text", () => {
    const html = render("javascript:alert(1)");
    expect(html).not.toContain("<a");
    expect(html).toContain("javascript:alert(1)");
  });

  it("escapes markup", () => {
    const html = render("<img src=x onerror=alert(1)>");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
  });
});
