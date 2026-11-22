// Vietnamese labels for the API's values.

import type { Stage } from "./turn";

export const VERDICT: Record<string, string> = {
  yes: "Có / Đúng",
  no: "Không / Sai",
  unknown: "Chưa xác định",
  uncertain: "Chưa chắc chắn",
  value: "Giá trị",
};

export const ANSWERED_BY: Record<string, string> = {
  rules: "Hệ luật",
  fallback: "Dự phòng",
  not_decided: "Chưa quyết định",
};

export const CONFIDENCE: Record<string, string> = { high: "cao", medium: "trung bình", low: "thấp" };

export const TRUTH: Record<string, string> = { true: "đúng", false: "sai", unknown: "chưa rõ" };

export function stageLabel(s: Stage): string {
  const i = s.info;
  switch (s.name) {
    case "started":
      return "Bắt đầu xử lý";
    case "perception": {
      if (i.ok === false) return "Đọc ảnh thất bại";
      const n = Array.isArray(i.signs) ? i.signs.length : 0;
      return `Đọc ảnh: ${n} biển báo${i.cache_hit ? " (đã lưu)" : ""}`;
    }
    case "parsed":
      return i.status === "ok" ? "Hiểu câu hỏi" : `Hiểu câu hỏi: ${String(i.status ?? "?")}`;
    case "engine":
      return `Hệ luật: ${VERDICT[String(i.verdict)] ?? String(i.verdict ?? "?")}`;
    case "route":
      return i.to === "fallback" ? "Chuyển sang trả lời dự phòng" : "Viết câu trả lời";
    case "answer":
      return `Hoàn tất (${ANSWERED_BY[String(i.answered_by)] ?? String(i.answered_by ?? "")})`;
    default:
      return s.name;
  }
}

export const fmtSeconds = (t: number | null | undefined) => (t == null ? "" : `${t.toFixed(1)} s`);
