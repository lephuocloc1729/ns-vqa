import { useState } from "react";
import { sendFeedback } from "../lib/api";
import type { Feedback } from "../lib/types";
import { Check, Copy, Pencil, ThumbDown, ThumbUp } from "./Icons";

export default function FeedbackBar({ turnId, answer, given, onSent }: {
  turnId: string;
  answer: string;
  given: Feedback[];
  onSent: (f: Feedback) => void;
}) {
  const [open, setOpen] = useState(false);
  const [fix, setFix] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const thumb = [...given].reverse().find((f) => f.thumb)?.thumb ?? null;
  const corrected = given.filter((f) => f.corrected_answer || f.note);

  async function send(body: Parameters<typeof sendFeedback>[1]) {
    setBusy(true);
    setErr(null);
    try {
      onSent(await sendFeedback(turnId, body));
      return true;
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Không gửi được.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  }

  return (
    <div className="feedback" data-testid="feedback">
      <div className="feedback-icons">
        <button type="button" className={`icon-btn${thumb === "up" ? " on" : ""}`} disabled={busy}
          aria-pressed={thumb === "up"} aria-label="Câu trả lời đúng" title="Câu trả lời đúng"
          onClick={() => send({ thumb: "up" })}><ThumbUp size={17} /></button>
        <button type="button" className={`icon-btn${thumb === "down" ? " on" : ""}`} disabled={busy}
          aria-pressed={thumb === "down"} aria-label="Câu trả lời sai" title="Câu trả lời sai"
          onClick={() => send({ thumb: "down" })}><ThumbDown size={17} /></button>
        <button type="button" className={`icon-btn${open ? " on" : ""}`} disabled={busy} aria-expanded={open}
          aria-label="Sửa đáp án" title="Sửa đáp án" onClick={() => setOpen(!open)}><Pencil size={17} /></button>
        <button type="button" className="icon-btn" aria-label="Sao chép câu trả lời" title="Sao chép"
          onClick={copy}>{copied ? <Check size={17} /> : <Copy size={17} />}</button>
        {thumb && <span className="muted small" role="status">Cảm ơn bạn đã đánh giá.</span>}
      </div>
      {open && (
        <form className="fix-form" onSubmit={async (e) => {
          e.preventDefault();
          if (!fix.trim() && !note.trim()) return;
          const ok = await send({ corrected_answer: fix.trim() || undefined, note: note.trim() || undefined });
          if (ok) { setFix(""); setNote(""); setOpen(false); }
        }}>
          <label className="sr-only" htmlFor={`fix-${turnId}`}>Đáp án đúng</label>
          <textarea id={`fix-${turnId}`} rows={2} maxLength={4000} placeholder="Đáp án đúng"
            value={fix} onChange={(e) => setFix(e.target.value)} />
          <label className="sr-only" htmlFor={`note-${turnId}`}>Ghi chú</label>
          <textarea id={`note-${turnId}`} rows={2} maxLength={2000} placeholder="Ghi chú (không bắt buộc)"
            value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="fix-actions">
            <button type="button" className="btn small" onClick={() => setOpen(false)}>Huỷ</button>
            <button type="submit" className="btn small primary" disabled={busy || (!fix.trim() && !note.trim())}>Gửi sửa</button>
          </div>
        </form>
      )}
      {corrected.length > 0 && (
        <div className="muted small">
          {corrected.map((f) => (
            <div key={f.id}>Đã gửi: {f.corrected_answer ? `“${f.corrected_answer}”` : ""}{f.note ? ` (ghi chú: ${f.note})` : ""}</div>
          ))}
        </div>
      )}
      {err && <span className="err" role="alert">{err}</span>}
    </div>
  );
}
