import { jsonRequest, request } from "../../lib/api";

export { ApiError as AuthError } from "../../lib/api";

export type Account = {
  id: string;
  username: string;
  role: "admin" | "analyst" | "viewer";
};

export type SessionAccount = Account & {
  organisation_id: string;
  organisation_name: string;
};

export const auth = {
  current: () => request<SessionAccount>("auth/me"),
  login: (username: string, password: string, organisationId?: string) =>
    request<SessionAccount>(
      "auth/login",
      jsonRequest("POST", {
        username,
        password,
        organisation_id: organisationId,
      }),
    ),
  logout: () => request<void>("auth/logout", { method: "POST" }),
  users: () => request<Account[]>("auth/users"),
};
