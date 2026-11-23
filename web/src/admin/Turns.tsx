import { useEffect, useState } from "react";
import ProofTree from "../components/ProofTree";
import { Close } from "../components/Icons";
import { ANSWERED_BY, VERDICT } from "../lib/labels";
import type { TurnOut } from "../lib/types";
import { admin, type Page, type Range, type TurnSummary } from "./api";
import { fmtSec, fmtTime, fmtUsd, ROUTE, ROUTE_COLOR, shorten } from "./format";

export function RouteBadge({ route }: { route: string }) {
  return <span className="adm-badge" style={{ borderColor: ROUTE_COLOR[route], color: ROUTE_COLOR[route] }}>{ROUTE[route] ?? route}</span>;
}

function Rating({ t }: { t: TurnSummary }) {
  return (
    <span className="adm-rating">
      {t.thumb === "up" ? "👍" : t.thumb === "down" ? "👎" : ""}
      {t.corrected_answer ? " ✏️" : ""}
    </span>
  );
}

/** The public app's address for a turn, when this page runs on admin.<domain>. */
function appLink(turnId: string): string | null {
  const h = window.location.host;
  return h.startsWith("admin.") ? `${window.location.protocol}//${h.slice(6)}/#turn=${turnId}` : null;
}

export function TurnDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const [t, setT] = useState<TurnOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    admin.turn(id).then(setT, (e) => setErr(String(e?.message ?? e)));
  }, [id]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const link = appLink(id);
  return (
    <div className="adm-modal" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="adm-modal-box" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="adm-icon-btn adm-close" aria-label="Đóng" onClick={onClose}><Close size={18} /></button>
        {err && <p className="adm-error">{err}</p>}
        {!t && !err && <p className="adm-muted">Đang tải…</p>}
        {t && (
          <div className="adm-detail">
            <img src={`/v1/images/${t.image_sha256}`} alt="Ảnh của câu hỏi" />
            <div>
              <p className="adm-q">{t.question}</p>
              <p className="adm-a">{t.answer ?? t.error ?? "—"}</p>
              <p className="adm-muted">
                {VERDICT[t.verdict ?? ""] ?? t.verdict ?? "–"} · {t.basis.includes("rag") ? "RAG" : ANSWERED_BY[t.answered_by ?? ""] ?? t.answered_by ?? t.status} · {fmtSec(t.seconds)} · {fmtUsd(t.cost_usd, 4)}
                {link && <> · <a href={link} target="_blank" rel="noreferrer">mở trong ứng dụng</a></>}
              </p>
              {t.citations.length > 0 && (
                <div className="adm-chips">{t.citations.map((c) => <span key={c} className="chip">{c}</span>)}</div>
              )}
              {t.retrieved.length > 0 && (
                <ul className="adm-laws">{t.retrieved.map((l, i) => (
                  <li key={i}><b>{l.law_id} {l.article_id}</b>{l.score != null ? ` (${l.score.toFixed(2)})` : ""}: {shorten(l.text, 200)}</li>
                ))}</ul>
              )}
              {t.feedback.length > 0 && (
                <ul className="adm-laws">{t.feedback.map((f) => (
                  <li key={f.id}>{f.thumb === "up" ? "👍" : f.thumb === "down" ? "👎" : "✏️"} {f.corrected_answer ?? ""} {f.note ? `(${f.note})` : ""}</li>
                ))}</ul>
              )}
              {t.proof && <ProofTree proof={t.proof} signs={t.signs} />}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function TurnTable({ items, onOpen, showFeedback = false }: {
  items: TurnSummary[];
  onOpen: (id: string) => void;
  showFeedback?: boolean;
}) {
  if (!items.length) return <p className="adm-muted">Không có câu hỏi nào.</p>;
  return (
    <div className="adm-table-wrap">
      <table className="adm-table">
        <thead>
          <tr>
            <th>Lúc</th><th>Tài khoản</th><th>Câu hỏi</th><th>{showFeedback ? "Sửa / ghi chú" : "Trả lời"}</th>
            <th>Cách trả lời</th><th>Đánh giá</th><th className="adm-num">Thời gian</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.turn_id} onClick={() => onOpen(t.turn_id)} tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && onOpen(t.turn_id)}>
              <td className="nowrap">{fmtTime(t.created_at)}</td>
              <td>{t.account ?? "–"}</td>
              <td>{shorten(t.question, 90)}</td>
              <td className="adm-muted">{showFeedback
                ? shorten([t.corrected_answer, t.note].filter(Boolean).join(" · ") || t.answer, 120)
                : shorten(t.answer ?? t.error, 120)}</td>
              <td><RouteBadge route={t.route} /></td>
              <td><Rating t={t} /></td>
              <td className="adm-num nowrap">{fmtSec(t.seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const ROUTES = ["", "rules", "rag", "rag_cache", "fallback", "not_decided", "error"];
const RATINGS: Record<string, string> = { "": "Mọi đánh giá", up: "👍", down: "👎", corrected: "Có sửa đáp án", none: "Chưa đánh giá" };

export default function Turns({ range, onError }: { range: Range; onError: (e: unknown) => void }) {
  const [route, setRoute] = useState("");
  const [rating, setRating] = useState("");
  const [account, setAccount] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page<TurnSummary> | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const limit = 50;

  useEffect(() => setOffset(0), [range, route, rating, account, q]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      admin.turns(range, { route, rating, account: account.trim().toLowerCase(), q: q.trim(), limit, offset })
        .then(setPage, onError);
    }, 250);
    return () => window.clearTimeout(t);
  }, [range, route, rating, account, q, offset, onError]);

  return (
    <div className="adm-stack">
      <div className="adm-filters">
        <select value={route} onChange={(e) => setRoute(e.target.value)} aria-label="Cách trả lời">
          {ROUTES.map((r) => <option key={r} value={r}>{r ? ROUTE[r] : "Mọi cách trả lời"}</option>)}
        </select>
        <select value={rating} onChange={(e) => setRating(e.target.value)} aria-label="Đánh giá">
          {Object.entries(RATINGS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input value={account} onChange={(e) => setAccount(e.target.value)} placeholder="Tài khoản" aria-label="Tài khoản" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm trong câu hỏi, câu trả lời" aria-label="Tìm" />
      </div>
      {page && <TurnTable items={page.items} onOpen={setOpen} />}
      {page && page.total > limit && (
        <div className="adm-pager">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>‹ Trước</button>
          <span>{offset + 1}–{Math.min(page.total, offset + limit)} / {page.total}</span>
          <button type="button" disabled={offset + limit >= page.total} onClick={() => setOffset(offset + limit)}>Sau ›</button>
        </div>
      )}
      {open && <TurnDetail id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

export function FeedbackInbox({ range, onError }: { range: Range; onError: (e: unknown) => void }) {
  const [page, setPage] = useState<Page<TurnSummary> | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    admin.feedback(range).then(setPage, onError);
  }, [range, onError]);
  return (
    <div className="adm-stack">
      <p className="adm-muted">Các câu trả lời bị đánh giá 👎, có đáp án sửa hoặc có ghi chú của người dùng.</p>
      {page && <TurnTable items={page.items} onOpen={setOpen} showFeedback />}
      {open && <TurnDetail id={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
