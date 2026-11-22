import { PRODUCT, TAGLINE } from "../lib/brand";
import type { KnownSession, Theme } from "../lib/storage";
import { Close, Contrast, Moon, PanelLeft, Plus, Sun } from "./Icons";

export const THEME_NEXT: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };
export const THEME_LABEL: Record<Theme, string> = { auto: "Giao diện: tự động", light: "Giao diện: sáng", dark: "Giao diện: tối" };
export const ThemeIcon = ({ theme, size }: { theme: Theme; size?: number }) =>
  theme === "dark" ? <Moon size={size} /> : theme === "light" ? <Sun size={size} /> : <Contrast size={size} />;

function groups(sessions: KnownSession[]): [string, KnownSession[]][] {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const today = sessions.filter((s) => new Date(s.at) >= start);
  const older = sessions.filter((s) => new Date(s.at) < start);
  return ([["Hôm nay", today], ["Trước đó", older]] as [string, KnownSession[]][]).filter(([, l]) => l.length);
}

export default function Sidebar({ sessions, current, busy, theme, serverNote, onNew, onOpen, onForget, onTheme, onClose, onCollapse }: {
  sessions: KnownSession[];
  current: string | null;
  busy: boolean;
  theme: Theme;
  serverNote: string | null;
  onNew: () => void;
  onOpen: (id: string) => void;
  onForget: (id: string) => void;
  onTheme: () => void;
  onClose?: () => void; // in the phone drawer
  onCollapse?: () => void; // on a wide screen: fold the bar away
}) {
  return (
    <div className="sidebar-inner">
      <div className="brand">
        <span className="brand-text"><span className="brand-name">{PRODUCT}</span><span className="brand-tag">{TAGLINE}</span></span>
        {onCollapse && (
          <button type="button" className="icon-btn" style={{ marginLeft: "auto" }} onClick={onCollapse}
            aria-label="Thu gọn thanh bên" title="Thu gọn thanh bên" aria-expanded={true}>
            <PanelLeft size={19} />
          </button>
        )}
        {onClose && (
          <button type="button" className="icon-btn" style={{ marginLeft: "auto" }} onClick={onClose} aria-label="Đóng lịch sử">
            <Close />
          </button>
        )}
      </div>
      <button type="button" className="new-chat" disabled={busy} onClick={onNew}>
        <Plus /> Cuộc trò chuyện mới
      </button>
      <nav aria-label="Lịch sử" className="history">
        {sessions.length === 0 && <p className="muted" style={{ padding: "6px 10px" }}>Chưa có cuộc trò chuyện nào.</p>}
        {groups(sessions).map(([label, list]) => (
          <div key={label}>
            <div className="history-label">{label}</div>
            <ul>
              {list.map((s) => (
                <li key={s.id} className={s.id === current ? "current" : ""}>
                  <button type="button" className="history-item" onClick={() => onOpen(s.id)}
                    aria-current={s.id === current ? "page" : undefined}
                    title={new Date(s.at).toLocaleString("vi-VN")}>
                    {s.firstQuestion || "(không có câu hỏi)"}
                  </button>
                  <button type="button" className="history-forget" onClick={() => onForget(s.id)}
                    aria-label="Bỏ khỏi danh sách" title="Bỏ khỏi danh sách">
                    <Close size={14} />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="sidebar-foot">
        <button type="button" className="theme-btn" onClick={onTheme}>
          <ThemeIcon theme={theme} size={16} /> {THEME_LABEL[theme]}
        </button>
        {serverNote && <div className="muted small">{serverNote}</div>}
        <div className="muted small">Danh sách lưu trên trình duyệt này.</div>
      </div>
    </div>
  );
}
