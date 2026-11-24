// Which notes an answer needs, from the engine's answer (the API's `proof`) and the signs read.

import type { EngineAnswer, ProofNode, SignBox, TurnOut } from "./types";

/** The signs the answer rests on: those with a reason, plus those the engine flagged as uncertain. */
export function reliedSignIds(proof: EngineAnswer | null | undefined): Set<string> {
  const ids = new Set<string>();
  for (const r of proof?.reasons ?? []) if (r.sign_id) ids.add(r.sign_id);
  for (const id of proof?.uncertain_signs ?? []) ids.add(id);
  return ids;
}

/** Low-confidence signs (with their 1-based number) that the answer rests on. */
export function lowConfidenceRelied(signs: SignBox[], proof: EngineAnswer | null | undefined) {
  const relied = reliedSignIds(proof);
  return signs.map((s, i) => ({ s, n: i + 1 })).filter((x) => x.s.confidence === "low" && relied.has(x.s.id));
}

function* walk(node: ProofNode | null | undefined): Generator<ProofNode> {
  if (!node) return;
  yield node;
  for (const c of node.children ?? []) yield* walk(c);
}

// local_plate(s1,'CẤM XE 2 VÀ 3 BÁNH'), as the engine prints it (Prolog quoted atom)
const LOCAL_PLATE = /^local_plate\(\s*([^,\s]+)\s*,\s*'((?:[^'\\]|\\.)*)'\s*\)$/;

/** The non-standard (local) plates the proof used, with their verbatim text. */
export function localPlates(proof: EngineAnswer | null | undefined): { signId: string; text: string }[] {
  const out: { signId: string; text: string }[] = [];
  const seen = new Set<string>();
  for (const r of proof?.reasons ?? []) {
    for (const n of walk(r.proof)) {
      const m = LOCAL_PLATE.exec(n.goal ?? "");
      if (!m) continue;
      const text = m[2].replace(/\\(.)/g, "$1");
      const key = `${m[1]}|${text}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.push({ signId: m[1], text });
      }
    }
  }
  return out;
}

/** A question the parser found no road-sign question in, and nothing else answered (no GPU connected).
 *  The answer text already says so (app/api/main.py, SCOPE_TEXT), so no "not enough data" note. */
export function outOfScope(t: Pick<TurnOut, "answered_by" | "stages">): boolean {
  return t.answered_by === "not_decided" && t.stages?.parser?.status === "out_of_scope";
}
