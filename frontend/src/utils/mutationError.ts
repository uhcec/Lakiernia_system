import { isApiError } from "../api/apiError";

export function getMutationErrorMessage(error: unknown, genericMessage: string): string {
  if (isApiError(error) && (error.status === 409 || error.status === 422)) {
    return error.message;
  }

  return genericMessage;
}