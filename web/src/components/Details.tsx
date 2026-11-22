import { CONFIDENCE } from "../lib/labels";
import type { SignBox, TurnOut } from "../lib/types";
import ProofTree from "./ProofTree";

export const RAG_BADGE = "Trả lời bằng RAG – chưa được hệ luật kiểm chứng";

function Notes({ t, signs }: { t: TurnOut; signs: SignBox[] }) {
  const notes: { kind: "warn" | "info"; body: React.ReactNode; id: string }[] = [];
  const proof = t.proof;
  const uncertain = proof?.uncertain_signs ?? [];
  const label = (id: string) => {
    const i = signs.findIndex((s) => s.id === id);
    return i >= 0 ? `biển ${i + 1} (${signs[i].code ?? "?"})` : id;
  };
  if (t.verdict === "unknown" || t.answered_by === "not_decided") {
    const why = (proof?.reasons ?? []).filter((r) => r.truth === "unknown" && r.detail).map((r) => r.detail as string);
    notes.push({
      id: "unknown", kind: "warn",
      body: (
        <>
          <strong>Chưa đủ dữ kiện để kết luận.</strong>{" "}
          {t.answered_by === "not_decided"
            ? "Hệ luật chưa quyết định được và chế độ dự phòng đang tắt."
            : "Thiếu thông tin trong ảnh hoặc câu hỏi (thời gian, làn đường, loại xe, …)."}
          {why.length > 0 && <ul>{why.slice(0, 5).map((w, i) => <li key={i}>{w}</li>)}</ul>}
        </>
      ),
    });
  }
  if (t.basis.includes("reading_choice")) {
    notes.push({
      id: "reading", kind: "warn",
      body: (
        <>
          <strong>Có biển đọc chưa chắc.</strong> Câu trả lời dùng cách đọc có độ tin cậy cao nhất
          {uncertain.length ? ` cho ${uncertain.map(label).join(", ")}` : ""}.
          {proof?.note && <div className="muted">{proof.note}</div>}
        </>
      ),
    });
  } else if (uncertain.length && t.answered_by === "rules") {
    notes.push({
      id: "uncertain", kind: "warn",
      body: <>Không đọc rõ {uncertain.map(label).join(", ")}; kết luận có thể thay đổi nếu đọc được biển này.</>,
    });
  }
  const low = signs.map((s, i) => ({ s, n: i + 1 })).filter((x) => x.s.confidence === "low");
  if (low.length) {
    notes.push({
      id: "low", kind: "warn",
      body: (
        <>
          Độ tin cậy {CONFIDENCE.low} khi đọc: {low.map((x) => `biển ${x.n} (${x.s.code ?? "?"})`).join(", ")}.
          Hãy kiểm tra lại khung trên ảnh.
        </>
      ),
    });
  }
  if (t.basis.includes("non_standard_plate")) {
    notes.push({ id: "local", kind: "info", body: <>Dựa trên biển phụ không theo QCVN 41 (nội dung được giữ nguyên văn).</> });
  }
  if (t.answered_by === "fallback" && !t.basis.includes("rag")) {
    notes.push({ id: "fb", kind: "warn", body: <>Trả lời bởi mô hình dự phòng – chưa được hệ luật kiểm chứng.</> });
  }
  if (!notes.length) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }} data-testid="notes">
      {notes.map((n) => <div key={n.id} className={`notice ${n.kind}`}>{n.body}</div>)}
    </div>
  );
}

export default function Details({ t, signs }: { t: TurnOut; signs: SignBox[] }) {
  const rag = t.basis.includes("rag");
  return (
    <>
      <Notes t={t} signs={signs} />
      {rag && (
        <div className="rag-box" data-testid="rag">
          <div className="rag-badge" role="note">⚠️ {RAG_BADGE}</div>
          {t.retrieved.length > 0 ? (
            <>
              <div className="section-title" style={{ marginTop: 10 }}>Điều luật RAG đã tìm và dùng</div>
              {t.retrieved.map((r, i) => (
                <details key={`${r.law_id}-${r.article_id}-${i}`}>
                  <summary>
                    <strong>{r.law_id} – {r.article_id}</strong>
                    <span className="muted">
                      {r.rank != null ? ` · hạng ${r.rank}` : ""}
                      {r.score != null ? ` · điểm ${Number(r.score).toFixed(3)}` : ""}
                    </span>
                  </summary>
                  {r.text ? <div className="law-text">{r.text}</div> : <p className="muted">Không có văn bản.</p>}
                </details>
              ))}
            </>
          ) : (
            <p className="muted">RAG không trả về điều luật nào.</p>
          )}
        </div>
      )}
      {t.citations.length > 0 && (
        <div>
          <div className="section-title">Căn cứ của hệ luật</div>
          <div className="chips" data-testid="citations">
            {t.citations.map((c) => <span key={c} className="chip">{c}</span>)}
          </div>
        </div>
      )}
      {t.proof && <ProofTree proof={t.proof} signs={signs} />}
    </>
  );
}
