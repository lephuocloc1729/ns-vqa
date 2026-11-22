import { TRUTH } from "../lib/labels";
import type { EngineAnswer, ProofNode, SignBox } from "../lib/types";

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

export default function ProofTree({ proof, signs }: { proof: EngineAnswer; signs: SignBox[] }) {
  const reasons = proof.reasons ?? [];
  if (!reasons.length) return null;
  const numberOf = (id?: string | null) => {
    const i = signs.findIndex((s) => s.id === id);
    return i >= 0 ? `${i + 1}. ${signs[i].code ?? ""}` : id ?? "";
  };
  return (
    <details className="block" data-testid="proof">
      <summary>Chứng minh của hệ luật ({reasons.length} lý do)</summary>
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
  );
}
