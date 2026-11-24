import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

const PHOTO = fileURLToPath(new URL("./fixtures/road.jpg", import.meta.url));

async function ask(page: Page, question: string) {
  await page.getByLabel("Câu hỏi", { exact: true }).fill(question);
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
}

test("ask, stream, boxes, citations, proof, feedback, RAG and history", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("fake-banner")).toContainText("pipeline giả");
  await expect(page.getByRole("heading", { name: "Hỏi biển báo trong ảnh của bạn" })).toBeVisible();
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  // record every text the streaming box shows (a draft is on screen for only a few hundred ms)
  await page.evaluate(() => {
    const seen: string[] = ((window as unknown as { streamSeen: string[] }).streamSeen = []);
    new MutationObserver(() => {
      // an empty stream box is not rendered: its disappearance after a draft counts as ""
      const el = document.querySelector('[data-testid="stream"]');
      const text = el ? el.textContent ?? "" : seen.length ? "" : null;
      if (text !== null && seen[seen.length - 1] !== text) seen.push(text);
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  });
  await ask(page, "Xe ô tô có được đi vào đường này không?");

  const turn = page.getByTestId("turn").first();

  // the final answer event replaces the stream
  await expect(turn).toHaveAttribute("data-phase", "done");
  await expect(turn.getByTestId("answer")).toHaveText("Không. Biển số 1 (P.103a) cấm xe ô tô đi vào.");
  // citations, proof and stage times are folded under one button
  await expect(turn.getByTestId("evidence")).toHaveCount(0);
  await turn.getByRole("button", { name: "Căn cứ và chứng minh" }).click();
  await expect(turn.getByTestId("citations")).toContainText("QCVN 41:2024/BGTVT B.3");
  await expect(turn.getByTestId("proof")).toContainText("forbids(s1, car, enter)");
  await expect(turn.locator('[data-stage="perception"]')).toContainText("2 biển báo");
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

  // feedback
  await turn.getByRole("button", { name: "Câu trả lời đúng" }).click();
  await expect(turn.getByRole("button", { name: "Câu trả lời đúng" })).toHaveAttribute("aria-pressed", "true");
  await turn.getByRole("button", { name: "Sửa đáp án" }).click();
  await turn.getByPlaceholder("Đáp án đúng").fill("Không được đi vào.");
  await turn.getByPlaceholder("Ghi chú (không bắt buộc)").fill("kiểm thử");
  await turn.getByRole("button", { name: "Gửi sửa" }).click();
  await expect(turn.getByTestId("feedback")).toContainText("Đã gửi: “Không được đi vào.”");

  // a follow-up on the same photo, answered by the RAG fallback
  await ask(page, "Hỏi RAG: xe ô tô có được đi vào không?");
  const rag = page.getByTestId("turn").nth(1);
  await expect(rag).toHaveAttribute("data-phase", "done");
  await expect(rag.getByTestId("rag-badge")).toHaveText("Trả lời bằng RAG – chưa được hệ luật kiểm chứng");
  await expect(rag.getByTestId("rag")).toContainText("QCVN 41:2024/BGTVT – B.3");
  await expect(rag.getByTestId("rag")).toContainText("Biển số P.103a"); // the first law is open
  await expect(rag.getByTestId("stats")).toContainText("Dự phòng");
  await rag.getByRole("button", { name: "Căn cứ và chứng minh" }).click();
  await expect(rag.getByTestId("evidence")).toBeVisible();
  await expect(rag.getByTestId("citations")).toHaveCount(0); // RAG laws are not rule citations
  await expect(rag.getByTestId("user-photo")).toHaveCount(0); // same photo: shown once

  // history: a reload restores the session with its turns and feedback
  await page.reload();
  await expect(page.getByTestId("turn")).toHaveCount(2);
  const first = page.getByTestId("turn").first();
  await expect(first.getByTestId("answer")).toHaveText("Không. Biển số 1 (P.103a) cấm xe ô tô đi vào.");
  await expect(first.getByRole("button", { name: "Câu trả lời đúng" })).toHaveAttribute("aria-pressed", "true");
  await expect(first.getByTestId("feedback")).toContainText("Không được đi vào.");
  await expect(page.getByTestId("turn").nth(1).getByTestId("rag")).toBeVisible();

  // a link to one turn reopens it with its details
  const url = page.url();
  expect(url).toMatch(/#turn=[0-9a-f]+/);
  await page.getByRole("button", { name: "Cuộc trò chuyện mới" }).click();
  await expect(page.getByTestId("turn")).toHaveCount(0);
  const menu = page.getByRole("button", { name: "Mở lịch sử" }); // phone: the history is in a drawer
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("navigation", { name: "Lịch sử" }).getByText("Xe ô tô có được đi vào đường này không?").click();
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

test("a question that is not about road signs gets the scope message and no 'not enough data' note", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  await ask(page, "Viết cho tôi một bài thơ về mùa thu.");
  const turn = page.getByTestId("turn").first();
  await expect(turn.getByTestId("answer")).toHaveText(/^Hệ thống chỉ trả lời câu hỏi về biển báo giao thông trong ảnh/);
  await expect(turn).not.toContainText("Chưa đủ dữ kiện");
});

test("a follow-up in the same chat shows how it was understood", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  await ask(page, "Xe ô tô có được đi vào đường này không?");
  await expect(page.getByTestId("turn").first().getByTestId("answer")).toBeVisible();
  await expect(page.getByTestId("understood-as")).toHaveCount(0); // a first question is never rewritten
  await ask(page, "Còn xe máy thì sao?");
  const second = page.getByTestId("turn").nth(1);
  await expect(second.getByTestId("understood-as")).toHaveText("Hiểu câu hỏi là: Xe máy có được đi vào đường này không?");
  await expect(second.getByTestId("answer")).toBeVisible();
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

test("voice: Vietnamese speech fills the question box; a desktop shows the mic instead of the camera", async ({ page }, info) => {
  // a fake recognizer: an interim result, then the final one, then the end of listening
  await page.addInitScript(() => {
    class FakeRecognition {
      lang = "";
      interimResults = false;
      continuous = false;
      onresult: ((e: unknown) => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        (window as unknown as { speechLang: string }).speechLang = this.lang;
        setTimeout(() => this.onresult?.({ results: [{ isFinal: false, 0: { transcript: "xe ô tô" } }] }), 50);
        setTimeout(() => {
          this.onresult?.({ results: [{ isFinal: true, 0: { transcript: "xe ô tô có được đi vào không" } }] });
          this.onend?.();
        }, 300);
      }
      stop() { this.onend?.(); }
      abort() {}
    }
    (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition = FakeRecognition;
  });
  await page.goto("/");
  const camera = page.getByRole("button", { name: "Chụp ảnh" });
  const pick = page.getByRole("button", { name: "Chụp hoặc chọn ảnh" });
  if (info.project.name === "desktop") {
    await expect(camera).toHaveCount(0); // hidden: no touch
    await expect(pick).toHaveCount(0);
  } else {
    await expect(pick).toBeVisible(); // a phone has one button: it offers the camera or the library
    await expect(camera).toHaveCount(0);
  }
  await page.getByRole("button", { name: "Hỏi bằng giọng nói" }).click();
  await expect(page.getByRole("button", { name: "Dừng nghe" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Câu hỏi", { exact: true })).toHaveValue("Xe ô tô có được đi vào không");
  await expect(page.getByRole("button", { name: "Hỏi bằng giọng nói" })).toHaveAttribute("aria-pressed", "false");
  expect(await page.evaluate(() => (window as unknown as { speechLang: string }).speechLang)).toBe("vi-VN");
});

test("the side bars fold and unfold from buttons that never move, and the choice is remembered", async ({ page }, info) => {
  await page.goto("/");
  const sideBtn = page.locator(".side-toggle");
  const photoBtn = page.locator(".photo-toggle");
  if (info.project.name !== "desktop") {
    await expect(sideBtn).toBeHidden(); // phones: the drawer and the photo's own arrow instead
    await expect(photoBtn).toBeHidden();
    return;
  }
  const sidebar = page.locator("aside.sidebar");
  const photo = page.getByRole("region", { name: "Ảnh" });
  // the desktop is drawn at 80%, like the browser's 80% zoom, and the side bars still fill the window
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).zoom)).toBe("0.8");
  const vh = page.viewportSize()!.height;
  for (const bar of [sidebar, photo]) {
    const b = (await bar.boundingBox())!;
    expect(Math.abs(b.y + b.height - vh)).toBeLessThan(2);
  }
  const at = async () => [await sideBtn.boundingBox(), await photoBtn.boundingBox()];
  const before = await at();
  const box = page.locator(".composer");
  const boxBefore = await box.boundingBox();

  await expect(sideBtn).toHaveAccessibleName("Thu gọn thanh bên");
  await sideBtn.click();
  await expect(sidebar).toBeHidden();
  await expect(sideBtn).toHaveAccessibleName("Mở thanh bên");
  // the question box only moves sideways, and no extra buttons appear in its place
  const boxAfter = await box.boundingBox();
  expect(boxAfter!.y).toBe(boxBefore!.y);
  expect(boxAfter!.x).toBeLessThan(boxBefore!.x);
  await expect(page.getByRole("button", { name: "Cuộc trò chuyện mới" })).toBeHidden();
  await expect(page.getByRole("button", { name: /^Giao diện/ })).toBeHidden();
  // also when the greeting wraps differently (fonts differ by system): force it to wrap with the sidebar
  // open and fit on fewer lines with it folded; the box must still keep its height
  await sideBtn.click();
  await page.addStyleTag({ content: ".hero-anchor > h2 { font-size: 44px !important; }" });
  const wrapped = await box.boundingBox();
  await sideBtn.click();
  expect((await box.boundingBox())!.y).toBe(wrapped!.y);
  await page.addStyleTag({ content: ".hero-anchor > h2 { font-size: revert-layer !important; }" });
  await photoBtn.click();
  await expect(photo).toBeHidden();
  await expect(photoBtn).toHaveAccessibleName("Mở khung ảnh");
  expect(await at()).toEqual(before); // same place, folded or not
  await expect(page.getByLabel("Câu hỏi", { exact: true })).toBeVisible();

  await page.reload();
  await expect(sidebar).toBeHidden();
  await expect(photo).toBeHidden();
  expect(await at()).toEqual(before);
  await sideBtn.click();
  await photoBtn.click();
  await expect(sidebar).toBeVisible();
  await expect(photo).toBeVisible();
  expect(await at()).toEqual(before);
});

test("a wrong file type is refused before upload", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("file-input").setInputFiles({ name: "a.gif", mimeType: "image/gif", buffer: Buffer.from("GIF89a") });
  await expect(page.getByRole("alert").filter({ hasText: "Không nhận ảnh" })).toContainText("image/gif");
});

test("phone layout as in the mockup: name in the bar, a one-line box, a short pinned photo with sign chips", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone only");
  await page.goto("/");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).zoom)).toBe("1"); // phones at 100%
  // before the first question: the name in the bar, no "new chat", the box under the greeting, no example questions
  await expect(page.locator(".topbar-brand")).toHaveText("SignCite");
  await expect(page.getByRole("button", { name: "Cuộc trò chuyện mới" })).toBeHidden();
  const box = page.locator("form.composer");
  const greeting = page.getByRole("heading", { name: "Hỏi biển báo trong ảnh của bạn" });
  expect((await box.boundingBox())!.y).toBeGreaterThan((await greeting.boundingBox())!.y + 100);
  await expect(page.locator(".example")).toHaveCount(0);
  // a picked photo is a chip in the box; the photo panel waits for the first question
  await page.getByTestId("file-input").setInputFiles(PHOTO);
  await expect(page.locator(".composer-photo")).toContainText("road.jpg");
  await expect(page.locator(".photo-panel")).toBeHidden();
  // one line: the text, the camera, the mic and send share a row
  const text = await page.getByLabel("Câu hỏi", { exact: true }).boundingBox();
  const send = await page.getByRole("button", { name: "Gửi", exact: true }).boundingBox();
  expect(Math.abs(text!.y + text!.height / 2 - (send!.y + send!.height / 2))).toBeLessThan(12);

  await ask(page, "Xe ô tô có được đi vào đường này không?");
  await expect(page.getByTestId("turn").first()).toHaveAttribute("data-phase", "done");
  // the photo is pinned under the bar, not repeated in the thread; the follow-up has no photo chip
  await expect(page.locator(".photo-panel")).toBeVisible();
  await expect(page.locator(".photo-head")).toBeHidden();
  await expect(page.getByTestId("user-photo")).toBeHidden();
  await expect(page.locator(".composer-photo")).toBeHidden();
  // short chips: code and confidence
  const chips = page.locator(".sign-list button");
  await expect(chips).toHaveCount(2);
  await expect(chips.first().locator(".sign-code")).toHaveText("P.103a");
  await expect(chips.first().locator(".sign-name")).toBeHidden();
  await expect(chips.first()).toContainText("cao");
  // folding hides the picture and keeps the chips and the button
  await page.getByRole("button", { name: "Thu gọn ảnh" }).click();
  await expect(page.locator(".photo-wrap")).toBeHidden();
  await expect(chips.first()).toBeVisible();
  await page.getByRole("button", { name: "Mở ảnh" }).click();
  await expect(page.locator(".photo-wrap")).toBeVisible();
  // the sent question's box is one line again
  expect((await page.getByLabel("Câu hỏi", { exact: true }).boundingBox())!.height).toBeLessThan(50);
});
