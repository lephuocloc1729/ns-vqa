import { ANSWERED_BY, VERDICT, fmtSeconds, stageLabel } from "../lib/labels";
import type { TurnState } from "../lib/turn";
import type { Feedback } from "../lib/types";
import Details from "./Details";
import FeedbackBar from "./FeedbackBar";

const NEXT: Record<string, string> = {
  "": "Đang gửi ảnh…",
  started: "Đang đọc biển báo trong ảnh…",
  perception: "Đang hiểu câu hỏi…",
  parsed: "Hệ luật đang suy luận…",
  engine: "Đang chuẩn bị câu trả lời…",
  route: "Đang viết câu trả lời…",
};

function Stages({ t }: { t: TurnState }) {
  const last = t.stages.length ? t.stages[t.stages.length - 1].name : "";
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
          <span><span className="spinner" aria-hidden />{NEXT[last] ?? "Đang xử lý…"}</span>
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
