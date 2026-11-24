// The rule engine's proof at three levels, all folded by default (owner, 2026-11-24):
//   1. Các bước suy luận: each step of the proof, its Prolog form beside what it means (app/api/proof_view.py)
//   2. Luật trong cơ sở tri thức: the rules that concluded, as written in kb/, with a reading
//   3. Cây chứng minh đầy đủ: the raw proof tree, as the engine returned it
// Every row comes from the proof; no model writes any of it.
import { TRUTH } from "../lib/labels";
import type { EngineAnswer, ProofNode, ProofStep, ReasonView, SignBox } from "../lib/types";

const APPLIES: Record<string, string> = { true: "áp dụng", false: "không áp dụng", unknown: "chưa rõ" };

const TYPE: Record<string, string> = {
  rule: "luật", fact: "dữ kiện", cite: "trích dẫn", naf: "phủ định", builtin: "tính toán", leaf: "kiểm tra",
};

function Node({ node, depth }: { node: ProofNode; depth: number }) {
  const label = (
    <>
      <span className="ptype">{TYPE[node.type] ?? node.type}</span>
      {node.rule && <code>{node.rule}</code>}
      {node.rule && node.goal ? " · " : null}
      {node.goal && <code>{node.goal}</code>}
      {node.source && <span className="chip" style={{ marginLeft: 6 }}>{node.source.law_id} {node.source.article_id}</span>}
    </>
  );
  const kids = node.children ?? [];
  if (!kids.length) return <li>{label}</li>;
  return (
    <li>
      <details open={depth < 1}>
        <summary>{label}</summary>
        <ul>
          {kids.map((c, i) => <Node key={i} node={c} depth={depth + 1} />)}
        </ul>
      </details>
    </li>
  );
}

function resultClass(r: string): string {
  if (r.startsWith("✓")) return "truth-true";
  if (r.startsWith("✗")) return "truth-false";
  if (r.startsWith("?")) return "truth-unknown";
  return "step-result-word";
}

function StepRow({ s, last }: { s: ProofStep; last: boolean }) {
  const cells = (
    <>
      <code className="step-rule">{s.rule}</code>
      <span className="step-text">
        {s.text}
        {s.cite && s.cite.length > 0 && <span className="step-cite"> — {s.cite.join("; ")}</span>}
      </span>
      <span className={`step-result ${resultClass(s.result)}`}>{s.result}</span>
    </>
  );
  const cls = `step${s.decisive ? " decisive" : ""}${last ? " conclusion" : ""}`;
  if (s.detail && s.detail.length) {
    return (
      <li className={cls}>
        <details>
          <summary className="step-grid">{cells}</summary>
          <ul className="steps sub">
            {s.detail.map((d, i) => <StepRow key={i} s={d} last={false} />)}
          </ul>
        </details>
      </li>
    );
  }
  return <li className={cls}><div className="step-grid">{cells}</div></li>;
}

function Steps({ views }: { views: ReasonView[] }) {
  return (
    <div className="proof-steps">
      {views.map((v, i) => (
        <div key={i} className="reason-view">
          <div className="reason-title">
            {v.title ?? "Quy tắc chung"}
            <span className={`truth-${v.truth}`}> · {APPLIES[v.truth] ?? v.truth}</span>
          </div>
          <div className="step-head" aria-hidden="true">
            <span>Quy tắc (Prolog)</span><span>Nghĩa là</span><span>Kết quả</span>
          </div>
          <ul className="steps">
            {v.steps.map((s, j) => <StepRow key={j} s={s} last={j === v.steps.length - 1} />)}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Rules({ views }: { views: ReasonView[] }) {
  const seen = new Set<string>();
  const cards = views.flatMap((v) => v.rules).filter((c) => (seen.has(c.name) ? false : (seen.add(c.name), true)));
  if (!cards.length) return <p className="muted">Chưa có diễn giải cho các luật này; xem cây chứng minh đầy đủ.</p>;
  return (
    <div className="rule-cards">
      {cards.map((c) => (
        <div key={c.name} className="rule-card">
          <pre className="rule-clause"><code>{c.clause ?? c.name}</code></pre>
          <p className="rule-reading">{c.reading}</p>
        </div>
      ))}
    </div>
  );
}

export default function ProofTree({ proof, signs, explanation }:
  { proof: EngineAnswer; signs: SignBox[]; explanation?: ReasonView[] | null }) {
  const reasons = proof.reasons ?? [];
  if (!reasons.length) return null;
  const numberOf = (id?: string | null) => {
    const i = signs.findIndex((s) => s.id === id);
    return i >= 0 ? `${i + 1}. ${signs[i].code ?? ""}` : id ?? "";
  };
  const views = explanation ?? [];
  return (
    <div className="proof-levels">
      <div className="section-title">Chứng minh của hệ luật</div>
      {views.length > 0 && (
        <details className="block" data-testid="proof-steps">
          <summary>Các bước suy luận</summary>
          <Steps views={views} />
        </details>
      )}
      {views.length > 0 && (
        <details className="block" data-testid="proof-rules">
          <summary>Luật trong cơ sở tri thức</summary>
          <Rules views={views} />
        </details>
      )}
      <details className="block" data-testid="proof">
        <summary>Cây chứng minh đầy đủ (Prolog, {reasons.length} lý do)</summary>
        <div className="proof">
          <ul>
            {reasons.map((r, i) => (
              <li key={i} style={{ marginTop: 6 }}>
                <div>
                  {r.sign_id && <strong>Biển {numberOf(r.sign_id)}: </strong>}
                  <span className={`truth-${r.truth}`}>{TRUTH[r.truth] ?? r.truth}</span>
                  {r.detail && <span className="muted"> — {r.detail}</span>}
                </div>
                {r.proof && <ul><Node node={r.proof} depth={0} /></ul>}
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}
