/**
 * The single place where the frontend talks to the API.
 *
 * - Adds the login token to every request.
 * - Turns error responses into an ApiError with the server's readable message.
 * - On 401 (expired or invalid login) it calls the registered handler, which logs the user out.
 */

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** FastAPI errors are {"detail": "text"} or, for 422, {"detail": [{loc, msg}, ...]}. */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => {
        const field = d.loc?.filter((p) => p !== "body" && p !== "query").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return status >= 500 ? "The server had a problem. Please try again." : `Request failed (${status})`;
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  });
  const qs = params.toString();
  return `${API_BASE}${path}${qs ? `?${qs}` : ""}`;
}

interface RequestOptions {
  method?: string;
  query?: Query;
  json?: unknown;
  form?: FormData | URLSearchParams;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let body: BodyInit | undefined;
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  } else if (options.form) {
    body = options.form;          // the browser sets the right Content-Type
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "Cannot reach the server. Is the API running?");
  }

  const isJson = response.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401 && authToken && onUnauthorized) onUnauthorized();
    throw new ApiError(response.status, errorMessage(data, response.status), data);
  }
  return data as T;
}

/**
 * Download a file that needs the login token (a plain link cannot send the token).
 * Fetches it, then saves it through a temporary object URL.
 */
export async function downloadFile(path: string, fallbackName: string, query?: Query): Promise<string> {
  const headers: Record<string, string> = {};
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), { headers });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the API running?");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    if (response.status === 401 && authToken && onUnauthorized) onUnauthorized();
    throw new ApiError(response.status, errorMessage(data, response.status), data);
  }
  const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return name;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => apiRequest<T>(path, { query, signal }),
  post: <T>(path: string, json?: unknown) => apiRequest<T>(path, { method: "POST", json: json ?? {} }),
  patch: <T>(path: string, json: unknown) => apiRequest<T>(path, { method: "PATCH", json }),
  put: <T>(path: string, json: unknown) => apiRequest<T>(path, { method: "PUT", json }),
  upload: <T>(path: string, form: FormData) => apiRequest<T>(path, { method: "POST", form }),
  postForm: <T>(path: string, form: URLSearchParams) => apiRequest<T>(path, { method: "POST", form }),
};
