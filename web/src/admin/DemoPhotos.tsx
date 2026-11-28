import { useCallback, useEffect, useRef, useState } from "react";
import { admin, type Demo, type DemoItem } from "./api";

const lines = (s: string) => s.split("\n").map((q) => q.trim()).filter(Boolean);

function Row({ item, first, last, busy, run, onMove }: {
  item: DemoItem; first: boolean; last: boolean; busy: boolean;
  run: (f: () => Promise<Demo>) => void;
  onMove: (step: -1 | 1) => void;
}) {
  const [caption, setCaption] = useState(item.caption);
  const [questions, setQuestions] = useState(item.questions.join("\n"));
  useEffect(() => {
    setCaption(item.caption);
    setQuestions(item.questions.join("\n"));
  }, [item]);
  const dirty = caption.trim() !== item.caption || lines(questions).join("\n") !== item.questions.join("\n");
  return (
    <li className="adm-card adm-demo-row">
      <img src={`/v1/demo/${item.sha256}/thumb`} alt="" />
      <div className="adm-demo-fields">
        <input value={caption} maxLength={120} placeholder="Chú thích (ví dụ: Biển cấm xe tải ở ngã tư)"
          aria-label="Chú thích" onChange={(e) => setCaption(e.target.value)} />
        <textarea rows={3} value={questions} placeholder="Câu hỏi gợi ý, mỗi dòng một câu (tối đa 5)"
          aria-label="Câu hỏi gợi ý" onChange={(e) => setQuestions(e.target.value)} />
        <div className="adm-filters">
          <button type="button" className="adm-primary" disabled={busy || !dirty}
            onClick={() => run(() => admin.editDemo(item.sha256, { caption: caption.trim(), questions: lines(questions) }))}>Lưu</button>
          <button type="button" disabled={busy || first} aria-label="Lên trên" onClick={() => onMove(-1)}>↑</button>
          <button type="button" disabled={busy || last} aria-label="Xuống dưới" onClick={() => onMove(1)}>↓</button>
          <button type="button" className="adm-danger" disabled={busy} onClick={() => {
            if (window.confirm("Bỏ ảnh này khỏi danh sách ảnh mẫu? Câu hỏi cũ về ảnh vẫn giữ nguyên.")) {
              run(() => admin.deleteDemo(item.sha256));
            }
          }}>Bỏ</button>
        </div>
      </div>
    </li>
  );
}

export default function DemoPhotos({ onError }: { onError: (e: unknown) => void }) {
  const [d, setD] = useState<Demo | null>(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [caption, setCaption] = useState("");
  const [questions, setQuestions] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => admin.demo().then(setD, onError), [onError]);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (f: () => Promise<Demo>) => {
    setBusy(true);
    try {
      setD(await f());
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };

  // ↑ / ↓: swap with the neighbour, then send the whole order
  const reorder = (sha: string, step: -1 | 1) => {
    if (!d) return;
    const order = d.items.map((x) => x.sha256);
    const i = order.indexOf(sha);
    const j = i + step;
    if (i < 0 || j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    void run(() => admin.orderDemo(order));
  };

  return (
    <div className="adm-stack">
      <p className="adm-muted">
        Ảnh có sẵn trên màn hình bắt đầu của ứng dụng, để người thử (ví dụ hội đồng) hỏi ngay mà không cần tải ảnh.
        Câu hỏi về ảnh mẫu được trả lời như mọi câu hỏi khác (vẫn tính chi phí). Dùng ảnh tự chụp hoặc ảnh được phép
        chia sẻ; không dùng ảnh của bộ kiểm tra riêng (private test).
      </p>
      {d && (
        <div className={d.enabled ? "adm-card adm-site-login adm-site-open" : "adm-card adm-site-login"}>
          <label className="adm-switch">
            <input type="checkbox" role="switch" checked={d.enabled} disabled={busy} aria-label="Hiện ảnh mẫu trên ứng dụng"
              onChange={() => run(() => admin.setDemoEnabled(!d.enabled))} />
            <span className="adm-switch-track" aria-hidden="true" />
            <b>{d.enabled ? "Đang hiện ảnh mẫu" : "Đang ẩn ảnh mẫu"}</b>
          </label>
          <p className="adm-muted">
            {d.enabled
              ? (d.items.length ? `Ứng dụng đang hiện ${d.items.length} ảnh mẫu.` : "Đã bật nhưng chưa có ảnh nào, nên ứng dụng chưa hiện gì.")
              : "Ứng dụng không hiện ảnh mẫu. Ảnh vẫn được giữ ở đây."}
          </p>
        </div>
      )}

      <form className="adm-card adm-demo-add" onSubmit={(e) => {
        e.preventDefault();
        if (!file) return;
        void run(async () => {
          const r = await admin.addDemo(file, caption.trim(), lines(questions));
          setFile(null);
          setCaption("");
          setQuestions("");
          if (fileRef.current) fileRef.current.value = "";
          return r;
        });
      }}>
        <b>Thêm ảnh mẫu</b>
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" aria-label="Ảnh"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <input value={caption} maxLength={120} placeholder="Chú thích (ví dụ: Biển cấm xe tải ở ngã tư)"
          aria-label="Chú thích ảnh mới" onChange={(e) => setCaption(e.target.value)} />
        <textarea rows={3} value={questions} placeholder="Câu hỏi gợi ý, mỗi dòng một câu (tối đa 5)"
          aria-label="Câu hỏi gợi ý cho ảnh mới" onChange={(e) => setQuestions(e.target.value)} />
        <div><button type="submit" className="adm-primary" disabled={busy || !file}>Thêm</button></div>
      </form>

      {d && (d.items.length === 0 ? <p className="adm-muted">Chưa có ảnh mẫu nào.</p> : (
        <ol className="adm-demo-list">
          {d.items.map((item, i) => (
            <Row key={item.sha256} item={item} first={i === 0} last={i === d.items.length - 1} busy={busy}
              run={(f) => void run(f)} onMove={(step) => reorder(item.sha256, step)} />
          ))}
        </ol>
      ))}
    </div>
  );
}
