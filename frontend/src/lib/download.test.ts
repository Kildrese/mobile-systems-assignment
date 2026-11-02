import { afterEach, describe, expect, it, vi } from "vitest";
import { REVOKE_AFTER_MS, saveFile } from "@/lib/download";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("saveFile", () => {
  it("clicks the link and revokes the URL only after the download started", () => {
    vi.useFakeTimers();
    const link = { href: "", download: "", click: vi.fn() };
    const revoke = vi.fn();
    vi.stubGlobal("document", { createElement: () => link });
    vi.stubGlobal("URL", { createObjectURL: () => "blob:1", revokeObjectURL: revoke });

    saveFile(new Blob(["x"]), "Ramp_CV.docx");

    expect(link.click).toHaveBeenCalledOnce();
    expect(link.download).toBe("Ramp_CV.docx");
    expect(revoke).not.toHaveBeenCalled();
    vi.advanceTimersByTime(REVOKE_AFTER_MS);
    expect(revoke).toHaveBeenCalledWith("blob:1");
  });
});
