// The session token, kept in localStorage so it survives reloads and is sent
// as a bearer header (never as a cookie). Anything that can run script on
// this origin can read it; the CSP and React's escaping are the defence.
const KEY = "token";

type Listener = () => void;
const listeners = new Set<Listener>();

export function getToken(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(KEY, token);
    else localStorage.removeItem(KEY);
  } catch {
    // Storage unavailable (e.g. blocked): the user just won't stay signed in.
  }
  listeners.forEach((listener) => listener());
}

// For useSyncExternalStore. Also follows other tabs signing in or out.
export function subscribeToken(listener: Listener): () => void {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY || event.key === null) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}
