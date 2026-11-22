import { useEffect, useState } from "react";
import { CONFIDENCE } from "../lib/labels";
import type { SignBox } from "../lib/types";
import { ChevronDown, ChevronUp, Image } from "./Icons";

interface Props {
  imageUrl: string | null;
  imageSize: [number, number] | null; // original-photo pixels, from the `started` event
  signs: SignBox[];
  onDropFile: (file: File) => void;
  busy: boolean;
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

export default function PhotoPanel({ imageUrl, imageSize, signs, onDropFile, busy }: Props) {
  const [drag, setDrag] = useState(false);
  const [natural, setNatural] = useState<[number, number] | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [collapsed, setCollapsed] = useState(false); // phone only

  useEffect(() => {
    setActive(null);
    setNatural(null);
  }, [imageUrl]);

  const size = imageSize ?? natural;
  const boxed = signs.map((s, i) => ({ s, n: i + 1 })).filter((x) => x.s.box && x.s.box.length === 4);
  const tag = size ? Math.max(size[0], size[1]) / 28 : 20;
  const cur = active != null ? signs[active - 1] : undefined;

  const dropProps = {
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setDrag(true); },
    onDragLeave: () => setDrag(false),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setDrag(false);
      const f = e.dataTransfer.files[0];
      if (f && !busy) onDropFile(f);
    },
  };

  const fold = (
    <button type="button" className="icon-btn small collapse-btn" onClick={() => setCollapsed(!collapsed)}
      aria-expanded={!collapsed} aria-label={collapsed ? "Mở ảnh" : "Thu gọn ảnh"}>
      {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
    </button>
  );

  return (
    <section className={`photo-panel${collapsed ? " collapsed" : ""}${imageUrl ? "" : " no-photo"}`} aria-label="Ảnh" {...dropProps}>
      <div className="photo-head">
        <span className="photo-title">Ảnh</span>
        {imageUrl && <span className="muted small">{signs.length ? `${signs.length} biển báo tìm thấy` : ""}</span>}
      </div>
      {!imageUrl ? (
        <div className={`photo-empty${drag ? " drag" : ""}`}>
          <Image size={34} />
          <div>Ảnh và các khung biển báo sẽ hiện ở đây.</div>
          <div className="muted small">Kéo thả ảnh vào đây, dán ảnh, hoặc đính kèm ở ô câu hỏi.</div>
        </div>
      ) : (
        <div className="photo-body">
          <div className={`photo-wrap${drag ? " drag" : ""}`}>
            <img src={imageUrl} alt="Ảnh đang xem"
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
                        onMouseEnter={() => setActive(n)} onFocus={() => setActive(n)} onClick={() => setActive(n)}>
                        <title>{`${n}. ${signTitle(s)} (${signDetail(s)})`}</title>
                      </rect>
                      <g className="tag" transform={`translate(${x0}, ${Math.max(0, y0 - tag * 1.1)})`}>
                        <rect width={tag * (String(n).length * 0.62 + 0.6)} height={tag} rx={tag / 4}
                          style={{ fill: `var(--${cls === "conf-none" ? "muted" : cls.slice(5)})` }} />
                        <text x={tag * 0.3} y={tag * 0.78} fontSize={tag * 0.8} fontWeight={700} fill="#fff">{n}</text>
                      </g>
                    </g>
                  );
                })}
              </svg>
            )}
            {cur && (
              <div className="sign-caption" aria-live="polite" data-testid="sign-info">
                <strong>{active}. {signTitle(cur)}</strong>
                <span>{signDetail(cur)}</span>
              </div>
            )}
          </div>
          {boxed.length > 0 && (
            <div className="legend" aria-hidden>
              <span><i className="line high" /> tin cậy cao</span>
              <span><i className="line medium" /> trung bình</span>
              <span><i className="line low" /> thấp</span>
            </div>
          )}
          {/* phone: the signs are one row of short chips, with the fold button at its end */}
          <div className="sign-row">
            {signs.length > 0 && (
              <ul className="sign-list">
                {signs.map((s, i) => (
                  <li key={s.id + i}>
                    <button type="button" className={active === i + 1 ? "active" : ""}
                      onMouseEnter={() => setActive(i + 1)} onFocus={() => setActive(i + 1)} onClick={() => setActive(i + 1)}>
                      <span className={`num ${confClass(s.confidence)}`}>{i + 1}</span>
                      <span className="sign-name">{signTitle(s)}</span>
                      <span className="sign-code">{s.code && s.code !== "UNKNOWN" ? s.code : "Không đọc được"}</span>
                      <span className="muted small">{CONFIDENCE[String(s.confidence)] ?? ""}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {fold}
          </div>
        </div>
      )}
    </section>
  );
}
