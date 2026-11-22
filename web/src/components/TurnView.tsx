import { useState } from "react";
import { ANSWERED_BY, fmtSeconds, stageLabel } from "../lib/labels";
import type { TurnState } from "../lib/turn";
import type { Feedback } from "../lib/types";
import { Evidence, Notes, RagBadge, RagSources, hasEvidence } from "./Details";
import FeedbackBar from "./FeedbackBar";
import { Check, ChevronDown, ChevronRight, Spinner } from "./Icons";

// What the spinner says, from the stages seen so far. Perception and parsing run in parallel,
// so their events come in either order.
function pending(t: TurnState): string {
  const has = (n: string) => t.stages.some((s) => s.name === n);
  if (!has("started")) return "Đang gửi ảnh…";
  if (has("route")) return t.stages.some((s) => s.name === "route" && s.info.to === "fallback")
    ? "Đang trả lời bằng phương án dự phòng…" : "Đang viết câu trả lời…";
  if (has("engine")) return "Đang chuẩn bị câu trả lời…";
  if (!has("perception") && !has("parsed")) return "Đang đọc biển báo và hiểu câu hỏi…";
  if (!has("perception")) return "Đang đọc biển báo trong ảnh…";
  if (!has("parsed")) return "Đang hiểu câu hỏi…";
  return "Hệ luật đang suy luận…";
}

function LiveStages({ t }: { t: TurnState }) {
  const shown = t.stages.filter((s) => s.name !== "started" && s.name !== "route");
  return (
    <ul className="pills" data-testid="stages" aria-live="polite">
      {shown.map((s, i) => (
        <li key={i} className="pill" data-stage={s.name}>
          <span className="ok"><Check size={12} /></span>{stageLabel(s)}{s.t != null && <span className="t"> · {fmtSeconds(s.t)}</span>}
        </li>
      ))}
      <li className="pill pending"><Spinner size={12} />{pending(t)}</li>
    </ul>
  );
}

export default function TurnView({ t, showImage, selected, onSelect, onFeedback }: {
  t: TurnState;
  showImage: boolean; // the photo differs from the previous question's
  selected: boolean;
  onSelect: () => void;
  onFeedback: (f: Feedback) => void;
}) {
  const [open, setOpen] = useState(false);
  const r = t.result;
  const rag = !!r && r.basis.includes("rag");
  return (
    <article className="turn" data-testid="turn" data-phase={t.phase}>
      <div className="msg-user">
        {showImage && t.imageUrl && (
          <button type="button" className={`user-photo${selected ? " selected" : ""}`} onClick={onSelect} data-testid="user-photo"
            aria-label="Xem ảnh của câu hỏi này" title="Xem ảnh và các khung biển báo">
            <img src={t.imageUrl} alt="" />
          </button>
        )}
        <div className="bubble" onClick={onSelect}>{t.question}</div>
      </div>

      <div className="msg-bot">
        {t.phase === "streaming" && (
          <>
            <LiveStages t={t} />
            {t.streamText && (
              <div className="answer" data-testid="stream">{t.streamText}<span className="caret" aria-hidden /></div>
            )}
          </>
        )}
        {t.phase === "interrupted" && (
          <div className="notice warn" role="status">
            Mất kết nối với luồng trả lời. Đang lấy lại câu trả lời đã lưu…
            {t.streamText && <div className="answer" style={{ marginTop: 6 }}>{t.streamText}</div>}
          </div>
        )}
        {t.phase === "error" && <div className="notice bad" role="alert">Lỗi: {t.error}</div>}
        {r && t.phase === "done" && (
          <>
            {rag && <RagBadge />}
            <div className="answer" data-testid="answer">{r.answer}</div>
            <div className="stats" data-testid="stats">
              {[
                r.answered_by ? ANSWERED_BY[r.answered_by] ?? r.answered_by : null,
                r.seconds != null ? fmtSeconds(r.seconds) : null,
                r.cost_usd != null ? `$${r.cost_usd.toFixed(4)}` : null,
              ].filter(Boolean).join(" · ")}
            </div>
            <Notes t={r} signs={t.signs} />
            {rag && <RagSources t={r} />}
            {hasEvidence(r, t.stages) && (
              <>
                <button type="button" className="evidence-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
                  {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} Căn cứ và chứng minh
                </button>
                {open && <Evidence t={r} signs={t.signs} stages={t.stages} />}
              </>
            )}
            {t.turnId && <FeedbackBar turnId={t.turnId} answer={r.answer ?? ""} given={t.feedback} onSent={onFeedback} />}
          </>
        )}
      </div>
    </article>
  );
}
