// SVG charts for the admin overview, interactive: hover (or tap, or the arrow keys) shows a tooltip
// with every series' value; legend entries switch a series off and on; clicking a bar or a row
// calls `onSelect`, which opens the matching questions. No chart library. Colours come from the
// app's tokens, so light and dark themes both work.

import { useMemo, useRef, useState } from "react";
import { fmtAxis, niceMax } from "./format";

export interface Series {
  key: string;
  label: string;
  color: string;
}

const W = 640;
const H = 210;
const PAD = { l: 38, r: 8, t: 12, b: 26 };

/** A day as DD/MM under a bar; any other label as it is. */
export const dayLabel = (l: string) => (/^\d{4}-\d{2}-\d{2}$/.test(l) ? `${l.slice(8)}/${l.slice(5, 7)}` : l);

function Axis({ max, fmt }: { max: number; fmt: (v: number) => string }) {
  const ih = H - PAD.t - PAD.b;
  return (
    <g className="adm-axis">
      {[0, max / 2, max].map((v) => {
        const y = PAD.t + ih - (v / max) * ih;
        return (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} />
            <text x={PAD.l - 6} y={y + 4} textAnchor="end">{fmt(v)}</text>
          </g>
        );
      })}
    </g>
  );
}

/** Stacked bars: one bar per label, one segment per series. */
export function StackedBars({ labels, rows, series, title, fmt = fmtAxis, unit = "", onSelect, selectHint }: {
  labels: string[];
  rows: Record<string, number>[];
  series: Series[];
  title: string;
  fmt?: (v: number) => string;
  unit?: string;
  onSelect?: (label: string) => void;
  selectHint?: string;
}) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const shown = series.filter((s) => !hidden.has(s.key));
  const totals = rows.map((r) => shown.reduce((s, x) => s + (r[x.key] ?? 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const slot = iw / Math.max(1, labels.length);
  const bw = Math.max(2, Math.min(40, slot * 0.68));
  const every = Math.ceil(labels.length / 10);

  const indexAt = (clientX: number) => {
    const svg = svgRef.current;
    if (!svg || !labels.length) return null;
    const box = svg.getBoundingClientRect();
    const x = ((clientX - box.left) / box.width) * W - PAD.l;
    if (x < 0 || x > iw) return null;
    return Math.min(labels.length - 1, Math.max(0, Math.floor(x / slot)));
  };

  const toggle = (key: string) => {
    const next = new Set(hidden);
    if (next.has(key)) next.delete(key);
    else if (shown.length > 1) next.add(key);       // never hide the last series
    setHidden(next);
  };

  const tip = hover !== null ? (
    <div className="adm-tip" role="status"
      style={{
        left: `${((PAD.l + (hover + 0.5) * slot) / W) * 100}%`,
        // open towards the side with room, so the tooltip never leaves the card
        transform: (hover + 0.5) / labels.length > 0.6 ? "translateX(calc(-100% - 10px))"
          : (hover + 0.5) / labels.length < 0.4 ? "translateX(10px)" : "translateX(-50%)",
      }}>
      <div className="adm-tip-title">{dayLabel(labels[hover])}</div>
      {shown.length > 1 ? shown.filter((s) => (rows[hover][s.key] ?? 0) !== 0).map((s) => (
        <div key={s.key} className="adm-tip-row">
          <i style={{ background: s.color }} />{s.label}<b>{fmt(rows[hover][s.key] ?? 0)}{unit}</b>
        </div>
      )) : null}
      <div className="adm-tip-row adm-tip-total">{shown.length > 1 ? "Tổng" : shown[0]?.label}<b>{fmt(totals[hover])}{unit}</b></div>
      {onSelect && totals[hover] > 0 && <div className="adm-tip-hint">{selectHint ?? "Bấm để xem"}</div>}
    </div>
  ) : null;

  return (
    <figure className="adm-chart" tabIndex={0} aria-label={title}
      onKeyDown={(e) => {
        if (!labels.length) return;
        if (e.key === "ArrowRight") setHover((h) => Math.min(labels.length - 1, (h ?? -1) + 1));
        else if (e.key === "ArrowLeft") setHover((h) => Math.max(0, (h ?? labels.length) - 1));
        else if (e.key === "Enter" && hover !== null && onSelect && totals[hover] > 0) onSelect(labels[hover]);
        else if (e.key === "Escape") setHover(null);
        else return;
        e.preventDefault();
      }}
      onBlur={() => setHover(null)}>
      <figcaption>{title}</figcaption>
      <div className="adm-plot">
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}
          className={onSelect ? "adm-clickable" : undefined}
          onPointerMove={(e) => { if (e.pointerType === "mouse") setHover(indexAt(e.clientX)); }}
          onPointerLeave={(e) => { if (e.pointerType === "mouse") setHover(null); }}
          onPointerUp={(e) => {
            const i = indexAt(e.clientX);
            if (i === null) return;
            // on a touch screen the first tap shows the tooltip and the second opens the questions
            if (e.pointerType !== "mouse" && hover !== i) {
              setHover(i);
              return;
            }
            if (onSelect && totals[i] > 0) onSelect(labels[i]);
          }}>
          <Axis max={max} fmt={fmt} />
          {hover !== null && (
            <rect className="adm-hover-band" x={PAD.l + hover * slot} y={PAD.t} width={slot} height={ih} />
          )}
          {rows.map((r, i) => {
            let y = PAD.t + ih;
            const x = PAD.l + i * slot + (slot - bw) / 2;
            return (
              <g key={labels[i]} opacity={hover === null || hover === i ? 1 : 0.55}>
                {shown.map((s) => {
                  const v = r[s.key] ?? 0;
                  const h = (v / max) * ih;
                  y -= h;
                  return v ? <rect key={s.key} x={x} y={y} width={bw} height={h} fill={s.color} rx={2} /> : null;
                })}
                {i % every === 0 && (
                  <text className="adm-xlabel" x={x + bw / 2} y={H - 8} textAnchor="middle">{dayLabel(labels[i])}</text>
                )}
              </g>
            );
          })}
        </svg>
        {tip}
      </div>
      {series.length > 1 && (
        <div className="adm-legend">
          {series.map((s) => (
            <button key={s.key} type="button" className={hidden.has(s.key) ? "off" : ""} aria-pressed={!hidden.has(s.key)}
              aria-label={`${hidden.has(s.key) ? "Hiện" : "Ẩn"} ${s.label}`} onClick={() => toggle(s.key)}>
              <i style={{ background: s.color }} />{s.label}
            </button>
          ))}
        </div>
      )}
    </figure>
  );
}

/** Plain bars with given labels (e.g. a histogram). */
export function Bars({ labels, values, title, color = "var(--accent)", fmt, unit, onSelect, selectHint }: {
  labels: string[];
  values: number[];
  title: string;
  color?: string;
  fmt?: (v: number) => string;
  unit?: string;
  onSelect?: (label: string) => void;
  selectHint?: string;
}) {
  return (
    <StackedBars title={title} labels={labels} rows={values.map((v) => ({ v }))} fmt={fmt} unit={unit}
      series={[{ key: "v", label: title, color }]} onSelect={onSelect} selectHint={selectHint} />
  );
}

/** Horizontal share bars: label, bar, count. Rows are buttons when `onSelect` is given. */
export function ShareList({ items, title, onSelect }: {
  items: { key: string; label: string; value: number; color?: string }[];
  title: string;
  onSelect?: (key: string) => void;
}) {
  const total = items.reduce((s, x) => s + x.value, 0);
  return (
    <figure className="adm-chart">
      <figcaption>{title}</figcaption>
      {total === 0 ? <p className="adm-muted">Chưa có dữ liệu.</p> : (
        <ul className="adm-share">
          {items.filter((x) => x.value > 0).map((x) => {
            const body = (
              <>
                <span className="adm-share-label">{x.label}</span>
                <span className="adm-share-bar">
                  <span style={{ width: `${(x.value / total) * 100}%`, background: x.color ?? "var(--accent)" }} />
                </span>
                <span className="adm-share-n">{x.value} · {Math.round((x.value / total) * 100)}%</span>
              </>
            );
            return (
              <li key={x.key}>
                {onSelect
                  ? <button type="button" className="adm-share-row" onClick={() => onSelect(x.key)}
                      aria-label={`${x.label}: ${x.value} câu. Xem các câu hỏi này`}>{body}</button>
                  : <div className="adm-share-row">{body}</div>}
              </li>
            );
          })}
        </ul>
      )}
    </figure>
  );
}

/** A small line for a card: the trend of `values`, with the last point marked. */
export function Sparkline({ values, color = "var(--accent)", label }: { values: number[]; color?: string; label: string }) {
  const pts = useMemo(() => {
    if (values.length < 2) return null;
    const max = Math.max(...values, 1);
    const w = 120, h = 36;
    return values.map((v, i) => [(i / (values.length - 1)) * w, h - 3 - (v / max) * (h - 6)] as const);
  }, [values]);
  if (!pts) return null;
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg className="adm-spark" viewBox="0 0 120 36" role="img" aria-label={label}>
      <polygon points={`0,36 ${line} 120,36`} fill={color} opacity={0.12} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r={2.6} fill={color} />
    </svg>
  );
}
