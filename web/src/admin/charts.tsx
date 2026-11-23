// Small SVG charts for the admin overview. No chart library: a few bars are all it needs.
// Colours come from the app's tokens, so light and dark themes both work.

import { fmtAxis, niceMax } from "./format";

export interface Series {
  key: string;
  label: string;
  color: string;
}

const W = 640;
const H = 200;
const PAD = { l: 34, r: 8, t: 10, b: 26 };

function Axis({ max }: { max: number }) {
  const ticks = [0, max / 2, max];
  const ih = H - PAD.t - PAD.b;
  return (
    <g className="adm-axis">
      {ticks.map((v) => {
        const y = PAD.t + ih - (v / max) * ih;
        return (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} />
            <text x={PAD.l - 6} y={y + 4} textAnchor="end">{fmtAxis(v)}</text>
          </g>
        );
      })}
    </g>
  );
}

/** A day as DD/MM under a bar; any other label as it is. */
const dayLabel = (l: string) => (/^\d{4}-\d{2}-\d{2}$/.test(l) ? `${l.slice(8)}/${l.slice(5, 7)}` : l);

/** Stacked bars: one bar per label, one segment per series. */
export function StackedBars({ labels, rows, series, title }: {
  labels: string[];
  rows: Record<string, number>[];
  series: Series[];
  title: string;
}) {
  const totals = rows.map((r) => series.reduce((s, x) => s + (r[x.key] ?? 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const slot = iw / Math.max(1, labels.length);
  const bw = Math.max(2, Math.min(36, slot * 0.7));
  const every = Math.ceil(labels.length / 10);
  return (
    <figure className="adm-chart">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        <Axis max={max} />
        {rows.map((r, i) => {
          let y = PAD.t + ih;
          const x = PAD.l + i * slot + (slot - bw) / 2;
          return (
            <g key={labels[i]}>
              <title>{`${labels[i]}: ${totals[i]}`}</title>
              {series.map((s) => {
                const v = r[s.key] ?? 0;
                const h = (v / max) * ih;
                y -= h;
                return v ? <rect key={s.key} x={x} y={y} width={bw} height={h} fill={s.color} rx={1.5} /> : null;
              })}
              {i % every === 0 && (
                <text className="adm-xlabel" x={x + bw / 2} y={H - 8} textAnchor="middle">{dayLabel(labels[i])}</text>
              )}
            </g>
          );
        })}
      </svg>
      <Legend series={series} />
    </figure>
  );
}

/** Plain bars with given labels (e.g. a histogram). */
export function Bars({ labels, values, title, color = "var(--accent)" }: {
  labels: string[];
  values: number[];
  title: string;
  color?: string;
}) {
  return (
    <StackedBars title={title} labels={labels} rows={values.map((v) => ({ v }))}
      series={[{ key: "v", label: title, color }]} />
  );
}

/** Horizontal share bars: label, bar, count. */
export function ShareList({ items, title }: { items: { label: string; value: number; color?: string }[]; title: string }) {
  const total = items.reduce((s, x) => s + x.value, 0);
  return (
    <figure className="adm-chart">
      <figcaption>{title}</figcaption>
      {total === 0 ? <p className="adm-muted">Chưa có dữ liệu.</p> : (
        <ul className="adm-share">
          {items.filter((x) => x.value > 0).map((x) => (
            <li key={x.label}>
              <span className="adm-share-label">{x.label}</span>
              <span className="adm-share-bar">
                <span style={{ width: `${(x.value / total) * 100}%`, background: x.color ?? "var(--accent)" }} />
              </span>
              <span className="adm-share-n">{x.value} · {Math.round((x.value / total) * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}

export function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <div className="adm-legend">
      {series.map((s) => (
        <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>
      ))}
    </div>
  );
}
