import { demoThumbUrl, type DemoPhoto } from "../lib/api";

/** The start screen's demo photos (switched on in the admin site): one click picks a photo,
 *  and its suggested questions fill the box. Nothing is sent until the visitor presses Gửi. */
export default function DemoGallery({ items, picked, busy, onPick, onQuestion }: {
  items: DemoPhoto[];
  picked: string | null;
  busy: boolean;
  onPick: (d: DemoPhoto) => void;
  onQuestion: (q: string) => void;
}) {
  if (!items.length) return null;
  const cur = items.find((d) => d.sha256 === picked);
  return (
    <section className="demo" aria-label="Ảnh mẫu">
      <div className="demo-title muted small">Chưa có ảnh? Thử một ảnh mẫu:</div>
      <ul className="demo-strip">
        {items.map((d) => (
          <li key={d.sha256}>
            <button type="button" className={`demo-card${d.sha256 === picked ? " picked" : ""}`} disabled={busy}
              aria-pressed={d.sha256 === picked} title={d.caption || "Ảnh mẫu"} onClick={() => onPick(d)}>
              <img src={demoThumbUrl(d.sha256)} alt={d.caption || "Ảnh mẫu"} loading="lazy" />
              {d.caption && <span className="demo-caption">{d.caption}</span>}
            </button>
          </li>
        ))}
      </ul>
      {cur && cur.questions.length > 0 && (
        <div className="demo-questions" aria-label="Câu hỏi gợi ý">
          {cur.questions.map((q) => (
            <button key={q} type="button" className="demo-q" disabled={busy} onClick={() => onQuestion(q)}>{q}</button>
          ))}
        </div>
      )}
    </section>
  );
}
