import { createApiError } from "../api/apiError";

// A plain <a href> / window.open navigation can't carry the Bearer token that the global fetch
// interceptor injects (main.tsx), so any auth-gated endpoint (the CSV exports, the QC document) 401s
// when opened as a link. Fetch it instead — the interceptor adds Authorization — then save the blob.
export async function downloadAuthedFile(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw await createApiError(response, "Nie udało się pobrać pliku");
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}
