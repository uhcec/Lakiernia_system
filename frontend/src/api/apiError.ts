export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export async function readApiErrorMessage(response: Response, fallbackMessage: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: string | { msg?: string }[] };

    if (typeof body.detail === "string" && body.detail.trim()) {
      return body.detail;
    }

    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const firstMessage = body.detail[0]?.msg;
      if (typeof firstMessage === "string" && firstMessage.trim()) {
        return firstMessage;
      }
    }
  } catch {
    return fallbackMessage;
  }

  return fallbackMessage;
}

export async function createApiError(response: Response, fallbackMessage: string): Promise<ApiError> {
  const message = await readApiErrorMessage(response, fallbackMessage);
  return new ApiError(response.status, message);
}
