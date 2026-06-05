export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

type ApiRequestOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

async function readResponsePayload(response: Response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json().catch(() => null);
  }
  return response.text().catch(() => "");
}

function errorMessageFromPayload(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    const detail = record.detail || record.error || record.message;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

export async function apiRequest<T>(url: string, options: ApiRequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const { body, ...requestOptions } = options;
  const init: RequestInit = { ...requestOptions, headers };

  if (body !== undefined) {
    if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    init.body = typeof body === "string" ? body : JSON.stringify(body);
  }

  const response = await fetch(url, init);
  const payload = await readResponsePayload(response);

  if (!response.ok) {
    throw new ApiError(
      errorMessageFromPayload(payload, `HTTP ${response.status}`),
      response.status,
      payload,
    );
  }

  return payload as T;
}

export function apiGet<T>(url: string, options: Omit<ApiRequestOptions, "method" | "body"> = {}) {
  return apiRequest<T>(url, { ...options, method: "GET" });
}

export function apiPost<T>(url: string, body?: unknown, options: Omit<ApiRequestOptions, "method" | "body"> = {}) {
  return apiRequest<T>(url, { ...options, method: "POST", body });
}
