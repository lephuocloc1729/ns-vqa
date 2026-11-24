import { describe, expect, it } from "vitest";
import { localPlates, lowConfidenceRelied, outOfScope, reliedSignIds } from "./notes";
import type { EngineAnswer, SignBox } from "./types";

const sign = (id: string, confidence: string): SignBox => ({
  id, code: id === "s1" ? "P.103a" : "I.417a", name: null, known: true, confidence, box: [0, 0, 1, 1],
});

const proof = (over: Partial<EngineAnswer> = {}): EngineAnswer => ({ verdict: "no", reasons: [], ...over });

describe("notes", () => {
  it("relies on the signs with a reason and the uncertain signs", () => {
    const p = proof({ reasons: [{ sign_id: "s1", truth: "true" }, { truth: "unknown" }], uncertain_signs: ["s3"] });
    expect([...reliedSignIds(p)].sort()).toEqual(["s1", "s3"]);
    expect(reliedSignIds(null).size).toBe(0);
  });

  it("warns about a low-confidence sign only when the answer rests on it", () => {
    const signs = [sign("s1", "high"), sign("s2", "low")];
    expect(lowConfidenceRelied(signs, proof({ reasons: [{ sign_id: "s1", truth: "true" }] }))).toEqual([]);
    const relied = lowConfidenceRelied(signs, proof({ reasons: [{ sign_id: "s2", truth: "true" }] }));
    expect(relied.map((x) => x.n)).toEqual([2]);
    expect(lowConfidenceRelied(signs, proof({ uncertain_signs: ["s2"] })).map((x) => x.n)).toEqual([2]);
    expect(lowConfidenceRelied(signs, null)).toEqual([]); // RAG or fallback answers: no rule reasons
  });

  it("reads the local plates' text from the proof, once each, unescaping quotes", () => {
    const node = (goal: string) => ({ type: "fact" as const, goal, children: [] });
    const p = proof({
      reasons: [
        { sign_id: "s1", truth: "true", proof: { type: "rule", rule: "forbids", children: [
          node("local_plate(s1,'CẤM XE 2 VÀ 3 BÁNH')"),
          { type: "rule", rule: "x", children: [node("local_plate(s1,'CẤM XE 2 VÀ 3 BÁNH')")] },
        ] } },
        { sign_id: "s2", truth: "true", proof: node("local_plate(s2,'XE \\'A\\' 6H-9H')") },
        { sign_id: "s3", truth: "true", proof: node("sign(s3, p103a)") },
      ],
    });
    expect(localPlates(p)).toEqual([
      { signId: "s1", text: "CẤM XE 2 VÀ 3 BÁNH" },
      { signId: "s2", text: "XE 'A' 6H-9H" },
    ]);
    expect(localPlates(null)).toEqual([]);
  });

  it("knows an out-of-scope question nobody answered", () => {
    const parser = (status: string) => ({ parser: { status } });
    expect(outOfScope({ answered_by: "not_decided", stages: parser("out_of_scope") })).toBe(true);
    expect(outOfScope({ answered_by: "not_decided", stages: parser("ok") })).toBe(false);       // undecided road-sign question
    expect(outOfScope({ answered_by: "fallback", stages: parser("out_of_scope") })).toBe(false); // the RAG answered it
    expect(outOfScope({ answered_by: "not_decided", stages: {} })).toBe(false);
  });
});
