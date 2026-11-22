// A small server-sent-events parser (https://html.spec.whatwg.org/multipage/server-sent-events.html).
// EventSource can only GET, and the ask endpoint takes an upload, so the stream is read with
// fetch and fed through this parser chunk by chunk.

import type { SseEvent } from "./types";

export class SseParser {
  private buf = "";
  private event = "";
  private data: string[] = [];
  private id: string | undefined;
  private skipLF = false;

  /** Feed decoded text; returns the events completed by it. */
  push(text: string): SseEvent[] {
    this.buf += text;
    const out: SseEvent[] = [];
    for (;;) {
      // a line ending in a lone \r at the end of a chunk may be the first half of \r\n
      if (this.skipLF && this.buf.startsWith("\n")) this.buf = this.buf.slice(1);
      if (this.buf.length) this.skipLF = false;
      const m = /\r\n|\n|\r/.exec(this.buf);
      if (!m) break;
      const line = this.buf.slice(0, m.index);
      this.buf = this.buf.slice(m.index + m[0].length);
      if (m[0] === "\r" && this.buf.length === 0) this.skipLF = true;
      const ev = this.line(line);
      if (ev) out.push(ev);
    }
    return out;
  }

  /** At end of stream: an event without its closing blank line is dropped, as the spec says. */
  end(): SseEvent[] {
    this.buf = "";
    this.skipLF = false;
    this.event = "";
    this.data = [];
    return [];
  }

  private line(line: string): SseEvent | null {
    if (line === "") {
      if (this.data.length === 0) {
        this.event = "";
        return null;
      }
      const ev: SseEvent = { event: this.event || "message", data: this.data.join("\n") };
      if (this.id !== undefined) ev.id = this.id;
      this.event = "";
      this.data = [];
      return ev;
    }
    if (line.startsWith(":")) return null; // comment (the API's keep-alive)
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.event = value;
    else if (field === "data") this.data.push(value);
    else if (field === "id" && !value.includes("\0")) this.id = value;
    return null;
  }
}

/** Read a fetch body as SSE; calls onEvent for each event, resolves when the stream ends. */
export async function readSse(body: ReadableStream<Uint8Array>, onEvent: (ev: SseEvent) => void): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = new SseParser();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const ev of parser.push(decoder.decode(value, { stream: true }))) onEvent(ev);
    }
    for (const ev of parser.push(decoder.decode())) onEvent(ev);
    parser.end();
  } finally {
    reader.releaseLock();
  }
}
