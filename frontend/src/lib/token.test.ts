import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getToken, setToken, subscribeToken } from "@/lib/token";

// The tests run without a DOM: a Map-backed localStorage and an EventTarget
// standing in for window.
function fakeStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

function storageEvent(key: string | null) {
  return Object.assign(new Event("storage"), { key });
}

let win: EventTarget;

beforeEach(() => {
  win = new EventTarget();
  vi.stubGlobal("localStorage", fakeStorage());
  vi.stubGlobal("window", win);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("token storage", () => {
  it("stores, reads and clears the token", () => {
    expect(getToken()).toBeNull();
    setToken("abc");
    expect(getToken()).toBe("abc");
    expect(localStorage.getItem("token")).toBe("abc");
    setToken(null);
    expect(getToken()).toBeNull();
  });

  it("survives blocked storage", () => {
    const throwing = () => {
      throw new Error("SecurityError");
    };
    vi.stubGlobal("localStorage", { getItem: throwing, setItem: throwing, removeItem: throwing });
    expect(getToken()).toBeNull();
    expect(() => setToken("abc")).not.toThrow();
  });
});

describe("subscribeToken", () => {
  it("notifies on changes in this tab until unsubscribed", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToken(listener);
    setToken("abc");
    setToken(null);
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    setToken("def");
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("follows other tabs changing the token or clearing storage", () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToken(listener);
    win.dispatchEvent(storageEvent("token"));
    win.dispatchEvent(storageEvent(null));
    win.dispatchEvent(storageEvent("something-else"));
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    win.dispatchEvent(storageEvent("token"));
    expect(listener).toHaveBeenCalledTimes(2);
  });
});
