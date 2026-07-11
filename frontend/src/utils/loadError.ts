import { isApiError } from "../api/apiError";

// CHANGES #16c: a backend-unreachable fetch rejects with the browser's raw English message
// ("Failed to fetch") — never show that to a Polish operator.
export const NETWORK_ERROR_MESSAGE_PL =
  "Brak połączenia z serwerem. Sprawdź połączenie sieciowe i spróbuj ponownie.";

/**
 * Error-to-operator-text for data loads (and any catch that used to render `error.message`
 * verbatim). An ApiError always carries a controlled Polish message (the backend's `detail`
 * or our own Polish fallback from createApiError) — surface it. A fetch rejection is a
 * browser-level TypeError with an English message — translate to the Polish network message.
 * Anything else keeps the caller's generic Polish message.
 */
export function getLoadErrorMessage(error: unknown, genericMessage: string): string {
  if (isApiError(error) && error.message.trim()) {
    return error.message;
  }
  if (error instanceof TypeError) {
    return NETWORK_ERROR_MESSAGE_PL;
  }
  return genericMessage;
}
