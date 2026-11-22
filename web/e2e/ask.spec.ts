import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PHOTO = fileURLToPath(new URL("./fixtures/road.jpg", import.meta.url));

async function ask(page: Page, question: string) {
  await page.getByLabel("Câu hỏi", { exact: true }).fill(question);
  await page.getByRole("button", { name: "Hỏi", exact: true }).click();
}

test("ask, stream, boxes, citations, proof, feedback, RAG and history", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("fake-banner")).toContainText("pipeline giả");
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  // record every text the streaming box shows (a draft is on screen for only a few hundred ms)
  await page.evaluate(() => {
    const seen: string[] = ((window as unknown as { streamSeen: string[] }).streamSeen = []);
    new MutationObserver(() => {
      const el = document.querySelector('[data-testid="stream"]');
      const text = el?.textContent ?? "";
      if (el && seen[seen.length - 1] !== text) seen.push(text);
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await ask(page, "Xe ô tô có được đi vào đường này không?");

  const turn = page.getByTestId("turn").first();
  await expect(turn.locator('[data-stage="perception"]')).toContainText("2 biển báo");

  // the final answer event replaces the stream
  await expect(turn).toHaveAttribute("data-phase", "done");
  await expect(turn.getByTestId("answer")).toHaveText("Không. Biển số 1 (P.103a) cấm xe ô tô đi vào.");
  await expect(turn.getByTestId("citations")).toContainText("QCVN 41:2024/BGTVT B.3");
  // streaming: the first draft grew token by token, token_reset cleared it, the final text streamed
  const seen = await page.evaluate(() => (window as unknown as { streamSeen: string[] }).streamSeen);
  const draft = seen.findIndex((t) => t.includes("Có, xe ô tô"));
  const reset = seen.findIndex((t, i) => i > draft && t === "");
  const final = seen.findIndex((t, i) => i > reset && t.startsWith("Không."));
  expect(draft, JSON.stringify(seen)).toBeGreaterThan(0);
  expect(reset, JSON.stringify(seen)).toBeGreaterThan(draft);
  expect(final, JSON.stringify(seen)).toBeGreaterThan(reset);
  expect(seen.slice(final).some((t) => t.includes("Có,"))).toBe(false);
  // sign 2 is low-confidence but the answer does not rest on it: no note; who answered is in the stats line
  await expect(turn.getByTestId("notes")).toHaveCount(0);
  await expect(turn.getByTestId("stats")).toContainText("Hệ luật");
  await expect(turn.locator(".badge")).toHaveCount(0);

  // boxes: numbered, code and name on tap
  await expect(page.getByTestId("box-1")).toBeVisible();
  await page.getByTestId("box-2").click();
  await expect(page.getByTestId("sign-info")).toContainText("W.207a");
  await expect(page.getByTestId("sign-info")).toContainText("độ tin cậy thấp");

  // proof tree
  await turn.getByText("Chứng minh của hệ luật").click();
  await expect(turn.getByTestId("proof")).toContainText("forbids(s1, car, enter)");

  // feedback
  await turn.getByRole("button", { name: "👍 Đúng" }).click();
  await expect(turn.getByRole("button", { name: "👍 Đúng" })).toHaveAttribute("aria-pressed", "true");
  await turn.getByRole("button", { name: "✏️ Sửa đáp án" }).click();
  await turn.getByPlaceholder("Đáp án đúng").fill("Không được đi vào.");
  await turn.getByPlaceholder("Ghi chú (không bắt buộc)").fill("kiểm thử");
  await turn.getByRole("button", { name: "Gửi" }).click();
  await expect(turn.getByTestId("feedback")).toContainText("Đã gửi: “Không được đi vào.”");

  // a follow-up on the same photo, answered by the RAG fallback
  await ask(page, "Hỏi RAG: xe ô tô có được đi vào không?");
  const rag = page.getByTestId("turn").nth(1);
  await expect(rag).toHaveAttribute("data-phase", "done");
  await expect(rag.getByTestId("rag")).toContainText("Trả lời bằng RAG – chưa được hệ luật kiểm chứng");
  await expect(rag.getByTestId("citations")).toHaveCount(0); // RAG laws are not rule citations
  await rag.getByText("QCVN 41:2024/BGTVT – B.3").click();
  await expect(rag.getByTestId("rag")).toContainText("Biển số P.103a");

  // history: a reload restores the session with its turns and feedback
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(2);
  const first = page.getByTestId("turn").first();
  await expect(first.getByTestId("answer")).toHaveText("Không. Biển số 1 (P.103a) cấm xe ô tô đi vào.");
  await expect(first.getByRole("button", { name: "👍 Đúng" })).toHaveAttribute("aria-pressed", "true");
  await expect(first.getByTestId("feedback")).toContainText("Không được đi vào.");
  await expect(page.getByTestId("turn").nth(1).getByTestId("rag")).toBeVisible();

  // a link to one turn reopens it with its details
  const url = page.url();
  expect(url).toMatch(/#turn=[0-9a-f]+/);
  await page.getByRole("button", { name: "Cuộc trò chuyện mới" }).click();
  await expect(page.getByTestId("turn")).toHaveCount(0);
  await page.getByRole("button", { name: "Lịch sử" }).click();
  await page.getByRole("dialog").getByText("Xe ô tô có được đi vào đường này không?").click();
  await expect(page.getByTestId("turn")).toHaveCount(2);
});

test("notes for a low-confidence sign and a local plate the answer rests on", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  await ask(page, "Theo biển phụ, xe máy có được đi vào không?");
  const notes = page.getByTestId("turn").first().getByTestId("notes");
  await expect(notes).toContainText("độ tin cậy thấp: biển 2 (W.207a)");
  await expect(notes).toContainText("Câu trả lời dựa trên chữ ghi trên biển phụ: “CẤM XE 2 VÀ 3 BÁNH”");
});

test("a dropped stream recovers the stored answer", async ({ page }) => {
  // the body ends after the first event (`turn`), as when a connection drops:
  // the client must fetch GET /v1/turns/{id}, which the server finishes on its own
  await page.addInitScript(() => {
    const real = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const res = await real(input, init);
      if (!String(input).includes("/v1/ask/stream") || !res.body) return res;
      const reader = res.body.getReader();
      let seen = "";
      const cut = new ReadableStream<Uint8Array>({
        async pull(c) {
          const { done, value } = await reader.read();
          if (done) return c.close();
          seen += new TextDecoder().decode(value);
          const end = seen.indexOf("\n\n");
          if (end === -1) return c.enqueue(value);
          c.enqueue(new TextEncoder().encode(seen.slice(0, end + 2)));
          void reader.cancel();
          c.close();
        },
      });
      return new Response(cut, { status: res.status, headers: res.headers });
    };
  });
  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  await ask(page, "Xe ô tô có được đi vào không?");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("answer")).toHaveText("Không. Biển số 1 (P.103a) cấm xe ô tô đi vào.");
  await expect(turn).toHaveAttribute("data-phase", "done");
});

test("a wrong file type is refused before upload", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles({ name: "a.gif", mimeType: "image/gif", buffer: Buffer.from("GIF89a") });
  await expect(page.getByRole("alert").filter({ hasText: "Không nhận ảnh" })).toContainText("image/gif");
});
