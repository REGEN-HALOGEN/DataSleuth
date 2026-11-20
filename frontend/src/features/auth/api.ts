export type Account = {
  id: string;
  username: string;
  role: "admin" | "analyst" | "viewer";
};

export class AuthError extends Error {
  constructor(readonly status: number) {
    super(`Authentication request failed (${status})`);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1/auth/${path}`, {
    ...options,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) throw new AuthError(response.status);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export const auth = {
  current: () => request<Account>("me"),
  login: (username: string, password: string) =>
    request<Account>("login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<void>("logout", { method: "POST" }),
  users: () => request<Account[]>("users"),
};
