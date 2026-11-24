// Formatting and date helpers for the admin site (pure; tested in format.test.ts).

import type { Range } from "./api";

export const ROUTE: Record<string, string> = {
  rules: "Hệ luật",
  rag: "RAG",
  rag_cache: "RAG (bộ nhớ đệm)",
  fallback: "Dự phòng Claude",
  not_decided: "Chưa quyết định",
  error: "Lỗi",
  running: "Đang trả lời",
};

/** Route colours: chart series and badges use the same ones. */
export const ROUTE_COLOR: Record<string, string> = {
  rules: "var(--accent)",
  rag: "var(--rag)",
  rag_cache: "var(--rag-border)",
  fallback: "var(--medium)",
  not_decided: "var(--muted)",
  error: "var(--bad)",
  running: "var(--border)",
};

export const ROUTE_ORDER = ["rules", "rag", "rag_cache", "fallback", "not_decided", "error"];

/** YYYY-MM-DD of a moment, in Vietnam time (UTC+7), whatever the browser's zone. */
export function vnDay(d: Date): string {
  return new Date(d.getTime() + 7 * 3600_000).toISOString().slice(0, 10);
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export type Preset = "today" | "7d" | "30d" | "all";

export function presetRange(p: Preset, now: Date = new Date()): Range {
  const today = vnDay(now);
  switch (p) {
    case "today":
      return { since: today, until: today };
    case "7d":
      return { since: addDays(today, -6), until: today };
    case "30d":
      return { since: addDays(today, -29), until: today };
    case "all":
      return { since: null, until: null };
  }
}

/** Every day from `since` to `until`, so a chart shows quiet days as zero. Capped at 120 days. */
export function daysBetween(since: string, until: string): string[] {
  const out: string[] = [];
  for (let d = since; d <= until && out.length < 120; d = addDays(d, 1)) out.push(d);
  return out;
}

export const fmtInt = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("vi-VN"));
export const fmtPct = (x: number | null | undefined) => (x == null ? "–" : `${Math.round(x * 100)}%`);
export const fmtSec = (x: number | null | undefined) => (x == null ? "–" : `${x.toFixed(1)} s`);
export const fmtUsd = (x: number | null | undefined, digits = 2) => (x == null ? "–" : `$${x.toFixed(digits)}`);

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  const v = new Date(d.getTime() + 7 * 3600_000).toISOString();
  return `${v.slice(8, 10)}/${v.slice(5, 7)} ${v.slice(11, 16)}`;
}

/** A tidy upper bound for a chart axis: 1, 2 or 5 times a power of ten, at least `max`. */
export function niceMax(max: number): number {
  if (max <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(max));
  for (const m of [1, 2, 5, 10]) if (m * p >= max) return m * p;
  return 10 * p;
}

/** An axis number: whole above 10, else at most three significant digits ("0.02", "2.5"). */
export function fmtAxis(v: number): string {
  if (v === 0) return "0";
  if (Math.abs(v) >= 10) return String(Math.round(v));
  return String(Number(v.toPrecision(3)));
}

/**
 * A GPU's SSH address from what a provider shows: "ssh -p 41413 root@1.2.3.4 -L 8080:localhost:8080",
 * "root@1.2.3.4:41413", "1.2.3.4 41413" or just "1.2.3.4". null when no host can be found.
 */
export function parseSsh(text: string): { host: string; port: number | null } | null {
  const t = text.trim();
  if (!t) return null;
  const portFlag = /(?:^|\s)-p\s*(\d{1,5})(?:\s|$)/.exec(t);
  const words = t.replace(/(?:^|\s)-[LRDJiop]\s*\S+/g, " ").split(/\s+/).filter((w) => w && w !== "ssh" && !w.startsWith("-"));
  for (const w of words) {
    const m = /^(?:[^@\s]+@)?([A-Za-z0-9.-]+)(?::(\d{1,5}))?$/.exec(w);
    if (m && /[A-Za-z0-9]/.test(m[1])) {
      const port = portFlag ? Number(portFlag[1]) : m[2] ? Number(m[2]) : null;
      const next = words[words.indexOf(w) + 1];
      return { host: m[1], port: port ?? (next && /^\d{1,5}$/.test(next) ? Number(next) : null) };
    }
  }
  return null;
}

export function shorten(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}
