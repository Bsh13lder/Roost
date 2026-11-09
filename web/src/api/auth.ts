import { apiRequest } from "./client";
import type { CurrentUser } from "./types";

export function register(username: string, password: string): Promise<CurrentUser> {
  return apiRequest<CurrentUser>("POST", "/api/auth/register", { username, password });
}

export function login(username: string, password: string): Promise<CurrentUser> {
  return apiRequest<CurrentUser>("POST", "/api/auth/login", { username, password });
}

export function logout(): Promise<void> {
  return apiRequest<void>("POST", "/api/auth/logout");
}

export function me(): Promise<CurrentUser> {
  return apiRequest<CurrentUser>("GET", "/api/auth/me");
}
