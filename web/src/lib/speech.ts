// Vietnamese speech-to-text with the browser's own recognizer (Web Speech API).
// Chrome and Edge send the audio to their vendor's speech service; Safari uses Apple's.
// Browsers without it (Firefox) get no microphone button.

import { useCallback, useEffect, useRef, useState } from "react";

export interface ResultLike {
  isFinal: boolean;
  0: { transcript: string };
}

interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ResultLike> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type RecognitionCtor = new () => RecognitionLike;

export function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** The question text: what was typed before speaking, then everything heard so far. */
export function mergeTranscript(base: string, results: ArrayLike<ResultLike>): string {
  let heard = "";
  for (let i = 0; i < results.length; i++) heard += results[i][0].transcript;
  heard = heard.replace(/\s+/g, " ").trim();
  if (!heard) return base;
  const head = base.trimEnd();
  return head ? `${head} ${heard}` : heard.charAt(0).toUpperCase() + heard.slice(1);
}

export const SPEECH_ERRORS: Record<string, string> = {
  "not-allowed": "Trình duyệt chưa cho phép dùng micro.",
  "service-not-allowed": "Trình duyệt chưa cho phép dùng micro.",
  "audio-capture": "Không tìm thấy micro.",
  "no-speech": "Không nghe thấy giọng nói. Hãy thử lại.",
  network: "Nhận dạng giọng nói cần kết nối mạng.",
  "language-not-supported": "Trình duyệt chưa hỗ trợ nhận dạng tiếng Việt.",
};

export function useSpeech(getBase: () => string, onText: (text: string) => void) {
  const Ctor = recognitionCtor();
  const rec = useRef<RecognitionLike | null>(null);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback(() => rec.current?.stop(), []);

  const start = useCallback(() => {
    if (!Ctor || rec.current) return;
    const r = new Ctor();
    r.lang = "vi-VN";
    r.interimResults = true;
    r.continuous = false; // stops after a pause
    const base = getBase();
    r.onresult = (e) => onText(mergeTranscript(base, e.results));
    r.onerror = (e) => {
      if (e.error !== "aborted") setError(SPEECH_ERRORS[e.error] ?? `Không nhận dạng được giọng nói (${e.error}).`);
    };
    r.onend = () => {
      rec.current = null;
      setListening(false);
    };
    rec.current = r;
    setError(null);
    setListening(true);
    try {
      r.start();
    } catch {
      rec.current = null;
      setListening(false);
      setError("Không bật được micro.");
    }
  }, [Ctor, getBase, onText]);

  useEffect(() => () => rec.current?.abort(), []);

  return { supported: !!Ctor, listening, error, start, stop };
}
