// Saves a blob the client fetched (with the bearer header) as a file. The object URL is
// revoked a moment later: revoking it right after `click()` can cancel the download in
// Firefox and Safari.
export const REVOKE_AFTER_MS = 1000;

export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
}
