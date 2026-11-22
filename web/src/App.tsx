import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { ApiError, askStream, getTurn, getTurns, imageUrl, recoverTurn } from "./lib/api";
import {
  forgetSession, loadFlag, loadSessionId, loadSessions, loadTheme, rememberSession, saveFlag, saveSessionId, saveTheme,
  type KnownSession, type Theme,
} from "./lib/storage";
import { newTurn, turnFromStored, turnReducer, type TurnAction, type TurnState } from "./lib/turn";
import Composer, { ACCEPTED } from "./components/Composer";
import { Menu, PanelLeft, PanelRight, Pencil } from "./components/Icons";
import PhotoPanel from "./components/PhotoPanel";
import Sidebar, { THEME_LABEL, THEME_NEXT, ThemeIcon } from "./components/Sidebar";
import TurnView from "./components/TurnView";
import { PRODUCT } from "./lib/brand";

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
  name: string | null; // a new file's name; null for the photo of an earlier question
  size: number | null;
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

// written for the demo, not taken from the dataset
const EXAMPLES = [
  "Xe ô tô có được đi vào đường này không?",
  "Đây là biển báo gì?",
  "Tốc độ tối đa cho xe máy là bao nhiêu?",
  "Xe tải có được đi qua đoạn đường này không?",
];

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
  // wide screens: the side bars can be folded away; the choice is remembered in this browser
  const [sideOpen, setSideOpen] = useState(() => loadFlag("vqa.sideOpen", true));
  const [photoOpen, setPhotoOpen] = useState(() => loadFlag("vqa.photoOpen", true));
  useEffect(() => saveFlag("vqa.sideOpen", sideOpen), [sideOpen]);
  useEffect(() => saveFlag("vqa.photoOpen", photoOpen), [photoOpen]);
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

  const openSession = useCallback(async (id: string, turnId?: string, quiet = false) => {
    setLoadErr(null);
    try {
      const stored = await getTurns(id);
      const list = stored.map((t) => turnFromStored(t.turn_id, t, imageUrl(t.image_sha256)));
      adoptSession(id);
      dispatch({ type: "set", turns: list });
      const pick = list.find((t) => t.turnId === turnId) ?? list[list.length - 1];
      setSelected(pick ? pick.key : null);
      setPhoto(pick?.imageUrl ? { url: pick.imageUrl, blob: null, name: null, size: null } : null);
      if (pick?.turnId) setHash(pick.turnId);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setSessions(forgetSession(id));
        if (loadSessionId() === id) adoptSession(null);
        if (!quiet) setLoadErr("Cuộc trò chuyện này không còn trên máy chủ.");
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
      if (sid) void openSession(sid, undefined, true); // a session the server no longer has is dropped quietly
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
    setPhoto({ url: URL.createObjectURL(f), blob: f, name: f.name || "Ảnh đã dán", size: f.size });
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

  async function ask(override?: string) {
    const q = (override ?? question).trim();
    if (!q || busy) return;
    if (!photo) {
      setPhotoErr("Hãy chọn ảnh trước khi hỏi.");
      return;
    }
    setBusy(true);
    setLoadErr(null);
    try {
      const blob = photo.blob ?? (await (await fetch(photo.url)).blob());
      const key = newKey();
      dispatch({ type: "add", turn: newTurn(key, q, photo.url) });
      setSelected(key);
      setQuestion("");
      setPhotoErr(null);
      setPhoto((p) => (p ? { ...p, name: null, size: null } : p)); // now the photo of a question
      await run(key, blob, q, sessionId, true);
    } catch {
      setPhotoErr("Không đọc được ảnh đã chọn. Hãy chọn lại ảnh.");
    } finally {
      setBusy(false);
    }
  }

  function selectTurn(t: TurnState) {
    setSelected(t.key);
    if (t.imageUrl) setPhoto((p) => (p && p.url === t.imageUrl ? p : { url: t.imageUrl as string, blob: null, name: null, size: null }));
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
  const title = turns.length ? turns[0].question : "";
  const serverNote = server?.ok && server.fallback
    ? `Dự phòng: ${server.fallback === "rag" ? "RAG" : server.fallback === "off" ? "tắt" : server.fallback}`
    : null;
  const chatDrop = {
    onDragOver: (e: React.DragEvent) => e.preventDefault(),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      const f = e.dataTransfer.files[0];
      if (f && !busy) pickFile(f);
    },
  };
  const sidebar = (inDrawer: boolean) => (
    <Sidebar sessions={sessions} current={sessionId} busy={busy} theme={theme} serverNote={serverNote}
      onNew={() => { setDrawer(false); newConversation(); }}
      onOpen={(id) => { setDrawer(false); void openSession(id); }}
      onForget={(id) => setSessions(forgetSession(id))}
      onTheme={() => setTheme(THEME_NEXT[theme])}
      onClose={inDrawer ? () => setDrawer(false) : undefined} />
  );
  const composer = (
    <Composer ref={textRef} busy={busy} error={photoErr} question={question} onQuestion={setQuestion}
      photo={photo ? { url: photo.url, name: photo.name, size: photo.size } : null}
      onPick={pickFile} onSubmit={() => void ask()}
      onClearPhoto={() => { setPhoto(null); setSelected(null); setHash(null); }} />
  );

  return (
    <div className={`shell${sideOpen ? "" : " no-side"}${photoOpen ? "" : " no-photo"}${turns.length ? "" : " empty"}`}>
      {/* wide screens: one button per side bar, pinned to its corner, open or folded */}
      <button type="button" className="icon-btn bar-toggle side-toggle" onClick={() => setSideOpen(!sideOpen)}
        aria-expanded={sideOpen} aria-label={sideOpen ? "Thu gọn thanh bên" : "Mở thanh bên"}
        title={sideOpen ? "Thu gọn thanh bên" : "Mở thanh bên"}><PanelLeft size={19} /></button>
      <button type="button" className="icon-btn bar-toggle photo-toggle" onClick={() => setPhotoOpen(!photoOpen)}
        aria-expanded={photoOpen} aria-label={photoOpen ? "Thu gọn khung ảnh" : "Mở khung ảnh"}
        title={photoOpen ? "Thu gọn khung ảnh" : "Mở khung ảnh"}><PanelRight size={19} /></button>
      <aside className="sidebar">{sidebar(false)}</aside>
      <header className={`topbar${turns.length ? "" : " empty"}`}>
        <button type="button" className="icon-btn narrow-only drawer-btn" aria-label="Mở lịch sử" title="Mở lịch sử"
          onClick={() => setDrawer(true)}>
          <Menu size={20} />
        </button>
        <h1 className="topbar-title">{title}</h1>
        {/* phones, before the first question: the product name in the middle of the bar */}
        {!turns.length && <span className="topbar-brand brand-name" aria-hidden>{PRODUCT}</span>}
        <button type="button" className="icon-btn narrow-only" onClick={() => setTheme(THEME_NEXT[theme])}
          aria-label={THEME_LABEL[theme]} title={THEME_LABEL[theme]}><ThemeIcon theme={theme} size={19} /></button>
        <button type="button" className="icon-btn narrow-only new-btn" disabled={busy} onClick={newConversation}
          aria-label="Cuộc trò chuyện mới" title="Cuộc trò chuyện mới"><Pencil size={19} /></button>
      </header>
      <PhotoPanel imageUrl={panelUrl} imageSize={shown?.imageSize ?? null} signs={shown?.signs ?? []}
        busy={busy} onDropFile={pickFile} />
      <main className={`chat${turns.length ? "" : " empty"}`} aria-label="Cuộc trò chuyện" {...chatDrop}>
        {server && !server.ok && (
          <div className="notice bad" role="alert">Không kết nối được máy chủ API. Hãy kiểm tra máy chủ rồi tải lại trang.</div>
        )}
        {server?.profile?.startsWith("fake") && (
          <div className="notice bad" role="alert" data-testid="fake-banner">
            <strong>Máy chủ thử nghiệm (pipeline giả, profile “{server.profile}”).</strong> Mọi câu trả lời đều là
            dữ liệu mẫu cố định, không phải từ hệ thống thật.
          </div>
        )}
        {loadErr && <div className="notice warn" role="status">{loadErr}</div>}
        {turns.length === 0 ? (
          <div className="hero">
            {/* the box is the anchor: the greeting sits just above it and grows upward if it wraps */}
            <div className="hero-anchor">
              <h2>Hỏi về biển báo trong ảnh của bạn</h2>
              {composer}
            </div>
            <div className="examples">
              {EXAMPLES.map((q) => (
                <button key={q} type="button" className="example" disabled={busy} onClick={() => {
                  if (photo) void ask(q);
                  else { setQuestion(q); setPhotoErr("Hãy đính kèm ảnh có biển báo trước khi hỏi."); textRef.current?.focus(); }
                }}>{q}</button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <div className={`thread${turns.every((o) => o.imageUrl === turns[0].imageUrl) ? " one-photo" : ""}`}>
              {turns.map((t, i) => {
                const prev = turns[i - 1];
                const same = prev && (t.imageSha && prev.imageSha ? t.imageSha === prev.imageSha : t.imageUrl === prev.imageUrl);
                return (
                  <TurnView key={t.key} t={t} showImage={!same} selected={t.key === selected && turns.some((o) => o.imageUrl !== t.imageUrl)}
                    onSelect={() => selectTurn(t)}
                    onFeedback={(f) => dispatch({ type: "turn", key: t.key, action: { type: "feedback", feedback: f } })} />
                );
              })}
              <div ref={endRef} />
            </div>
            <div className="composer-dock">
              {composer}
              <p className="footnote">Câu trả lời của hệ luật có căn cứ và chứng minh; câu trả lời RAG chưa được hệ luật kiểm chứng.</p>
            </div>
          </>
        )}
      </main>
      {drawer && (
        <>
          <div className="drawer-bg" onClick={() => setDrawer(false)} />
          <aside className="drawer" role="dialog" aria-modal="true" aria-label="Lịch sử">{sidebar(true)}</aside>
        </>
      )}
    </div>
  );
}
