export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`API request failed (${status})`);
  }
}

let expectedOrganisation: string | undefined;

export function setSessionOrganisation(organisationId?: string) {
  expectedOrganisation = organisationId;
}

export async function fetchApi(
  path: string,
  options?: RequestInit,
): Promise<Response> {
  const headers = new Headers(options?.headers);
  if (expectedOrganisation && path !== "auth/me" && path !== "auth/login") {
    headers.set("X-DataSleuth-Organisation", expectedOrganisation);
  }
  const response = await fetch(`/api/v1/${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) throw new ApiError(response.status);
  return response;
}

export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const headers = new Headers(options?.headers);
  if (expectedOrganisation && path !== "auth/me" && path !== "auth/login") {
    headers.set("X-DataSleuth-Organisation", expectedOrganisation);
  }
  const response = await fetchApi(path, options);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function jsonRequest(
  method: "POST" | "PATCH",
  body: object,
): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}
