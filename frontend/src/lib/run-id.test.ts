import { describe, expect, it } from "vitest";
import { runDate, runLabel } from "@/lib/run-id";

describe("runDate", () => {
  it("reads the UTC start time", () => {
    expect(runDate("20261004T173811Z-d334")?.toISOString()).toBe("2026-10-04T17:38:11.000Z");
  });

  it.each(["", "cli", "2026-10-04", "20261004T1738Z-d334"])("rejects %j", (id) =>
    expect(runDate(id)).toBeNull(),
  );
});

describe("runLabel", () => {
  it("falls back to the id", () => expect(runLabel("nope")).toBe("nope"));
});
