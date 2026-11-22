import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ApiError, askStream, getTurn, getTurns, imageUrl, recoverTurn } from "./lib/api";
import {
  forgetSession, loadSessionId, loadSessions, loadTheme, rememberSession, saveSessionId, saveTheme,
  type KnownSession, type Theme,
} from "./lib/storage";
import { newTurn, turnFromStored, turnReducer, type TurnAction, type TurnState } from "./lib/turn";
import HistoryDrawer from "./components/HistoryDrawer";
import PhotoPanel, { ACCEPTED } from "./components/PhotoPanel";
import TurnView from "./components/TurnView";

const MAX_BYTES = 10 * 1024 * 1024; // the API's default VQA_MAX_IMAGE_MB

type ConvAction =
  | { type: "add"; turn: TurnState }
  | { type: "turn"; key: string; action: TurnAction }
  | { type: "set"; turns: TurnState[] };

function convReducer(turns: TurnState[], a: ConvAction): TurnState[] {
  switch (a.type) {
    case "add":
      return [...turns, a.turn];
    case "set":
      return a.turns;
    case "turn":
      return turns.map((t) => (t.key === a.key ? turnReducer(t, a.action) : t));
  }
}

interface Photo {
  url: string;
  blob: Blob | null; // null for a stored image; fetched again when asked about
}

const newKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

function turnFromHash(): string | null {
  const m = /(?:^#|&)turn=([0-9a-zA-Z_-]+)/.exec(window.location.hash);
  return m ? m[1] : null;
}

function setHash(turnId: string | null) {
  try {
    const url = turnId ? `#turn=${turnId}` : window.location.pathname + window.location.search;
    window.history.replaceState(null, "", url);
  } catch {
    /* ignore */
  }
}

const THEME_NEXT: Record<Theme, Theme> = { auto: "light", light: "dark", dark: "auto" };
const THEME_ICON: Record<Theme, string> = { auto: "🌓", light: "☀️", dark: "🌙" };
const THEME_LABEL: Record<Theme, string> = { auto: "Tự động", light: "Sáng", dark: "Tối" };

export default function App() {
  const [turns, dispatch] = useReducer(convReducer, []);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<KnownSession[]>(() => loadSessions());
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [photoErr, setPhotoErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => loadTheme());
  const [server, setServer] = useState<{ ok: boolean; fallback?: string; profile?: string } | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "auto") delete root.dataset.theme;
    else root.dataset.theme = theme;
    saveTheme(theme);
  }, [theme]);

  const adoptSession = useCallback((id: string | null) => {
    setSessionId(id);
    saveSessionId(id);
  }, []);

  const openSession = useCallback(async (id: string, turnId?: string) => {
    setLoadErr(null);
    try {
      const stored = await getTurns(id);
      const list = stored.map((t) => turnFromStored(t.turn_id, t, imageUrl(t.image_sha256)));
      adoptSession(id);
      dispatch({ type: "set", turns: list });
      const pick = list.find((t) => t.turnId === turnId) ?? list[list.length - 1];
      setSelected(pick ? pick.key : null);
      setPhoto(pick?.imageUrl ? { url: pick.imageUrl, blob: null } : null);
      if (pick?.turnId) setHash(pick.turnId);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setSessions(forgetSession(id));
        if (loadSessionId() === id) adoptSession(null);
        setLoadErr("Cuộc trò chuyện này không còn trên máy chủ.");
      } else {
        setLoadErr("Không tải được lịch sử. Kiểm tra kết nối tới máy chủ.");
      }
    }
  }, [adoptSession]);

  // start: a #turn=… link, else the last session of this browser
  useEffect(() => {
    fetch("/health")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(() => fetch("/version").then((r) => (r.ok ? r.json() : {})).catch(() => ({})))
      .then((v: { answer_fallback?: string; profile?: string }) =>
        setServer({ ok: true, fallback: v.answer_fallback, profile: v.profile }))
      .catch(() => setServer({ ok: false }));
    const linked = turnFromHash();
    if (linked) {
      getTurn(linked)
        .then((t) => openSession(t.session_id, t.turn_id))
        .catch(() => setLoadErr("Không tìm thấy câu hỏi trong đường dẫn."));
    } else {
      const sid = loadSessionId();
      if (sid) void openSession(sid);
    }
  }, [openSession]);

  // a #turn=… link followed while the page is open (replaceState in setHash does not fire this)
  useEffect(() => {
    const onHash = () => {
      const linked = turnFromHash();
      if (!linked) return;
      getTurn(linked)
        .then((t) => openSession(t.session_id, t.turn_id))
        .catch(() => setLoadErr("Không tìm thấy câu hỏi trong đường dẫn."));
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [openSession]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  const pickFile = useCallback((f: File) => {
    if (f.type && !ACCEPTED.includes(f.type)) {
      setPhotoErr(`Không nhận ảnh dạng ${f.type}. Hãy dùng JPEG, PNG hoặc WEBP.`);
      return;
    }
    if (f.size > MAX_BYTES) {
      setPhotoErr("Ảnh lớn hơn 10 MB.");
      return;
    }
    setPhotoErr(null);
    setPhoto({ url: URL.createObjectURL(f), blob: f });
    setSelected(null);
    setHash(null);
    textRef.current?.focus();
  }, []);

  // paste an image anywhere on the page
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (busy) return;
      const item = Array.from(e.clipboardData?.items ?? []).find((i) => i.kind === "file" && i.type.startsWith("image/"));
      const f = item?.getAsFile();
      if (f) {
        e.preventDefault();
        pickFile(f);
      }
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [busy, pickFile]);

  async function run(key: string, blob: Blob, q: string, sid: string | null, retry: boolean): Promise<void> {
    const act = (action: TurnAction) => dispatch({ type: "turn", key, action });
    let turnId: string | null = null;
    let final = false;
    try {
      await askStream(blob, q, sid, (event, data) => {
        if (event === "turn") {
          turnId = String(data.turn_id);
          const s = String(data.session_id);
          adoptSession(s);
          setSessions(rememberSession(s, q));
          setHash(turnId);
        }
        if (event === "answer" || event === "error") final = true;
        act({ type: "event", event, data });
      });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404 && sid && retry) {
        adoptSession(null); // the server no longer knows this session: start a new one
        return run(key, blob, q, null, false);
      }
      if (!turnId) {
        act({ type: "fail", error: e instanceof Error ? e.message : "Không kết nối được máy chủ." });
        return;
      }
    }
    if (final || !turnId) return;
    act({ type: "stream_end" });
    try {
      const t = await recoverTurn(turnId);
      act({ type: "loaded", turn: t });
      if (t.status === "running") act({ type: "fail", error: "Máy chủ vẫn đang xử lý; mở lại từ Lịch sử sau ít phút." });
    } catch {
      act({ type: "fail", error: "Mất kết nối với máy chủ. Câu trả lời vẫn được lưu; mở lại từ Lịch sử sau." });
    }
  }

  async function ask() {
    const q = question.trim();
    if (!q || busy) return;
    if (!photo) {
      setPhotoErr("Hãy chọn ảnh trước khi hỏi.");
      return;
    }
    setBusy(true);
    try {
      const blob = photo.blob ?? (await (await fetch(photo.url)).blob());
      const key = newKey();
      dispatch({ type: "add", turn: newTurn(key, q, photo.url) });
      setSelected(key);
      setQuestion("");
      await run(key, blob, q, sessionId, true);
    } catch {
      setPhotoErr("Không đọc được ảnh đã chọn. Hãy chọn lại ảnh.");
    } finally {
      setBusy(false);
    }
  }

  function selectTurn(t: TurnState) {
    setSelected(t.key);
    if (t.imageUrl) setPhoto((p) => (p && p.url === t.imageUrl ? p : { url: t.imageUrl as string, blob: null }));
    if (t.turnId) {
      setHash(t.turnId);
      if (!t.result && t.phase !== "streaming") {
        getTurn(t.turnId).then((full) => dispatch({ type: "turn", key: t.key, action: { type: "loaded", turn: full } })).catch(() => {});
      }
    }
  }

  function newConversation() {
    adoptSession(null);
    dispatch({ type: "set", turns: [] });
    setPhoto(null);
    setSelected(null);
    setLoadErr(null);
    setHash(null);
  }

  const shown = turns.find((t) => t.key === selected) ?? null;
  const panelUrl = shown?.imageUrl ?? photo?.url ?? null;

  return (
    <div className="app">
      <header className="topbar">
        <h1>🚦 Hỏi đáp biển báo giao thông</h1>
        <button type="button" className="btn small" onClick={() => setTheme(THEME_NEXT[theme])}
          aria-label={`Giao diện: ${THEME_LABEL[theme]}`} title={`Giao diện: ${THEME_LABEL[theme]}`}>
          {THEME_ICON[theme]}<span className="lbl">{THEME_LABEL[theme]}</span></button>
        <button type="button" className="btn small" onClick={() => setDrawer(true)} aria-label="Lịch sử">🕘<span className="lbl">Lịch sử</span></button>
        <button type="button" className="btn small" disabled={busy} onClick={newConversation} aria-label="Cuộc trò chuyện mới">＋<span className="lbl">Mới</span></button>
      </header>
      {server && !server.ok && (
        <div className="notice bad" role="alert" style={{ margin: "12px 16px 0" }}>
          Không kết nối được máy chủ API. Hãy kiểm tra máy chủ rồi tải lại trang.
        </div>
      )}
      {server?.profile?.startsWith("fake") && (
        <div className="notice bad" role="alert" data-testid="fake-banner" style={{ margin: "12px 16px 0" }}>
          <strong>Máy chủ thử nghiệm (pipeline giả, profile “{server.profile}”).</strong> Mọi câu trả lời đều là
          dữ liệu mẫu cố định, không phải từ hệ thống thật.
        </div>
      )}
      <main className="layout">
        <div className="photo-col">
          <PhotoPanel imageUrl={panelUrl} imageSize={shown?.imageSize ?? null} signs={shown?.signs ?? []}
            busy={busy} onPick={pickFile} error={photoErr}
            onClear={() => { setPhoto(null); setSelected(null); setHash(null); }} />
          {server?.ok && server.fallback && (
            <p className="muted" style={{ margin: "8px 4px 0" }}>
              Chế độ dự phòng: {server.fallback === "rag" ? "RAG" : server.fallback === "off" ? "tắt" : server.fallback}
            </p>
          )}
        </div>
        <section className="conv" aria-label="Cuộc trò chuyện">
          {loadErr && <div className="notice warn" role="status">{loadErr}</div>}
          {turns.length === 0 && (
            <div className="card empty">
              Chọn một ảnh có biển báo, rồi đặt câu hỏi, ví dụ: “Xe ô tô có được đi vào đường này không?”
            </div>
          )}
          {turns.map((t) => (
            <TurnView key={t.key} t={t} selected={t.key === selected && turns.length > 1}
              onSelect={() => selectTurn(t)}
              onFeedback={(f) => dispatch({ type: "turn", key: t.key, action: { type: "feedback", feedback: f } })} />
          ))}
          <div ref={endRef} />
          <form className="card ask" onSubmit={(e) => { e.preventDefault(); void ask(); }}>
            <label htmlFor="question" className="sr-only">Câu hỏi</label>
            <textarea id="question" ref={textRef} rows={1} maxLength={500} value={question}
              placeholder={photo ? "Đặt câu hỏi về ảnh…" : "Chọn ảnh, rồi đặt câu hỏi…"}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  void ask();
                }
              }} />
            <button type="submit" className="btn primary" disabled={busy || !question.trim() || !photo}>
              {busy ? "Đang trả lời…" : "Hỏi"}
            </button>
          </form>
        </section>
      </main>
      {drawer && (
        <HistoryDrawer sessions={sessions} current={sessionId}
          onOpen={(id) => { setDrawer(false); void openSession(id); }}
          onForget={(id) => setSessions(forgetSession(id))}
          onClose={() => setDrawer(false)} />
      )}
    </div>
  );
}
