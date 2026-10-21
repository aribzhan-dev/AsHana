import type { components } from "./schema";
import { identityRu as t } from "../locales/identity";

export type Staff = components["schemas"]["UserResponse"];
export type StaffSession = components["schemas"]["SessionResponse"];
export type Role = components["schemas"]["Role"];
export { ApiError } from "./http";
import { ApiError, record, strings, request } from "./http";
function staff(value: unknown): Staff {
  if (
    !record(value) ||
    typeof value.id !== "string" ||
    (value.phone !== null && typeof value.phone !== "string") ||
    typeof value.login !== "string" ||
    typeof value.name !== "string" ||
    typeof value.is_demo !== "boolean" ||
    !strings(value.permissions) ||
    !strings(value.roles) ||
    !value.roles.every((role) => Object.hasOwn(t.roleLabels, role))
  )
    throw new ApiError(0, t.genericError);
  return {
    id: value.id,
    login: value.login,
    phone: value.phone,
    name: value.name,
    is_demo: value.is_demo,
    permissions: value.permissions,
    roles: value.roles as Role[],
  };
}
function sessionList(value: unknown): StaffSession[] {
  if (!Array.isArray(value)) throw new ApiError(0, t.genericError);
  return value.map((item: unknown) => {
    if (
      !record(item) ||
      typeof item.id !== "string" ||
      typeof item.current !== "boolean" ||
      typeof item.created_at !== "string" ||
      typeof item.expires_at !== "string" ||
      !Number.isFinite(Date.parse(item.created_at)) ||
      !Number.isFinite(Date.parse(item.expires_at))
    )
      throw new ApiError(0, t.genericError);
    return {
      id: item.id,
      current: item.current,
      created_at: item.created_at,
      expires_at: item.expires_at,
    };
  });
}
export const identityApi = {
  me: () => request("/auth/me").then(staff),
  login: (login: string, password: string) =>
    request("/auth/login", "POST", { login, password }).then(staff),
  logout: async (): Promise<void> => {
    await request("/auth/logout", "POST");
  },
  sessions: () => request("/auth/sessions").then(sessionList),
  revoke: async (id: string): Promise<void> => {
    await request(`/auth/sessions/${id}`, "DELETE");
  },
  create: (data: components["schemas"]["StaffInput"]) =>
    request("/admin/users", "POST", data).then(staff),
  search: (login: string) =>
    request("/admin/users/search", "POST", { login }).then(staff),
  roles: (id: string, roles: Role[]) =>
    request(`/admin/users/${id}/roles`, "PUT", { roles }).then(staff),
};
