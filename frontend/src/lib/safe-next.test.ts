import { describe, expect, it } from "vitest";
import { authHref, safeNext } from "@/lib/safe-next";

describe("safeNext", () => {
  it.each(["/", "/account", "/account?tab=password", "/account#danger", "/a/b/c"])(
    "keeps the same-site path %s",
    (value) => expect(safeNext(value)).toBe(value),
  );

  it.each([
    ["not a string", 42],
    ["null", null],
    ["undefined", undefined],
    ["empty", ""],
    ["relative path", "account"],
    ["absolute URL", "https://evil.example/"],
    ["protocol-relative URL", "//evil.example"],
    ["backslash host", "/\\evil.example"],
    ["tab trick", "/\t/evil.example"],
    ["newline trick", "/\n/evil.example"],
    ["backslash anywhere", "/account\\x"],
    ["javascript: URL", "javascript:alert(1)"],
    ["login page", "/login"],
    ["login page with a query", "/login?next=/account"],
    ["register page with a trailing slash", "/register/"],
  ])("falls back to / for %s", (_, value) => expect(safeNext(value)).toBe("/"));
});

describe("authHref", () => {
  it("leaves out the default next", () => {
    expect(authHref("/login", "/")).toBe("/login");
  });

  it("encodes next", () => {
    expect(authHref("/register", "/account?tab=a&b=c")).toBe(
      "/register?next=%2Faccount%3Ftab%3Da%26b%3Dc",
    );
  });
});
