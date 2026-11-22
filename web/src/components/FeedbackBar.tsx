import { useState } from "react";
import { sendFeedback } from "../lib/api";
import type { Feedback } from "../lib/types";

export default function FeedbackBar({ turnId, given, onSent }: {
  turnId: string;
  given: Feedback[];
  onSent: (f: Feedback) => void;
}) {
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
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

  return (
    <div className="feedback" data-testid="feedback">
      <span className="muted">Câu trả lời này:</span>
      <button type="button" className={`btn small${thumb === "up" ? " on" : ""}`} disabled={busy}
        aria-pressed={thumb === "up"} onClick={() => send({ thumb: "up" })}>👍 Đúng</button>
      <button type="button" className={`btn small${thumb === "down" ? " on" : ""}`} disabled={busy}
        aria-pressed={thumb === "down"} onClick={() => send({ thumb: "down" })}>👎 Sai</button>
      <button type="button" className="btn small" disabled={busy} onClick={() => setOpen(!open)}>✏️ Sửa đáp án</button>
      {open && (
        <form onSubmit={async (e) => {
          e.preventDefault();
          if (!answer.trim() && !note.trim()) return;
          const ok = await send({ corrected_answer: answer.trim() || undefined, note: note.trim() || undefined });
          if (ok) { setAnswer(""); setNote(""); setOpen(false); }
        }}>
          <label className="sr-only" htmlFor={`fix-${turnId}`}>Đáp án đúng</label>
          <textarea id={`fix-${turnId}`} rows={2} maxLength={4000} placeholder="Đáp án đúng"
            value={answer} onChange={(e) => setAnswer(e.target.value)} />
          <label className="sr-only" htmlFor={`note-${turnId}`}>Ghi chú</label>
          <textarea id={`note-${turnId}`} rows={2} maxLength={2000} placeholder="Ghi chú (không bắt buộc)"
            value={note} onChange={(e) => setNote(e.target.value)} />
          <div><button type="submit" className="btn small primary" disabled={busy || (!answer.trim() && !note.trim())}>Gửi</button></div>
        </form>
      )}
      {corrected.length > 0 && (
        <div className="muted" style={{ width: "100%" }}>
          {corrected.map((f) => (
            <div key={f.id}>Đã gửi: {f.corrected_answer ? `“${f.corrected_answer}”` : ""}{f.note ? ` (ghi chú: ${f.note})` : ""}</div>
          ))}
        </div>
      )}
      {thumb && <span className="muted" role="status">Cảm ơn bạn đã đánh giá.</span>}
      {err && <span className="err" role="alert">{err}</span>}
    </div>
  );
}
