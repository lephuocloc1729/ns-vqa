import { describe, expect, it } from "vitest";
import { SseParser, readSse } from "./sse";

const all = (p: SseParser, chunks: string[]) => chunks.flatMap((c) => p.push(c));

describe("SseParser", () => {
  it("parses named events with JSON data", () => {
    const evs = new SseParser().push('event: turn\ndata: {"turn_id":"t1"}\n\nevent: done\ndata: {}\n\n');
    expect(evs).toEqual([
      { event: "turn", data: '{"turn_id":"t1"}' },
      { event: "done", data: "{}" },
    ]);
  });

  it("joins events split across chunks at any byte", () => {
    const text = 'event: token\ndata: {"text":"Có"}\n\nevent: token\ndata: {"text":"."}\n\n';
    for (let cut = 1; cut < text.length; cut++) {
      const evs = all(new SseParser(), [text.slice(0, cut), text.slice(cut)]);
      expect(evs.map((e) => e.data)).toEqual(['{"text":"Có"}', '{"text":"."}']);
    }
  });

  it("handles CRLF and CR line endings, including a CRLF split between chunks", () => {
    expect(new SseParser().push("event: a\r\ndata: 1\r\n\r\n")).toEqual([{ event: "a", data: "1" }]);
    expect(new SseParser().push("event: b\rdata: 2\r\r")).toEqual([{ event: "b", data: "2" }]);
    const p = new SseParser();
    expect(all(p, ["event: c\r", "\ndata: 3\r", "\n\r", "\n"])).toEqual([{ event: "c", data: "3" }]);
  });

  it("ignores comments (keep-alives) and unknown fields", () => {
    const evs = new SseParser().push(": keep-alive\n\nretry: 10\nfoo: bar\ndata: x\n\n");
    expect(evs).toEqual([{ event: "message", data: "x" }]);
  });

  it("joins several data lines with newlines and strips one leading space only", () => {
    const evs = new SseParser().push("data:  a\ndata:b\n\n");
    expect(evs).toEqual([{ event: "message", data: " a\nb" }]);
  });

  it("dispatches nothing for a blank line without data, and resets the event name", () => {
    const evs = new SseParser().push("event: x\n\ndata: y\n\n");
    expect(evs).toEqual([{ event: "message", data: "y" }]);
  });

  it("keeps the last id", () => {
    const evs = new SseParser().push("id: 7\ndata: a\n\ndata: b\n\n");
    expect(evs.map((e) => e.id)).toEqual(["7", "7"]);
  });

  it("drops an event whose stream ends before its blank line", () => {
    const p = new SseParser();
    expect(p.push('event: answer\ndata: {"a":1}\n')).toEqual([]);
    expect(p.end()).toEqual([]);
  });
});

function streamOf(chunks: Uint8Array[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(c) {
      chunks.forEach((x) => c.enqueue(x));
      c.close();
    },
  });
}

describe("readSse", () => {
  it("decodes UTF-8 split inside a multi-byte character", async () => {
    const bytes = new TextEncoder().encode('event: token\ndata: {"text":"Đường cấm"}\n\n');
    const cut = bytes.indexOf(0xc4) + 1; // inside "Đ"
    const got: string[] = [];
    await readSse(streamOf([bytes.slice(0, cut), bytes.slice(cut)]), (e) => got.push(JSON.parse(e.data).text));
    expect(got).toEqual(["Đường cấm"]);
  });

  it("rejects when the body errors mid-stream, after delivering the complete events", async () => {
    const enc = new TextEncoder();
    let pulls = 0;
    const body = new ReadableStream<Uint8Array>({
      pull(c) {
        if (pulls++ === 0) c.enqueue(enc.encode("event: started\ndata: {}\n\nevent: tok"));
        else c.error(new TypeError("network error"));
      },
    });
    const got: string[] = [];
    await expect(readSse(body, (e) => got.push(e.event))).rejects.toThrow("network error");
    expect(got).toEqual(["started"]);
  });
});
