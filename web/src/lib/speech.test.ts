import { describe, expect, it } from "vitest";
import { mergeTranscript, type ResultLike } from "./speech";

const r = (transcript: string, isFinal = true): ResultLike => ({ isFinal, 0: { transcript } });

describe("mergeTranscript", () => {
  it("capitalises speech into an empty box", () => {
    expect(mergeTranscript("", [r("xe ô tô có được đi vào không")])).toBe("Xe ô tô có được đi vào không");
  });

  it("appends to what was typed, with one space", () => {
    expect(mergeTranscript("Biển số 1:  ", [r(" nghĩa là gì")])).toBe("Biển số 1: nghĩa là gì");
  });

  it("joins final and interim pieces and collapses spaces", () => {
    expect(mergeTranscript("", [r("xe tải "), r(" có được   đi", false)])).toBe("Xe tải có được đi");
  });

  it("leaves the box alone when nothing was heard", () => {
    expect(mergeTranscript("Câu cũ", [r("   ", false)])).toBe("Câu cũ");
    expect(mergeTranscript("Câu cũ", [])).toBe("Câu cũ");
  });
});
