import { describe, expect, it } from "vitest";
import { newTurn, turnFromStored, turnReducer, type TurnAction, type TurnState } from "./turn";
import type { TurnOut } from "./types";

const ev = (event: string, data: Record<string, unknown> = {}): TurnAction => ({ type: "event", event, data });
const run = (actions: TurnAction[], s: TurnState = newTurn("k", "Ô tô có được vào không?", "blob:x")) =>
  actions.reduce(turnReducer, s);

const stored = (over: Partial<TurnOut> = {}): TurnOut => ({
  turn_id: "t1", session_id: "s1", status: "done", question: "Ô tô có được vào không?", image_sha256: "a".repeat(64),
  answer: "Không. Biển P.103a cấm ô tô.", verdict: "no", answered_by: "rules", basis: ["rules"],
  citations: ["QCVN 41:2024/BGTVT B.3"], signs: [{ id: "s1", code: "P.103a", name: "Cấm xe ô tô", known: true,
  confidence: "high", box: [1, 2, 3, 4] }], retrieved: [], proof: null, stages: {}, cost_usd: 0.01,
  seconds: 12.5, error: null, feedback: [], ...over,
});

const sign = { id: "s1", code: "P.103a", name: null, known: true, confidence: "low", box: [10, 20, 110, 120] };

describe("turnReducer", () => {
  it("records ids, stages with times, signs and the photo size from the events", () => {
    const s = run([
      ev("turn", { turn_id: "t1", session_id: "s1", image_sha256: "abc" }),
      ev("started", { image_size: [640, 480], t: 0.001 }),
      ev("perception", { ok: true, signs: [sign], t: 3.2 }),
      ev("parsed", { status: "ok", program: {}, t: 3.5 }),
      ev("engine", { verdict: "no", t: 4.0 }),
      ev("route", { to: "writer", t: 4.1 }),
    ]);
    expect(s.turnId).toBe("t1");
    expect(s.sessionId).toBe("s1");
    expect(s.imageSize).toEqual([640, 480]);
    expect(s.signs).toHaveLength(1);
    expect(s.stages.map((x) => [x.name, x.t])).toEqual([
      ["started", 0.001], ["perception", 3.2], ["parsed", 3.5], ["engine", 4.0], ["route", 4.1],
    ]);
    expect(s.stages[3].info).toEqual({ verdict: "no" }); // `t` is not repeated in info
    expect(s.phase).toBe("streaming");
  });

  it("appends tokens, clears them on token_reset, and lets the answer event replace the text", () => {
    let s = run([ev("token", { text: "Có, " }), ev("token", { text: "được" })]);
    expect(s.streamText).toBe("Có, được");
    s = run([ev("token_reset", { reason: "retry" })], s);
    expect(s.streamText).toBe("");
    s = run([ev("token", { text: "Khôn" }), ev("answer", stored() as unknown as Record<string, unknown>)], s);
    expect(s.phase).toBe("done");
    expect(s.streamText).toBe("");
    expect(s.result?.answer).toBe("Không. Biển P.103a cấm ô tô.");
    expect(s.stages.at(-1)).toMatchObject({ name: "answer", t: 12.5 });
  });

  it("ignores tokens and errors that arrive after the answer", () => {
    const s = run([ev("answer", stored() as unknown as Record<string, unknown>), ev("token", { text: "x" }),
      ev("error", { error: "late" }), { type: "stream_end" }, { type: "fail", error: "late" }]);
    expect(s.phase).toBe("done");
    expect(s.streamText).toBe("");
    expect(s.error).toBeNull();
  });

  it("shows a server error event", () => {
    const s = run([ev("turn", { turn_id: "t1", session_id: "s1" }), ev("token", { text: "Có" }),
      ev("error", { turn_id: "t1", error: "the spend limit for this server was reached" })]);
    expect(s.phase).toBe("error");
    expect(s.error).toContain("spend limit");
    expect(run([{ type: "stream_end" }], s).phase).toBe("error");
  });

  it("shows an HTTP or network failure before any event", () => {
    const s = run([{ type: "fail", error: "Ảnh quá lớn." }]);
    expect(s.phase).toBe("error");
    expect(s.error).toBe("Ảnh quá lớn.");
  });

  it("marks a stream that closes without answer or error as interrupted, then recovers from the stored turn", () => {
    let s = run([ev("turn", { turn_id: "t1", session_id: "s1" }), ev("started", { t: 0 }),
      ev("token", { text: "Có" }), { type: "stream_end" }]);
    expect(s.phase).toBe("interrupted");
    expect(s.streamText).toBe("Có");
    s = run([{ type: "loaded", turn: stored({ status: "running", answer: null }) }], s);
    expect(s.phase).toBe("interrupted"); // still running on the server
    s = run([{ type: "loaded", turn: stored() }], s);
    expect(s.phase).toBe("done");
    expect(s.result?.verdict).toBe("no");
    expect(s.streamText).toBe("");
  });

  it("recovers a stored error after a drop", () => {
    const s = run([{ type: "stream_end" }, { type: "loaded", turn: stored({ status: "error", error: "boom", answer: null }) }]);
    expect(s.phase).toBe("error");
    expect(s.error).toBe("boom");
  });

  it("keeps the perception signs when the answer has none", () => {
    const s = run([ev("perception", { signs: [sign] }), ev("answer", stored({ signs: [] }) as unknown as Record<string, unknown>)]);
    expect(s.signs).toEqual([sign]);
  });

  it("ignores unknown events and done", () => {
    const before = run([ev("started", { t: 0 })]);
    expect(run([ev("mystery", { a: 1 }), ev("done", { turn_id: "t1" })], before)).toEqual(before);
  });

  it("builds a turn from history, with its feedback, and adds new feedback", () => {
    const fb = { id: "f1", thumb: "up" as const, corrected_answer: null, note: null };
    let s = turnFromStored("t1", stored({ feedback: [fb] }), "/v1/images/aaa");
    expect(s.phase).toBe("done");
    expect(s.imageUrl).toBe("/v1/images/aaa");
    expect(s.feedback).toEqual([fb]);
    s = turnReducer(s, { type: "feedback", feedback: { ...fb, id: "f2", thumb: "down" } });
    expect(s.feedback.map((f) => f.id)).toEqual(["f1", "f2"]);
  });
});
