// Per-browser conveniences in localStorage: the current session and the sessions seen here.
// Storage can be missing or throw (private windows, blocked site data); nothing depends on it.

const SESSION = "vqa.session";
const SESSIONS = "vqa.sessions";
const THEME = "vqa.theme";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

export interface KnownSession {
  id: string;
  firstQuestion: string;
  at: string; // ISO time of the first turn seen
}

export const loadSessionId = () => read(SESSION);
export const saveSessionId = (id: string | null) => write(SESSION, id);

export function loadSessions(): KnownSession[] {
  try {
    const v = JSON.parse(read(SESSIONS) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => x && typeof x.id === "string") : [];
  } catch {
    return [];
  }
}

export function rememberSession(id: string, firstQuestion: string): KnownSession[] {
  const all = loadSessions();
  if (!all.some((s) => s.id === id)) {
    all.unshift({ id, firstQuestion, at: new Date().toISOString() });
    write(SESSIONS, JSON.stringify(all.slice(0, 50)));
  }
  return loadSessions();
}

export function forgetSession(id: string): KnownSession[] {
  write(SESSIONS, JSON.stringify(loadSessions().filter((s) => s.id !== id)));
  return loadSessions();
}

export type Theme = "auto" | "light" | "dark";
export const loadTheme = (): Theme => {
  const t = read(THEME);
  return t === "light" || t === "dark" ? t : "auto";
};
export const saveTheme = (t: Theme) => write(THEME, t === "auto" ? null : t);

/** Remembered on/off choices (e.g. whether a side bar is open); `fallback` when unset or unreadable. */
export function loadFlag(key: string, fallback: boolean): boolean {
  const v = read(key);
  return v === "1" ? true : v === "0" ? false : fallback;
}
export const saveFlag = (key: string, on: boolean) => write(key, on ? "1" : "0");
