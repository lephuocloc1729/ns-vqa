import { useCallback, useEffect, useState } from "react";
import { admin, type Live, type SettingsView } from "./api";
import { fmtInt, fmtUsd } from "./format";
import GpuCard from "./GpuCard";

const MODES: Record<Live["answer_fallback"], string> = {
  off: "Tắt: câu hệ luật chưa quyết định được trả lời là chưa xác định",
  rag: "RAG trên GPU thuê",
  claude: "Claude (Sonnet) – tốn chi phí API",
};

export default function Settings({ onError }: { onError: (e: unknown) => void }) {
  const [v, setV] = useState<SettingsView | null>(null);
  const [form, setForm] = useState<Live | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(() => admin.settings().then((x) => {
    setV(x);
    setForm(x.live);
  }, onError), [onError]);
  useEffect(() => {
    load();
  }, [load]);

  if (!v || !form) return <p className="adm-muted">Đang tải…</p>;

  const changed: Partial<Live> = {};
  (Object.keys(form) as (keyof Live)[]).forEach((k) => {
    if (form[k] !== v.live[k]) (changed as Record<string, unknown>)[k] = form[k];
  });
  const dirty = Object.keys(changed).length > 0;

  const run = async (f: () => Promise<SettingsView | void>, done: string) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await f();
      if (r) {
        setV(r);
        setForm(r.live);
      } else {
        await load();
      }
      setMsg(done);
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };

  const tag = (k: keyof Live) => (v.overridden.includes(k)
    ? <span className="adm-tag">đặt tại đây</span>
    : <span className="adm-tag adm-tag-muted">mặc định .env</span>);

  return (
    <div className="adm-stack adm-settings">
      <p className="adm-muted">
        Áp dụng từ câu hỏi tiếp theo, không khởi động lại máy chủ. Câu đang trả lời dở vẫn dùng cài đặt cũ.
      </p>

      <GpuCard onChange={load} onError={onError} />

      <fieldset>
        <legend>Trả lời dự phòng {tag("answer_fallback")}</legend>
        {(Object.keys(MODES) as Live["answer_fallback"][]).map((m) => (
          <label key={m} className="adm-radio">
            <input type="radio" name="fallback" checked={form.answer_fallback === m}
              onChange={() => setForm({ ...form, answer_fallback: m })} />
            {MODES[m]}
          </label>
        ))}
        <label className="adm-field">
          <span>Địa chỉ RAG {tag("rag_url")}</span>
          <input value={form.rag_url} onChange={(e) => setForm({ ...form, rag_url: e.target.value })} />
        </label>
        <p className={v.rag.reachable ? "adm-ok" : "adm-muted"}>
          {v.rag.reachable ? "● RAG đang trả lời tại " : "○ RAG không trả lời tại "}{v.rag.url}
          {!v.rag.reachable && ` (${v.rag.detail}). Bật RAG cần GPU đang chạy và đường hầm đã nối.`}
        </p>
      </fieldset>

      <fieldset>
        <legend>Bộ nhớ đệm câu trả lời RAG {tag("rag_cache")}</legend>
        <label className="adm-radio">
          <input type="checkbox" checked={form.rag_cache} onChange={(e) => setForm({ ...form, rag_cache: e.target.checked })} />
          Dùng lại câu trả lời RAG cũ cho cùng ảnh và cùng câu hỏi
        </label>
        <p className="adm-muted">
          Đang lưu {fmtInt(v.rag_cache_entries)} câu trả lời.{" "}
          <button type="button" disabled={busy || !v.rag_cache_entries} onClick={() => {
            if (window.confirm("Xoá toàn bộ bộ nhớ đệm câu trả lời RAG? Không hoàn tác được.")) {
              run(async () => { await admin.clearRagCache(); }, "Đã xoá bộ nhớ đệm câu trả lời RAG.");
            }
          }}>Xoá bộ nhớ đệm</button>
        </p>
      </fieldset>

      <fieldset>
        <legend>Hạn mức chi phí Claude {tag("spend_limit")}</legend>
        <label className="adm-field">
          <span>USD cho tiến trình máy chủ hiện tại</span>
          <input type="number" min={0.5} max={1000} step={0.5} value={form.spend_limit ?? ""}
            onChange={(e) => setForm({ ...form, spend_limit: e.target.value === "" ? null : Number(e.target.value) })} />
        </label>
        <p className="adm-muted">
          Đã dùng {v.spend.spent != null ? fmtUsd(v.spend.spent)
            : v.spend.loaded ? "– (không theo dõi)" : "– (chưa có câu hỏi nào từ lần khởi động này)"} / {fmtUsd(v.spend.limit)}.
          Số đã dùng tính lại từ 0 khi máy chủ khởi động lại.
        </p>
      </fieldset>

      <fieldset>
        <legend>Cố định (cần khởi động lại để đổi)</legend>
        <p className="adm-muted">Số câu trả lời cùng lúc: {v.fixed.answer_slots} · Cấu hình: {v.fixed.profile}</p>
      </fieldset>

      <div className="adm-filters">
        <button type="button" className="adm-primary" disabled={busy || !dirty}
          onClick={() => run(() => admin.saveSettings(changed), "Đã lưu. Áp dụng từ câu hỏi tiếp theo.")}>Lưu</button>
        <button type="button" disabled={busy || !dirty} onClick={() => setForm(v.live)}>Huỷ thay đổi</button>
        <button type="button" disabled={busy || v.overridden.length === 0} onClick={() => {
          if (window.confirm("Trở về các giá trị trong .env?")) run(() => admin.resetSettings(), "Đã trở về mặc định .env.");
        }}>Về mặc định .env</button>
        <button type="button" disabled={busy} onClick={() => run(async () => { await load(); }, "Đã tải lại.")}>Kiểm tra lại</button>
      </div>
      {msg && <p className="adm-ok" role="status">{msg}</p>}
    </div>
  );
}
