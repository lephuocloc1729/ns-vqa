// The state of one question/answer turn, built from the stream's events (or from a stored turn).
// The final `answer` event is authoritative: it replaces whatever text has streamed.

import type { Feedback, SignBox, TurnOut } from "./types";

export type Phase = "streaming" | "done" | "error" | "interrupted";

export interface Stage {
  name: string; // started | perception | parsed | engine | route | answer
  t: number | null; // seconds since the pipeline started
  info: Record<string, unknown>;
}

export interface TurnState {
  key: string; // local id, stable before the server's turn id arrives
  phase: Phase;
  question: string;
  imageUrl: string | null;
  turnId: string | null;
  sessionId: string | null;
  imageSha: string | null;
  imageSize: [number, number] | null;
  stages: Stage[];
  signs: SignBox[];
  streamText: string;
  result: TurnOut | null;
  error: string | null;
  feedback: Feedback[];
}

export type TurnAction =
  | { type: "event"; event: string; data: Record<string, unknown> }
  | { type: "stream_end" } // the body closed; without `answer` or `error` the stream was dropped
  | { type: "fail"; error: string } // HTTP or network error
  | { type: "loaded"; turn: TurnOut } // a stored turn (history, or recovery after a drop)
  | { type: "feedback"; feedback: Feedback };

export function newTurn(key: string, question: string, imageUrl: string | null): TurnState {
  return {
    key, phase: "streaming", question, imageUrl, turnId: null, sessionId: null, imageSha: null,
    imageSize: null, stages: [], signs: [], streamText: "", result: null, error: null, feedback: [],
  };
}

export function turnFromStored(key: string, t: TurnOut, imageUrl: string): TurnState {
  return turnReducer(newTurn(key, t.question, imageUrl), { type: "loaded", turn: t });
}

const STAGE_EVENTS = new Set(["started", "perception", "parsed", "engine", "route"]);

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function turnReducer(s: TurnState, a: TurnAction): TurnState {
  switch (a.type) {
    case "event":
      return onEvent(s, a.event, a.data);
    case "stream_end":
      return s.phase === "streaming" ? { ...s, phase: "interrupted" } : s;
    case "fail":
      return s.phase === "done" ? s : { ...s, phase: "error", error: a.error };
    case "loaded":
      return fromStored(s, a.turn);
    case "feedback":
      return { ...s, feedback: [...s.feedback, a.feedback] };
  }
}

function onEvent(s: TurnState, event: string, d: Record<string, unknown>): TurnState {
  if (s.phase === "done" || s.phase === "error") return s; // nothing after the end counts
  if (event === "turn") {
    return {
      ...s,
      turnId: (d.turn_id as string) ?? s.turnId,
      sessionId: (d.session_id as string) ?? s.sessionId,
      imageSha: (d.image_sha256 as string) ?? s.imageSha,
    };
  }
  if (STAGE_EVENTS.has(event)) {
    const { t, ...info } = d;
    const next: TurnState = { ...s, stages: [...s.stages, { name: event, t: num(t), info }] };
    if (event === "started" && Array.isArray(d.image_size)) {
      next.imageSize = [Number(d.image_size[0]), Number(d.image_size[1])];
    }
    if (event === "perception" && Array.isArray(d.signs)) next.signs = d.signs as SignBox[];
    return next;
  }
  if (event === "token") return { ...s, streamText: s.streamText + String(d.text ?? "") };
  if (event === "token_reset") return { ...s, streamText: "" };
  if (event === "answer") return fromStored(s, d as unknown as TurnOut);
  if (event === "error") {
    return { ...s, phase: "error", error: String(d.error ?? "lỗi không rõ"), turnId: (d.turn_id as string) ?? s.turnId };
  }
  return s; // `done` and unknown events change nothing
}

function fromStored(s: TurnState, t: TurnOut): TurnState {
  const base: TurnState = {
    ...s,
    turnId: t.turn_id,
    sessionId: t.session_id,
    imageSha: t.image_sha256,
    question: t.question || s.question,
    signs: t.signs && t.signs.length ? t.signs : s.signs,
    feedback: t.feedback ?? s.feedback,
  };
  if (t.status === "done") {
    const stages = s.stages.some((x) => x.name === "answer")
      ? s.stages
      : [...s.stages, { name: "answer", t: t.seconds, info: { answered_by: t.answered_by } }];
    return { ...base, phase: "done", result: t, streamText: "", error: null, stages };
  }
  if (t.status === "error") return { ...base, phase: "error", error: t.error ?? "lỗi không rõ", result: null };
  return { ...base, phase: s.phase === "interrupted" ? "interrupted" : "streaming" }; // still running
}
