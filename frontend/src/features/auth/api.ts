import { jsonRequest, request } from "../../lib/api";

export { ApiError as AuthError } from "../../lib/api";

export type Account = {
  id: string;
  username: string;
  role: "admin" | "analyst" | "viewer";
};

export const auth = {
  current: () => request<Account>("auth/me"),
  login: (username: string, password: string) =>
    request<Account>("auth/login", jsonRequest("POST", { username, password })),
  logout: () => request<void>("auth/logout", { method: "POST" }),
  users: () => request<Account[]>("auth/users"),
};
