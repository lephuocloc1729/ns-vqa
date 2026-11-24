// The GPU connection on the Cài đặt page: connect the server to a rented GPU's RAG, switch the
// answer fallback to it, and disconnect (app/api/gpu.py, docker/rag-tunnel/tunnel.sh).

import { useCallback, useEffect, useState } from "react";
import { Copy } from "../components/Icons";
import { admin, type Gpu } from "./api";
import { parseSsh } from "./format";

const STATE: Record<string, { text: string; tone: "ok" | "wait" | "bad" | "idle" }> = {
  not_running: { text: "Dịch vụ đường hầm chưa chạy trên máy chủ", tone: "bad" },
  unknown: { text: "Không đọc được trạng thái đường hầm", tone: "bad" },
  standby: { text: "Chưa nối GPU", tone: "idle" },
  no_key: { text: "Máy chủ chưa có khoá SSH (chạy docker/rag-session.sh key trên máy chủ)", tone: "bad" },
  connecting: { text: "Đang nối…", tone: "wait" },
  connected: { text: "Đã nối", tone: "ok" },
  error: { text: "Nối không được, đang thử lại", tone: "bad" },
};

export default function GpuCard({ onChange, onError }: { onChange: () => void; onError: (e: unknown) => void }) {
  const [g, setG] = useState<Gpu | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => admin.gpu().then(setG, onError), [onError]);
  useEffect(() => {
    load();
  }, [load]);

  // while a connection is being made (or is up), keep the state fresh
  const watching = !!g?.target;
  useEffect(() => {
    if (!watching) return;
    const id = window.setInterval(() => admin.gpu().then(setG, () => {}), 3000);
    return () => window.clearInterval(id);
  }, [watching]);

  if (!g) return null;
  if (!g.enabled) {
    return (
      <fieldset>
        <legend>Máy GPU cho RAG</legend>
        <p className="adm-muted">Máy chủ này chưa bật điều khiển GPU (VQA_GPU_DIR).</p>
      </fieldset>
    );
  }

  const run = async (f: () => Promise<Gpu>) => {
    setBusy(true);
    try {
      setG(await f());
      onChange();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };

  const parsed = parseSsh(text);
  const st = STATE[g.state ?? "unknown"] ?? STATE.unknown;
  const ragOk = g.state === "connected" && g.rag?.reachable;

  return (
    <fieldset className="adm-gpu">
      <legend>Máy GPU cho RAG</legend>

      <p className={`adm-gpu-state adm-tone-${st.tone}`}>
        <span className="adm-dot" />
        {st.text}
        {g.target && <> · <code>{g.target.host}:{g.target.port}</code></>}
        {g.state === "connected" && (ragOk ? " · RAG trả lời" : " · đang chờ RAG trả lời")}
        {g.rag_in_use && <span className="adm-tag">đang dùng cho câu hỏi</span>}
      </p>
      {g.detail && g.state !== "connected" && <p className="adm-muted">{g.detail}</p>}

      {!g.target ? (
        <form className="adm-filters" onSubmit={(e) => {
          e.preventDefault();
          if (parsed?.host && parsed.port) run(() => admin.gpuConnect(parsed.host, parsed.port!));
        }}>
          <input value={text} onChange={(e) => setText(e.target.value)} aria-label="Địa chỉ SSH của máy GPU"
            placeholder="Dán lệnh SSH của vast.ai, ví dụ: ssh -p 41413 root@122.117.118.68" />
          <button type="submit" className="adm-primary" disabled={busy || !parsed?.host || !parsed.port}>Nối</button>
          {text && parsed && <span className="adm-muted">{parsed.host}{parsed.port ? `:${parsed.port}` : " (thiếu cổng)"}</span>}
        </form>
      ) : (
        <div className="adm-filters">
          {ragOk && !g.rag_in_use && (
            <button type="button" className="adm-primary" disabled={busy}
              onClick={() => run(async () => {
                await admin.saveSettings({ answer_fallback: "rag", rag_url: g.rag_url });
                return admin.gpu();
              })}>Dùng RAG trên GPU này</button>
          )}
          {g.rag_in_use && (
            <button type="button" disabled={busy}
              onClick={() => run(async () => {
                await admin.saveSettings({ answer_fallback: "off" });
                return admin.gpu();
              })}>Tạm tắt RAG</button>
          )}
          <button type="button" disabled={busy} onClick={() => {
            if (window.confirm("Ngắt GPU? Câu hỏi hệ luật chưa quyết định sẽ không còn chuyển sang RAG.")) {
              run(() => admin.gpuDisconnect());
            }
          }}>Ngắt GPU</button>
        </div>
      )}

      <p className="adm-muted">
        Ngắt GPU trước khi huỷ máy trên vast.ai. Câu đang trả lời dở vẫn xong với cài đặt cũ.
      </p>
      {g.public_key && (
        <details className="adm-key">
          <summary>Khoá SSH của máy chủ (thêm vào vast.ai một lần)</summary>
          <code>{g.public_key}</code>
          <button type="button" className="adm-icon-btn" aria-label="Sao chép khoá" onClick={() => {
            navigator.clipboard?.writeText(g.public_key ?? "").then(() => setCopied(true), () => {});
          }}><Copy size={16} /></button>
          {copied && <span className="adm-muted"> đã sao chép</span>}
        </details>
      )}
    </fieldset>
  );
}
