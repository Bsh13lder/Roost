import { apiRequest } from "./client";
import type { LinkOut, MadeOut } from "./types";

export const getMade = (botId: string) => apiRequest<MadeOut>("GET", `/api/bots/${botId}/made`);
export const getLinks = (botId: string) => apiRequest<LinkOut[]>("GET", `/api/bots/${botId}/links`);
