// Typed client for the CI API. The browser calls same-origin /api/v1/*; next.config.ts forwards it to the API.
import useSWR, { type SWRConfiguration } from "swr";
import { isStale, pickRecord } from "@/lib/record";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

export function path(p: string, q?: Query): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(q ?? {})) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.append(k, String(v));
  }
  const s = sp.toString();
  return `/api/v1${p}${s ? `?${s}` : ""}`;
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "network", "The CI API is not reachable. Is it running?");
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    // a proxy error page or a non-JSON reply
  }
  if (!res.ok) {
    const e = (body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)?.error;
    throw new ApiError(
      res.status,
      e?.code ?? (res.status >= 500 ? "server_error" : "http_error"),
      e?.message ?? (res.status >= 500 ? "The CI API is not reachable or failed." : `Request failed (${res.status}).`),
      e?.details ?? {},
    );
  }
  return body as T;
}

export const get = <T>(url: string) => request<T>(url);

export function send<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", url: string, body?: unknown, version?: number) {
  return request<T>(url, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: version === undefined ? undefined : { "If-Match": String(version) },
  });
}

/** SWR on a GET path; pass null to skip. */
export function useApi<T>(url: string | null, opts?: SWRConfiguration<T, ApiError>) {
  return useSWR<T, ApiError>(url, get<T>, { revalidateOnFocus: false, keepPreviousData: true, ...opts });
}

/** SWR for one record by id: no keepPreviousData, and the data only when its id equals the requested id
 *  (lib/record.ts). A failed load returns the error with no data, so the previous record is never shown. */
export function useRecord<T>(url: string | null, requested: string | null | undefined, idOf: (d: T) => string | null | undefined,
  opts?: SWRConfiguration<T, ApiError>) {
  const q = useSWR<T, ApiError>(url, get<T>, { revalidateOnFocus: false, ...opts, keepPreviousData: false });
  const data = pickRecord(requested, q.data, idOf);
  return { data, error: q.error, isLoading: q.isLoading || (!data && !q.error && Boolean(url)), mutate: q.mutate, stale: isStale(requested, q.data, idOf) };
}
