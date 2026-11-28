// The API client. Paths are relative: the Vite dev server (and nginx later) forwards /v1 to the API.

import { readSse } from "./sse";
import type { Feedback, TurnOut } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const HTTP_TEXT: Record<number, string> = {
  413: "Ảnh quá lớn.",
  415: "Không đọc được ảnh. Chỉ nhận ảnh JPEG, PNG hoặc WEBP.",
  404: "Không tìm thấy dữ liệu trên máy chủ.",
  503: "Máy chủ tạm thời không trả lời được (có thể đã hết hạn mức chi phí).",
};

async function errorFrom(res: Response): Promise<ApiError> {
  let detail = "";
  try {
    const j = await res.json();
    detail = typeof j?.detail === "string" ? j.detail : "";
  } catch {
    /* not JSON */
  }
  const text = HTTP_TEXT[res.status] ?? `Lỗi máy chủ (${res.status}).`;
  return new ApiError(res.status, detail ? `${text} (${detail})` : text);
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw await errorFrom(res);
  return (await res.json()) as T;
}

export const imageUrl = (sha: string) => `/v1/images/${sha}`;

export interface DemoPhoto {
  sha256: string;
  caption: string;
  questions: string[];
}

export const demoThumbUrl = (sha: string) => `/v1/demo/${sha}/thumb`;

/** The demo photos the admin site has switched on (none when off, or when the server is older). */
export const getDemo = () =>
  getJson<{ enabled: boolean; items: DemoPhoto[] }>("/v1/demo").then((d) => (d.enabled ? d.items : []), () => []);

export const getTurn = (id: string) => getJson<TurnOut>(`/v1/turns/${encodeURIComponent(id)}`);

export const getTurns = (sessionId: string) =>
  getJson<TurnOut[]>(`/v1/sessions/${encodeURIComponent(sessionId)}/turns`);

export function sendFeedback(
  turnId: string,
  body: { thumb?: "up" | "down"; corrected_answer?: string; note?: string },
): Promise<Feedback> {
  return getJson<Feedback>(`/v1/turns/${encodeURIComponent(turnId)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * POST /v1/ask/stream, read with fetch and a stream reader (EventSource cannot upload).
 * Calls onEvent for every event with its parsed JSON; resolves when the body closes.
 * Throws ApiError for an HTTP error, or the fetch error for a network failure.
 */
export async function askStream(
  image: Blob,
  question: string,
  sessionId: string | null,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append("image", image, (image as File).name || "photo.jpg");
  form.append("question", question);
  if (sessionId) form.append("session_id", sessionId);
  const res = await fetch("/v1/ask/stream", {
    method: "POST", body: form, signal, headers: { Accept: "text/event-stream" },
  });
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) throw new ApiError(0, "Trình duyệt không đọc được luồng trả lời.");
  await readSse(res.body, (ev) => {
    let data: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse(ev.data);
      if (parsed && typeof parsed === "object") data = parsed;
    } catch {
      return; // a malformed event is skipped; the final answer can still be fetched
    }
    onEvent(ev.event, data);
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** After a dropped stream: fetch the stored turn until it is finished (the API keeps running). */
export async function recoverTurn(turnId: string, tries = 90, delayMs = 2000): Promise<TurnOut> {
  let last: TurnOut | null = null;
  for (let i = 0; i < tries; i++) {
    last = await getTurn(turnId);
    if (last.status !== "running") return last;
    await sleep(delayMs);
  }
  return last as TurnOut;
}
