import { forwardRef, useCallback, useRef } from "react";
import { useSpeech } from "../lib/speech";
import { Camera, Clip, Close, Mic, Send } from "./Icons";

export const ACCEPTED = ["image/jpeg", "image/png", "image/webp"];

export interface ComposerPhoto {
  url: string;
  name: string | null; // a new file's name; null for the photo of an earlier question
  size: number | null;
}

const mb = (n: number) => `${(n / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;

const Composer = forwardRef<HTMLTextAreaElement, {
  photo: ComposerPhoto | null;
  question: string;
  busy: boolean;
  error: string | null;
  onQuestion: (q: string) => void;
  onPick: (f: File) => void;
  onClearPhoto: () => void;
  onSubmit: () => void;
}>(function Composer({ photo, question, busy, error, onQuestion, onPick, onClearPhoto, onSubmit }, ref) {
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const take = (files: FileList | null) => {
    const f = files && files[0];
    if (f) onPick(f);
  };
  const latest = useRef(question);
  latest.current = question;
  const speech = useSpeech(useCallback(() => latest.current, []), onQuestion);
  const canSend = !busy && !!question.trim() && !!photo;
  const submit = () => {
    if (!canSend) return;
    speech.stop();
    onSubmit();
  };
  return (
    <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      {photo && (
        <div className="composer-photo">
          <img src={photo.url} alt="" />
          <div className="composer-photo-text">
            <span>{photo.name ?? "Hỏi tiếp về ảnh này"}</span>
            {photo.size != null && <span className="muted small">{mb(photo.size)}</span>}
          </div>
          <button type="button" className="icon-btn small" disabled={busy} onClick={onClearPhoto} aria-label="Bỏ ảnh">
            <Close size={14} />
          </button>
        </div>
      )}
      <div className="composer-row">
        <label htmlFor="question" className="sr-only">Câu hỏi</label>
        <textarea id="question" ref={ref} rows={1} maxLength={500} value={question}
          placeholder={photo ? "Đặt câu hỏi về ảnh…" : "Thêm ảnh rồi hỏi…"}
          onChange={(e) => {
            onQuestion(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }} />
        <input ref={fileRef} type="file" accept={ACCEPTED.join(",")} hidden data-testid="file-input"
          onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
        <input ref={camRef} type="file" accept="image/*" capture="environment" hidden
          onChange={(e) => { take(e.target.files); e.target.value = ""; }} />
        <button type="button" className="icon-btn" disabled={busy} onClick={() => fileRef.current?.click()}
          aria-label="Đính kèm ảnh" title="Đính kèm ảnh"><Clip /></button>
        {/* the camera is for phones and tablets; a desktop gets the microphone in its place */}
        <button type="button" className="icon-btn touch-only" disabled={busy} onClick={() => camRef.current?.click()}
          aria-label="Chụp ảnh" title="Chụp ảnh"><Camera /></button>
        {speech.supported && (
          <button type="button" className={`icon-btn mic${speech.listening ? " listening" : ""}`} disabled={busy}
            aria-pressed={speech.listening} aria-label={speech.listening ? "Dừng nghe" : "Hỏi bằng giọng nói"}
            title={speech.listening ? "Dừng nghe" : "Hỏi bằng giọng nói (tiếng Việt)"}
            onClick={() => (speech.listening ? speech.stop() : speech.start())}><Mic /></button>
        )}
        <button type="submit" className="send-btn" disabled={!canSend} aria-label="Gửi" title="Gửi">
          <Send />
        </button>
      </div>
      {speech.listening && <p className="listening-hint" role="status">Đang nghe… nói câu hỏi bằng tiếng Việt.</p>}
      {(error || speech.error) && <p className="err" role="alert">{error ?? speech.error}</p>}
    </form>
  );
});

export default Composer;
