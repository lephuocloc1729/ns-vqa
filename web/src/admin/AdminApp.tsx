import { useCallback, useEffect, useState } from "react";
import { Logo } from "../components/Icons";
import { PRODUCT } from "../lib/brand";
import { loadTheme, saveTheme, type Theme } from "../lib/storage";
import { THEME_LABEL, THEME_NEXT, ThemeIcon } from "../components/Sidebar";
import Accounts from "./Accounts";
import { AdminError, type Range } from "./api";
import { presetRange, type Preset } from "./format";
import Overview from "./Overview";
import Settings from "./Settings";
import Turns, { FeedbackInbox } from "./Turns";

const TABS = {
  overview: "Tổng quan",
  feedback: "Phản hồi",
  turns: "Câu hỏi",
  accounts: "Tài khoản",
  settings: "Cài đặt",
} as const;
type Tab = keyof typeof TABS;

const PRESETS: Record<Preset, string> = { today: "Hôm nay", "7d": "7 ngày", "30d": "30 ngày", all: "Tất cả" };

function tabFromHash(): Tab {
  const h = window.location.hash.slice(1);
  return (h in TABS ? h : "overview") as Tab;
}

export default function AdminApp() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [preset, setPreset] = useState<Preset | "custom">("7d");
  const [range, setRange] = useState<Range>(() => presetRange("7d"));
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(() => loadTheme());

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    saveTheme(theme);
  }, [theme]);

  useEffect(() => {
    const f = () => setTab(tabFromHash());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);

  const onError = useCallback((e: unknown) => {
    if (e instanceof AdminError && e.status === 401) setError("Cần đăng nhập quản trị. Tải lại trang để nhập mật khẩu.");
    else setError(e instanceof Error ? e.message : String(e));
  }, []);

  const go = (t: Tab) => {
    setError(null);
    setTab(t);
    window.history.replaceState(null, "", `#${t}`);
  };

  const showRange = tab === "overview" || tab === "turns" || tab === "feedback";

  return (
    <div className="adm">
      <header className="adm-head">
        <div className="adm-brand"><Logo size={26} /><span className="brand-name">{PRODUCT}</span><span className="adm-tag">quản trị</span></div>
        <nav className="adm-tabs" aria-label="Mục">
          {(Object.keys(TABS) as Tab[]).map((t) => (
            <button key={t} type="button" className={t === tab ? "active" : ""} aria-current={t === tab ? "page" : undefined}
              onClick={() => go(t)}>{TABS[t]}</button>
          ))}
        </nav>
        <button type="button" className="adm-icon-btn" aria-label={THEME_LABEL[theme]} title={THEME_LABEL[theme]}
          onClick={() => setTheme(THEME_NEXT[theme])}><ThemeIcon theme={theme} /></button>
      </header>

      {showRange && (
        <div className="adm-range">
          {(Object.keys(PRESETS) as Preset[]).map((p) => (
            <button key={p} type="button" className={preset === p ? "active" : ""}
              onClick={() => { setPreset(p); setRange(presetRange(p)); }}>{PRESETS[p]}</button>
          ))}
          <label>Từ <input type="date" value={range.since ?? ""}
            onChange={(e) => { setPreset("custom"); setRange({ ...range, since: e.target.value || null }); }} /></label>
          <label>đến <input type="date" value={range.until ?? ""}
            onChange={(e) => { setPreset("custom"); setRange({ ...range, until: e.target.value || null }); }} /></label>
          <span className="adm-muted">giờ Việt Nam</span>
        </div>
      )}

      {error && <p className="adm-error" role="alert">{error} <button type="button" onClick={() => setError(null)}>Đóng</button></p>}

      <main className="adm-main">
        {tab === "overview" && <Overview range={range} onError={onError} />}
        {tab === "feedback" && <FeedbackInbox range={range} onError={onError} />}
        {tab === "turns" && <Turns range={range} onError={onError} />}
        {tab === "accounts" && <Accounts onError={onError} />}
        {tab === "settings" && <Settings onError={onError} />}
      </main>
    </div>
  );
}
