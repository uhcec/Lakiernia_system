import { isApiError } from "../api/apiError";

export function getMutationErrorMessage(error: unknown, genericMessage: string): string {
  // Surface the backend's controlled reason for any client error (e.g. 403 wrong-station,
  // 409 workflow conflict, 422 validation) so the operator sees *why* the action was rejected.
  // Server errors (5xx) and network failures keep the generic message — their detail isn't actionable.
  if (isApiError(error) && error.status >= 400 && error.status < 500 && error.message.trim()) {
    return error.message;
  }

  return genericMessage;
}
