// Shapes of the API's JSON (app/api/main.py: TurnOut, FeedbackOut; app/api/runner.py: stage events).

export type Confidence = "high" | "medium" | "low";

export interface SignBox {
  id: string;
  code: string | null;
  name: string | null;
  known: boolean;
  confidence: Confidence | string | null;
  value?: number | string | null;
  unit?: string | null;
  box: [number, number, number, number] | null; // original-photo pixels x0, y0, x1, y1
  plates?: string[];
  alternatives?: string[];
}

export interface Feedback {
  id: string;
  thumb: "up" | "down" | null;
  corrected_answer: string | null;
  note: string | null;
}

export interface ProofNode {
  type: "rule" | "fact" | "cite" | "naf" | "builtin" | "leaf";
  goal?: string | null;
  rule?: string | null;
  source?: { law_id: string; article_id: string } | null;
  children?: ProofNode[];
}

export interface Reason {
  sign_id?: string | null;
  truth: "true" | "false" | "unknown";
  detail?: string | null;
  proof?: ProofNode | null;
}

/** The engine's Answer (vqa/schemas.py), as the API's `proof` field. */
export interface EngineAnswer {
  verdict: string;
  value?: unknown;
  reasons?: Reason[];
  citations?: { law_id: string; article_id: string }[];
  uncertain_signs?: string[];
  note?: string | null;
  basis?: string[];
}

/** A law the RAG fallback used (never a rule citation). */
export interface RetrievedLaw {
  law_id: string;
  article_id: string;
  rank?: number | null;
  score?: number | null;
  text?: string | null;
}

export interface TurnOut {
  turn_id: string;
  session_id: string;
  status: "running" | "done" | "error" | string;
  question: string;
  understood_as?: string | null; // a follow-up, rewritten into the question that was answered
  image_sha256: string;
  answer: string | null;
  verdict: string | null;
  answered_by: string | null;
  basis: string[];
  citations: string[];
  signs: SignBox[];
  retrieved: RetrievedLaw[];
  proof: EngineAnswer | null;
  stages: Record<string, Record<string, unknown>>;
  cost_usd: number | null;
  seconds: number | null;
  error: string | null;
  feedback: Feedback[];
}

export interface SseEvent {
  event: string;
  data: string;
  id?: string;
}
