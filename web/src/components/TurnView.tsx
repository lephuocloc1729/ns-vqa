import { ANSWERED_BY, VERDICT, fmtSeconds, stageLabel } from "../lib/labels";
import type { TurnState } from "../lib/turn";
import type { Feedback } from "../lib/types";
import Details from "./Details";
import FeedbackBar from "./FeedbackBar";

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

function Stages({ t }: { t: TurnState }) {
  const live = t.phase === "streaming";
  const list = (
    <ul className="stages" data-testid="stages">
      {t.stages.map((s, i) => (
        <li key={i} data-stage={s.name}>
          <span>✓ {stageLabel(s)}</span>
          <span className="t">{fmtSeconds(s.t)}</span>
        </li>
      ))}
      {live && (
        <li className="pending">
          <span><span className="spinner" aria-hidden />{pending(t)}</span>
        </li>
      )}
    </ul>
  );
  if (live || !t.stages.length) return live ? list : null;
  return (
    <details className="block">
      <summary className="muted" style={{ fontWeight: 400 }}>
        {t.stages.length > 1 ? `${t.stages.length} bước` : "Đã trả lời"}
        {t.result?.seconds != null ? ` · ${fmtSeconds(t.result.seconds)}` : ""}
        {t.result?.cost_usd != null ? ` · $${t.result.cost_usd.toFixed(4)}` : ""}
      </summary>
      {list}
    </details>
  );
}

export default function TurnView({ t, selected, onSelect, onFeedback }: {
  t: TurnState;
  selected: boolean;
  onSelect: () => void;
  onFeedback: (f: Feedback) => void;
}) {
  const r = t.result;
  return (
    <article className={`card turn${selected ? " selected" : ""}`} data-testid="turn" data-phase={t.phase}>
      <div className="q">
        {t.imageUrl && (
          <button type="button" className="q-thumb" onClick={onSelect} title="Xem ảnh của câu hỏi này"
            aria-label="Xem ảnh của câu hỏi này">
            <img src={t.imageUrl} alt="" style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: 5 }} />
          </button>
        )}
        <div className="q-text">{t.question}</div>
      </div>
      <Stages t={t} />
      {t.phase === "streaming" && (
        <div className="answer" aria-live="polite" data-testid="stream">
          {t.streamText}
          <span className="caret" aria-hidden />
        </div>
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
          <div className="answer" data-testid="answer">{r.answer}</div>
          <div className="badges">
            {r.verdict && <span className={`badge ${r.verdict}`}>{VERDICT[r.verdict] ?? r.verdict}</span>}
            {r.answered_by && <span className="badge">{ANSWERED_BY[r.answered_by] ?? r.answered_by}</span>}
          </div>
          <Details t={r} signs={t.signs} />
          {t.turnId && <FeedbackBar turnId={t.turnId} given={t.feedback} onSent={onFeedback} />}
        </>
      )}
    </article>
  );
}
