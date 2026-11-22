import { useEffect } from "react";
import type { KnownSession } from "../lib/storage";

export default function HistoryDrawer({ sessions, current, onOpen, onForget, onClose }: {
  sessions: KnownSession[];
  current: string | null;
  onOpen: (id: string) => void;
  onForget: (id: string) => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <>
      <div className="drawer-bg" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label="Lịch sử">
        <h2>
          Lịch sử trên máy này
          <button type="button" className="btn small" onClick={onClose} aria-label="Đóng">✕</button>
        </h2>
        {sessions.length === 0 ? (
          <p className="muted">Chưa có cuộc trò chuyện nào.</p>
        ) : (
          <ul>
            {sessions.map((s) => (
              <li key={s.id}>
                <button type="button" className={s.id === current ? "current" : ""} onClick={() => onOpen(s.id)}>
                  <span className="ellip">{s.firstQuestion || "(không có câu hỏi)"}</span>
                  <span className="muted">{new Date(s.at).toLocaleString("vi-VN")}</span>
                </button>
                <button type="button" className="btn small" title="Bỏ khỏi danh sách" aria-label="Bỏ khỏi danh sách"
                  onClick={() => onForget(s.id)}>✕</button>
              </li>
            ))}
          </ul>
        )}
        <p className="muted" style={{ marginTop: 16 }}>
          Danh sách chỉ lưu trên trình duyệt này; câu hỏi và câu trả lời được lưu trên máy chủ.
        </p>
      </aside>
    </>
  );
}
