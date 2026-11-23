import { useEffect, useState } from "react";
import { VERDICT } from "../lib/labels";
import { admin, type Overview as Data, type Range } from "./api";
import { Bars, ShareList, Sparkline, StackedBars } from "./charts";
import { daysBetween, fmtInt, fmtPct, fmtSec, fmtUsd, ROUTE, ROUTE_COLOR, ROUTE_ORDER } from "./format";

/** What a click on a chart opens: the questions of a day, a route or a verdict. */
export interface Drill {
  since?: string;
  until?: string;
  route?: string;
  verdict?: string;
}

function Card({ label, value, sub, trend, trendColor, onClick }: {
  label: string;
  value: string;
  sub?: string;
  trend?: number[];
  trendColor?: string;
  onClick?: () => void;
}) {
  const body = (
    <>
      <div className="adm-card-label">{label}</div>
      <div className="adm-card-row">
        <div className="adm-card-value">{value}</div>
        {trend && <Sparkline values={trend} color={trendColor} label={`${label}: xu hướng theo ngày`} />}
      </div>
      {sub && <div className="adm-card-sub">{sub}</div>}
    </>
  );
  return onClick
    ? <button type="button" className="adm-card adm-card-link" onClick={onClick}>{body}</button>
    : <div className="adm-card">{body}</div>;
}

export default function Overview({ range, onError, onDrill }: {
  range: Range;
  onError: (e: unknown) => void;
  onDrill: (d: Drill) => void;
}) {
  const [d, setD] = useState<Data | null>(null);

  useEffect(() => {
    let live = true;
    admin.overview(range).then((x) => live && setD(x), onError);
    const id = window.setInterval(() => admin.overview(range).then((x) => live && setD(x), () => {}), 30_000);
    return () => {
      live = false;
      window.clearInterval(id);
    };
  }, [range, onError]);

  if (!d) return <p className="adm-muted">Đang tải…</p>;

  const r = d.routes;
  const decided = (r.rules ?? 0) + (r.rag ?? 0) + (r.rag_cache ?? 0) + (r.fallback ?? 0) + (r.not_decided ?? 0);
  const ragAll = (r.rag ?? 0) + (r.rag_cache ?? 0);
  const span = d.per_day.length
    ? daysBetween(range.since ?? d.per_day[0].day, range.until ?? d.per_day[d.per_day.length - 1].day)
    : [];
  const byDay = new Map(d.per_day.map((x) => [x.day, x]));
  const rows = span.map((day) => {
    const x = byDay.get(day);
    return x ? { ...x } as unknown as Record<string, number> : {};
  });
  const perDay = (f: (x: Data["per_day"][number]) => number) => span.map((day) => {
    const x = byDay.get(day);
    return x ? f(x) : 0;
  });
  const series = ROUTE_ORDER.map((k) => ({ key: k, label: ROUTE[k], color: ROUTE_COLOR[k] }));
  const b = d.seconds.buckets;
  const histLabels = [...b.map((v, i) => `${i ? b[i - 1] : 0}–${v}s`), `>${b[b.length - 1]}s`];
  const spend = d.spend;
  const day = (label: string) => onDrill({ since: label, until: label });

  return (
    <div className="adm-stack">
      <div className="adm-cards">
        <Card label="Câu hỏi" value={fmtInt(d.questions)} trend={perDay((x) => x.questions)}
          sub={`${fmtInt(d.conversations)} cuộc trò chuyện · ${fmtInt(d.photos)} ảnh · ${fmtInt(d.accounts)} tài khoản`}
          onClick={() => onDrill({})} />
        <Card label="Hệ luật trả lời" value={fmtPct(decided ? (r.rules ?? 0) / decided : null)}
          trend={perDay((x) => x.rules)} trendColor={ROUTE_COLOR.rules}
          sub={`RAG ${fmtInt(ragAll)} (đệm ${fmtInt(r.rag_cache ?? 0)}) · chưa quyết định ${fmtInt(r.not_decided ?? 0)}`}
          onClick={() => onDrill({ route: "rules" })} />
        <Card label="👍 trên số đánh giá" value={fmtPct(d.feedback.up_share)}
          sub={`${d.feedback.up} 👍 · ${d.feedback.down} 👎 · ${d.feedback.corrected} sửa đáp án`} />
        <Card label="Thời gian (trung vị)" value={fmtSec(d.seconds.p50)}
          sub={`p95 ${fmtSec(d.seconds.p95)} · câu đầu trên ảnh mới ${fmtSec(d.seconds.first_on_photo_p50)} (${d.seconds.first_on_photo_n})`} />
        <Card label="Chi phí Claude" value={fmtUsd(d.cost_usd.total)} trend={perDay((x) => x.cost_usd)} trendColor="var(--medium)"
          sub={`${fmtUsd(d.cost_usd.per_answer, 4)}/câu · hạn mức: ${spend.spent != null ? `${fmtUsd(spend.spent)} / ${fmtUsd(spend.limit)}` : spend.loaded ? "không theo dõi" : "chưa có câu hỏi từ lần khởi động này"}`} />
        <Card label="Lỗi" value={fmtInt(r.error ?? 0)} sub={r.running ? `${r.running} câu đang trả lời` : undefined}
          onClick={r.error ? () => onDrill({ route: "error" }) : undefined} />
      </div>
      {d.questions === 0 ? (
        <p className="adm-muted">Không có câu hỏi nào trong khoảng thời gian này.</p>
      ) : (
        <div className="adm-grid">
          <StackedBars title="Câu hỏi mỗi ngày, theo cách trả lời" labels={span} rows={rows} series={series}
            onSelect={day} selectHint="Bấm để xem các câu hỏi của ngày này" />
          <ShareList title="Kết luận" onSelect={(k) => onDrill({ verdict: k })}
            items={Object.entries(d.verdicts).sort((a, b2) => b2[1] - a[1])
              .map(([k, v]) => ({ key: k, label: VERDICT[k] ?? k, value: v }))} />
          <ShareList title="Cách trả lời" onSelect={(k) => onDrill({ route: k })}
            items={ROUTE_ORDER.map((k) => ({ key: k, label: ROUTE[k], value: r[k] ?? 0, color: ROUTE_COLOR[k] }))} />
          <Bars title="Thời gian trả lời (số câu)" labels={histLabels} values={d.seconds.histogram} />
          <Bars title="Chi phí Claude mỗi ngày" labels={span} unit=" USD" color="var(--medium)"
            fmt={(v) => (v >= 1 ? v.toFixed(2) : v.toFixed(v ? 3 : 0))}
            values={perDay((x) => x.cost_usd)} onSelect={day} selectHint="Bấm để xem các câu hỏi của ngày này" />
        </div>
      )}
    </div>
  );
}
