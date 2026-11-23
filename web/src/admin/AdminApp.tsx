import { useCallback, useEffect, useState } from "react";
import { Close, Logo, Menu } from "../components/Icons";
import { THEME_LABEL, THEME_NEXT, ThemeIcon } from "../components/Sidebar";
import { PRODUCT } from "../lib/brand";
import { loadTheme, saveTheme, type Theme } from "../lib/storage";
import Accounts from "./Accounts";
import { AdminError, type Range } from "./api";
import { presetRange, type Preset } from "./format";
import { External, Gear, Home, Inbox, List, Users } from "./icons";
import Overview, { type Drill } from "./Overview";
import Settings from "./Settings";
import Turns, { FeedbackInbox, type TurnFilters } from "./Turns";

type Tab = "overview" | "feedback" | "turns" | "accounts" | "settings";

const NAV: { group: string; items: { tab: Tab; label: string; icon: (p: { size?: number }) => JSX.Element; hint: string }[] }[] = [
  {
    group: "Theo dõi",
    items: [
      { tab: "overview", label: "Tổng quan", icon: Home, hint: "Số liệu và biểu đồ" },
      { tab: "feedback", label: "Phản hồi", icon: Inbox, hint: "Câu trả lời bị chê, sửa hoặc ghi chú" },
      { tab: "turns", label: "Câu hỏi", icon: List, hint: "Mọi câu hỏi, lọc theo tài khoản" },
    ],
  },
  {
    group: "Quản lý",
    items: [
      { tab: "accounts", label: "Tài khoản", icon: Users, hint: "Tài khoản người thử" },
      { tab: "settings", label: "Cài đặt", icon: Gear, hint: "Dự phòng, bộ nhớ đệm, hạn mức" },
    ],
  },
];
const LABEL = Object.fromEntries(NAV.flatMap((g) => g.items.map((i) => [i.tab, i.label]))) as Record<Tab, string>;

const PRESETS: Record<Preset, string> = { today: "Hôm nay", "7d": "7 ngày", "30d": "30 ngày", all: "Tất cả" };

function tabFromHash(): Tab {
  const h = window.location.hash.slice(1);
  return (h in LABEL ? h : "overview") as Tab;
}

/** The public app's address, when this page runs on admin.<domain>. */
function appAddress(): string | null {
  const h = window.location.host;
  return h.startsWith("admin.") ? `${window.location.protocol}//${h.slice(6)}/` : null;
}

export default function AdminApp() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [preset, setPreset] = useState<Preset | "custom">("7d");
  const [range, setRange] = useState<Range>(() => presetRange("7d"));
  const [filters, setFilters] = useState<TurnFilters>({});
  const [drillKey, setDrillKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(() => loadTheme());
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") delete root.dataset.theme;
    else root.dataset.theme = theme;
    saveTheme(theme);
  }, [theme]);

  useEffect(() => {
    const f = () => setTab(tabFromHash());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);

  useEffect(() => {
    document.title = `${LABEL[tab]} – ${PRODUCT} quản trị`;
  }, [tab]);

  const onError = useCallback((e: unknown) => {
    if (e instanceof AdminError && e.status === 401) setError("Cần đăng nhập quản trị. Tải lại trang để nhập mật khẩu.");
    else setError(e instanceof Error ? e.message : String(e));
  }, []);

  const go = (t: Tab, f: TurnFilters = {}) => {
    setError(null);
    setFilters(f);
    setDrillKey((k) => k + 1);
    setTab(t);
    setDrawer(false);
    window.history.replaceState(null, "", `#${t}`);
    window.scrollTo(0, 0);
  };

  const drill = (d: Drill) => {
    if (d.since || d.until) {
      setPreset("custom");
      setRange({ since: d.since ?? range.since, until: d.until ?? range.until });
    }
    go("turns", { route: d.route, verdict: d.verdict });
  };

  const showRange = tab === "overview" || tab === "turns" || tab === "feedback";
  const app = appAddress();

  const sidebar = (
    <aside className={`adm-side${drawer ? " open" : ""}`} aria-label="Điều hướng">
      <div className="adm-side-brand">
        <Logo size={24} /><span className="brand-name">{PRODUCT}</span><span className="adm-tag">quản trị</span>
        <button type="button" className="adm-icon-btn adm-drawer-close" aria-label="Đóng menu" onClick={() => setDrawer(false)}>
          <Close size={18} />
        </button>
      </div>
      <nav>
        {NAV.map((g) => (
          <div key={g.group} className="adm-nav-group">
            <div className="adm-nav-title">{g.group}</div>
            {g.items.map(({ tab: t, label, icon: Icon, hint }) => (
              <button key={t} type="button" className={`adm-nav-item${t === tab ? " active" : ""}`} title={hint}
                aria-current={t === tab ? "page" : undefined} onClick={() => go(t)}>
                <Icon size={18} /><span>{label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="adm-side-foot">
        {app && (
          <a className="adm-nav-item" href={app} target="_blank" rel="noreferrer"><External size={18} /><span>Mở ứng dụng</span></a>
        )}
        <button type="button" className="adm-nav-item" onClick={() => setTheme(THEME_NEXT[theme])}>
          <ThemeIcon theme={theme} size={18} /><span>{THEME_LABEL[theme]}</span>
        </button>
        <div className="adm-side-user">Đăng nhập: <b>admin</b></div>
      </div>
    </aside>
  );

  return (
    <div className="adm-shell">
      {sidebar}
      {drawer && <div className="adm-drawer-bg" onClick={() => setDrawer(false)} />}
      <div className="adm-content">
        <header className="adm-top">
          <button type="button" className="adm-icon-btn adm-menu" aria-label="Mở menu" onClick={() => setDrawer(true)}>
            <Menu size={20} />
          </button>
          <h1>{LABEL[tab]}</h1>
          {showRange && (
            <div className="adm-range">
              <div className="adm-seg" role="group" aria-label="Khoảng thời gian">
                {(Object.keys(PRESETS) as Preset[]).map((p) => (
                  <button key={p} type="button" className={preset === p ? "active" : ""} aria-pressed={preset === p}
                    onClick={() => { setPreset(p); setRange(presetRange(p)); }}>{PRESETS[p]}</button>
                ))}
              </div>
              <label><span className="adm-sr">Từ ngày</span><input type="date" value={range.since ?? ""}
                onChange={(e) => { setPreset("custom"); setRange({ ...range, since: e.target.value || null }); }} /></label>
              <span className="adm-muted">–</span>
              <label><span className="adm-sr">Đến ngày</span><input type="date" value={range.until ?? ""}
                onChange={(e) => { setPreset("custom"); setRange({ ...range, until: e.target.value || null }); }} /></label>
            </div>
          )}
        </header>

        {error && <p className="adm-error" role="alert">{error} <button type="button" onClick={() => setError(null)}>Đóng</button></p>}

        <main className="adm-main">
          {tab === "overview" && <Overview range={range} onError={onError} onDrill={drill} />}
          {tab === "feedback" && <FeedbackInbox range={range} onError={onError} />}
          {tab === "turns" && <Turns key={drillKey} range={range} onError={onError} initial={filters} />}
          {tab === "accounts" && <Accounts onError={onError} />}
          {tab === "settings" && <Settings onError={onError} />}
          {showRange && <p className="adm-muted adm-foot-note">Ngày tính theo giờ Việt Nam.</p>}
        </main>
      </div>
    </div>
  );
}
