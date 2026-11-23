import { useCallback, useEffect, useState } from "react";
import { Copy } from "../components/Icons";
import { admin, type Accounts as Data } from "./api";
import { fmtTime } from "./format";

function PasswordBox({ name, password, onClose }: { name: string; password: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const text = `Tài khoản SignCite: ${name}\nMật khẩu: ${password}`;
  return (
    <div className="adm-notice" role="status">
      <p>
        Mật khẩu của <b>{name}</b>: <code className="adm-password">{password}</code>
        <button type="button" className="adm-icon-btn" aria-label="Sao chép" onClick={() => {
          navigator.clipboard?.writeText(text).then(() => setCopied(true), () => {});
        }}><Copy size={16} /></button>
        {copied && <span className="adm-muted"> đã sao chép</span>}
      </p>
      <p className="adm-muted">Mật khẩu chỉ hiện một lần. Gửi riêng cho người thử (không gửi vào nhóm chung).</p>
      <button type="button" onClick={onClose}>Đã lưu, đóng lại</button>
    </div>
  );
}

export default function Accounts({ onError }: { onError: (e: unknown) => void }) {
  const [d, setD] = useState<Data | null>(null);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [shown, setShown] = useState<{ name: string; password: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => admin.accounts().then(setD, onError), [onError]);
  useEffect(() => {
    load();
  }, [load]);

  const run = async (f: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await f();
      await load();
    } catch (e) {
      onError(e);
    } finally {
      setBusy(false);
    }
  };

  const nextName = () => {
    const used = new Set(d?.items.map((a) => a.name));
    for (let i = 1; i < 100; i++) {
      const n = `p${String(i).padStart(2, "0")}`;
      if (!used.has(n)) return n;
    }
    return "";
  };

  return (
    <div className="adm-stack">
      <p className="adm-muted">
        Mỗi người thử một tài khoản đăng nhập trang SignCite. Câu hỏi được ghi kèm tài khoản đã hỏi.
        Thay đổi có hiệu lực ngay, không cần khởi động lại.
        {d?.shared_account && <> Tài khoản chung trong .env: <b>{d.shared_account}</b>.</>}
      </p>
      {d && !d.enabled && <p className="adm-error">Máy chủ này chưa bật tài khoản riêng (VQA_SITE_USERS_FILE).</p>}
      {shown && <PasswordBox {...shown} onClose={() => setShown(null)} />}
      <form className="adm-filters" onSubmit={(e) => {
        e.preventDefault();
        const n = (name || nextName()).trim().toLowerCase();
        run(async () => {
          const r = await admin.createAccount(n, note.trim() || null);
          setShown(r);
          setName("");
          setNote("");
        });
      }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={`Tên (để trống: ${nextName()})`}
          aria-label="Tên tài khoản" maxLength={32} />
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ghi chú (ví dụ: nhóm, giờ hẹn)"
          aria-label="Ghi chú" maxLength={200} />
        <button type="submit" className="adm-primary" disabled={busy || (d ? !d.enabled : true)}>Tạo tài khoản</button>
      </form>
      {d && (d.items.length === 0 ? <p className="adm-muted">Chưa có tài khoản nào.</p> : (
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr><th>Tài khoản</th><th>Ghi chú</th><th>Trạng thái</th><th className="adm-num">Câu hỏi</th>
                <th>Câu gần nhất</th><th>Tạo lúc</th><th /></tr>
            </thead>
            <tbody>
              {d.items.map((a) => (
                <tr key={a.name} className={a.enabled ? "" : "adm-disabled"}>
                  <td><b>{a.name}</b></td>
                  <td className="adm-muted">{a.note ?? ""}</td>
                  <td>{a.enabled ? "Đang dùng" : "Đã khoá"}</td>
                  <td className="adm-num">{a.questions}</td>
                  <td className="nowrap">{fmtTime(a.last_question_at)}</td>
                  <td className="nowrap">{fmtTime(a.created_at)}</td>
                  <td className="nowrap adm-actions">
                    <button type="button" disabled={busy} onClick={() => {
                      if (window.confirm(`Đặt mật khẩu mới cho ${a.name}? Mật khẩu cũ sẽ không dùng được nữa.`)) {
                        run(async () => setShown(await admin.resetPassword(a.name)));
                      }
                    }}>Mật khẩu mới</button>
                    <button type="button" disabled={busy} onClick={() => run(() => admin.setEnabled(a.name, !a.enabled))}>
                      {a.enabled ? "Khoá" : "Mở khoá"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {d && d.items.some((a) => a.enabled) && (
        <button type="button" disabled={busy} onClick={() => {
          if (window.confirm("Khoá tất cả tài khoản người thử? Tài khoản chung trong .env vẫn dùng được.")) {
            run(async () => {
              for (const a of d.items.filter((x) => x.enabled)) await admin.setEnabled(a.name, false);
            });
          }
        }}>Khoá tất cả</button>
      )}
    </div>
  );
}
