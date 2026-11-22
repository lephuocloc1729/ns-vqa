import { useEffect, useRef, useState } from "react";
import { CONFIDENCE } from "../lib/labels";
import type { SignBox } from "../lib/types";

export const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

interface Props {
  imageUrl: string | null;
  imageSize: [number, number] | null; // original-photo pixels, from the `started` event
  signs: SignBox[];
  busy: boolean;
  onPick: (file: File) => void;
  onClear: () => void;
  error: string | null;
}

const confClass = (c: unknown) => (c === "high" || c === "medium" || c === "low" ? `conf-${c}` : "conf-none");

function signTitle(s: SignBox): string {
  const parts = [s.code && s.code !== "UNKNOWN" ? s.code : "Không đọc được"];
  if (s.name) parts.push(s.name);
  if (s.value != null) parts.push(`${s.value}${s.unit ? " " + s.unit : ""}`);
  return parts.join(" – ");
}

function signDetail(s: SignBox): string {
  const bits = [`độ tin cậy ${CONFIDENCE[String(s.confidence)] ?? "không rõ"}`];
  if (s.plates && s.plates.length) bits.push(`biển phụ: ${s.plates.join("; ")}`);
  if (s.alternatives && s.alternatives.length) bits.push(`có thể là: ${s.alternatives.join(", ")}`);
  if (s.code && s.code !== "UNKNOWN" && !s.known) bits.push("không có trong danh mục");
  return bits.join(" · ");
}

export default function PhotoPanel({ imageUrl, imageSize, signs, busy, onPick, onClear, error }: Props) {
  const [drag, setDrag] = useState(false);
  const [natural, setNatural] = useState<[number, number] | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setActive(null);
    setNatural(null);
  }, [imageUrl]);

  const size = imageSize ?? natural;
  const boxed = signs.map((s, i) => ({ s, n: i + 1 })).filter((x) => x.s.box && x.s.box.length === 4);
  const tag = size ? Math.max(size[0], size[1]) / 28 : 20;

  function take(files: FileList | null | undefined) {
    const f = files && files[0];
    if (f) onPick(f);
  }

  const dropProps = {
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      setDrag(true);
    },
    onDragLeave: () => setDrag(false),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setDrag(false);
      if (!busy) take(e.dataTransfer.files);
    },
  };

  const pickers = (
    <>
      <input ref={fileRef} type="file" accept={ACCEPTED.join(",")} hidden data-testid="file-input"
        onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
      <input ref={camRef} type="file" accept="image/*" capture="environment" hidden
        onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
      <button type="button" className="btn" disabled={busy} onClick={() => fileRef.current?.click()}>🖼️ Chọn ảnh</button>
      <button type="button" className="btn" disabled={busy} onClick={() => camRef.current?.click()}>📷 Chụp ảnh</button>
    </>
  );

  return (
    <section className="card photo-card" aria-label="Ảnh">
      {!imageUrl ? (
        <div className={`dropzone${drag ? " drag" : ""}`} {...dropProps}>
          <div style={{ fontSize: 34 }} aria-hidden>🚦</div>
          <p style={{ margin: "6px 0 0" }}>Kéo thả ảnh vào đây, dán ảnh (Ctrl/⌘+V), hoặc chọn ảnh có biển báo.</p>
          <div className="photo-actions">{pickers}</div>
        </div>
      ) : (
        <>
          <div className={`photo-wrap${drag ? " drag" : ""}`} {...dropProps}>
            <img src={imageUrl} alt="Ảnh đã chọn"
              onLoad={(e) => setNatural([e.currentTarget.naturalWidth, e.currentTarget.naturalHeight])} />
            {size && boxed.length > 0 && (
              <svg className="overlay" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="xMidYMid meet"
                role="group" aria-label="Biển báo tìm thấy">
                {boxed.map(({ s, n }) => {
                  const [x0, y0, x1, y1] = s.box!;
                  const cls = confClass(s.confidence);
                  return (
                    <g key={s.id + n}>
                      <rect className={`box ${cls}${active === n ? " active" : ""}`} x={x0} y={y0}
                        width={Math.max(1, x1 - x0)} height={Math.max(1, y1 - y0)} tabIndex={0}
                        data-testid={`box-${n}`} aria-label={`${n}. ${signTitle(s)}, ${signDetail(s)}`}
                        onMouseEnter={() => setActive(n)} onFocus={() => setActive(n)}
                        onClick={() => setActive(n)}>
                        <title>{`${n}. ${signTitle(s)} (${signDetail(s)})`}</title>
                      </rect>
                      <g className="tag" transform={`translate(${x0}, ${Math.max(0, y0 - tag * 1.1)})`}>
                        <rect width={tag * (String(n).length * 0.62 + 0.6)} height={tag} rx={tag / 4}
                          className={`num ${cls}`} style={{ fill: `var(--${cls.replace("conf-none", "muted")})` }} />
                        <text x={tag * 0.3} y={tag * 0.78} fontSize={tag * 0.8} fontWeight={700} fill="#fff">{n}</text>
                      </g>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
          {boxed.length > 0 && (
            <div className="legend" aria-hidden>
              <span><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="var(--conf-high)" strokeWidth="3" /></svg> tin cậy cao</span>
              <span><svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="var(--conf-medium)" strokeWidth="3" strokeDasharray="7 4" /></svg> trung bình</span>
              <span><svg width="26" height="8"><line x1="1" y1="4" x2="26" y2="4" stroke="var(--conf-low)" strokeWidth="3" strokeDasharray="1 5" strokeLinecap="round" /></svg> thấp</span>
            </div>
          )}
          {signs.length > 0 && (
            <>
              <div className="sign-info" aria-live="polite" data-testid="sign-info">
                {active != null && signs[active - 1] ? (
                  <>
                    <strong>{active}. {signTitle(signs[active - 1])}</strong>
                    <div className="muted">{signDetail(signs[active - 1])}</div>
                  </>
                ) : (
                  <span className="muted">Chạm hoặc rê chuột lên khung (hoặc danh sách) để xem mã và tên biển.</span>
                )}
              </div>
              <ul className="sign-list">
                {signs.map((s, i) => (
                  <li key={s.id + i}>
                    <button type="button" className={active === i + 1 ? "active" : ""}
                      onMouseEnter={() => setActive(i + 1)} onClick={() => setActive(i + 1)}>
                      <span className={`num ${confClass(s.confidence)}`}>{i + 1}</span>
                      <span style={{ flex: 1, minWidth: 0 }}>{signTitle(s)}</span>
                      <span className="muted">{CONFIDENCE[String(s.confidence)] ?? ""}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="photo-meta">
            <div className="photo-actions" style={{ marginTop: 0 }}>{pickers}</div>
            <button type="button" className="btn small" disabled={busy} onClick={onClear}>Bỏ ảnh</button>
          </div>
        </>
      )}
      {error && <p className="err" role="alert">{error}</p>}
    </section>
  );
}
