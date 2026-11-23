// The admin site's API client (app/api/admin.py). The browser's own login prompt handles the
// admin password: nginx (and the API) answer 401 with a Basic challenge until it is given.

import type { TurnOut } from "../lib/types";

export class AdminError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  // the page's origin, never its full address: an address with user:password@ in it makes fetch refuse
  const url = typeof window === "undefined" ? path : new URL(path, window.location.origin).toString();
  const res = await fetch(url, { credentials: "same-origin", ...init });
  if (!res.ok) {
    let detail = "";
    try {
      const j = await res.json();
      detail = typeof j?.detail === "string" ? j.detail : "";
    } catch {
      /* not JSON */
    }
    throw new AdminError(res.status, detail || `Lỗi máy chủ (${res.status}).`);
  }
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export interface Range {
  since: string | null; // YYYY-MM-DD, Vietnam days
  until: string | null;
}

export function rangeQuery(r: Range, extra: Record<string, string | number | null | undefined> = {}): string {
  const p = new URLSearchParams();
  if (r.since) p.set("since", r.since);
  if (r.until) p.set("until", r.until);
  for (const [k, v] of Object.entries(extra)) if (v !== null && v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface DayRow {
  day: string;
  questions: number;
  rules: number;
  rag: number;
  rag_cache: number;
  fallback: number;
  not_decided: number;
  error: number;
  cost_usd: number;
}

export interface Spend {
  spent: number | null;
  limit: number | null;
  loaded: boolean;
}

export interface Overview {
  questions: number;
  conversations: number;
  accounts: number;
  photos: number;
  routes: Record<string, number>;
  verdicts: Record<string, number>;
  feedback: { rated: number; up: number; down: number; up_share: number | null; corrected: number };
  seconds: {
    n: number; p50: number | null; p90: number | null; p95: number | null;
    first_on_photo_p50: number | null; first_on_photo_n: number;
    seen_before_p50: number | null; seen_before_n: number;
    buckets: number[]; histogram: number[];
  };
  cost_usd: { total: number; per_answer: number | null };
  per_day: DayRow[];
  spend: Spend;
}

export interface TurnSummary {
  turn_id: string;
  session_id: string;
  created_at: string;
  account: string | null;
  question: string;
  image_sha256: string;
  status: string;
  verdict: string | null;
  route: string;
  answer: string | null;
  seconds: number | null;
  cost_usd: number | null;
  error: string | null;
  thumb: "up" | "down" | null;
  corrected_answer: string | null;
  note: string | null;
}

export interface Page<T> {
  total: number;
  items: T[];
}

export interface Live {
  answer_fallback: "off" | "claude" | "rag";
  rag_url: string;
  rag_cache: boolean;
  spend_limit: number | null;
}

export interface SettingsView {
  live: Live;
  defaults: Live;
  overridden: string[];
  fixed: { answer_slots: number; profile: string };
  rag: { url: string; reachable: boolean; detail: string };
  rag_cache_entries: number | null;
  spend: Spend;
}

export interface Account {
  name: string;
  enabled: boolean;
  note: string | null;
  created_at: string;
  password_set_at: string;
  questions: number;
  last_question_at: string | null;
}

export interface Accounts {
  enabled: boolean;
  shared_account: string | null;
  items: Account[];
}

export const admin = {
  overview: (r: Range) => call<Overview>(`/v1/admin/overview${rangeQuery(r)}`),
  turns: (r: Range, f: Record<string, string | number | null>) => call<Page<TurnSummary>>(`/v1/admin/turns${rangeQuery(r, f)}`),
  feedback: (r: Range) => call<Page<TurnSummary>>(`/v1/admin/feedback${rangeQuery(r)}`),
  turn: (id: string) => call<TurnOut>(`/v1/turns/${encodeURIComponent(id)}`),
  settings: () => call<SettingsView>("/v1/admin/settings"),
  saveSettings: (s: Partial<Live>) => call<SettingsView>("/v1/admin/settings", json("PUT", s)),
  resetSettings: () => call<SettingsView>("/v1/admin/settings/reset", json("POST")),
  clearRagCache: () => call<{ removed: number }>("/v1/admin/rag-cache/clear", json("POST")),
  accounts: () => call<Accounts>("/v1/admin/accounts"),
  createAccount: (name: string, note: string | null) =>
    call<{ name: string; password: string }>("/v1/admin/accounts", json("POST", { name, note })),
  resetPassword: (name: string) =>
    call<{ name: string; password: string }>(`/v1/admin/accounts/${encodeURIComponent(name)}/reset`, json("POST")),
  setEnabled: (name: string, enabled: boolean) =>
    call<Account>(`/v1/admin/accounts/${encodeURIComponent(name)}`, json("PATCH", { enabled })),
};
