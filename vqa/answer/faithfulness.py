"""The faithfulness guard (docs/plans/phase-4.md, item 1; DESIGN.md section 7).

Code, run on every writer reply. A reply passes only if:

1. it has the shape `{"verdict", "answer", "cited_signs", "cited_rules"}`;
2. its `verdict` equals the engine's;
3. every cited sign and rule is in the digest;
4. the text holds no sign code and no number missing from the digest or the
   question. Numbers the question states (a time, a weight, a speed) may be
   repeated, since they are not invented;
5. the first word has the verdict's polarity:
   - a true/false question ("đúng hay sai", "đúng không", "phải không", ...) starts
     with "Đúng" (yes) or "Sai" (no);
   - other yes/no verdicts start with a word the Yes/No scorer reads the same way
     (Đúng / Có / Được for yes; Sai / Không for no);
   - `unknown` and `uncertain` never start with a yes or no word.

`check` returns the list of failures (empty when the reply passes). It never
decides an answer.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from vqa.answer.digest import to_text

REPLY_KEYS = ("verdict", "answer", "cited_signs", "cited_rules")

# A sign code or an appendix article id as written in text: P.127b, W.207c, IE.452,
# DP.134, R.415a, S.504, B.25, F.10. Case-insensitive, an optional space after the dot.
CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{1,3})\.\s?(\d{1,3}[a-z]?)(?![0-9])")
# A number: digits with an optional decimal part (comma or dot), or a time 6:30 / 6h30.
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")

TRUE_FALSE_RE = re.compile(
    r"đúng\s+hay\s+sai|đúng\s+hoặc\s+sai|sai\s+hay\s+đúng|đúng\s+không|đúng\s+chứ|"
    r"phải\s+không|có\s+đúng\s+không|có\s+đúng\s+là|đúng\s+là\s+.+\s+không\s*\??\s*$",
    re.I)

_YES_WORDS = ("đúng", "có", "được")
_NO_WORDS = ("sai", "không")


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def is_true_false(question: str) -> bool:
    """A stated claim the dataset answers with Đúng / Sai."""
    return bool(TRUE_FALSE_RE.search(_nfc(question).lower()))


def leading_polarity(text: str) -> bool | None:
    """True / False when the text opens with a yes / no word, None otherwise.
    "Không được" is no (it starts with "không")."""
    t = _nfc(text).strip().lower().lstrip("\"'“”«»*-– ")
    first = re.split(r"[\s,.;:!?]+", t, maxsplit=1)[0] if t else ""
    if first in _NO_WORDS:
        return False
    if first in _YES_WORDS:
        return True
    return None


def codes_in(text: str) -> set[str]:
    return {f"{a.upper()}.{b.lower()}" for a, b in CODE_RE.findall(_nfc(text))}


def _readings(token: str) -> set[float]:
    """The values a number token can stand for: 1,25 or 1.25 -> 1.25; 1.000 -> 1.0 or 1000."""
    out: set[float] = set()
    for t in (token.replace(",", "."), token.replace(".", "").replace(",", "")):
        if t.count(".") <= 1:
            try:
                out.add(float(t))
            except ValueError:
                pass
    return out


def numbers_in(text: str) -> set[float]:
    out: set[float] = set()
    for tok in NUM_RE.findall(_nfc(text)):
        out |= _readings(tok)
        # a time or a range written with separators also contributes its parts
        for part in re.split(r"[.,]", tok):
            if part:
                out.add(float(part))
    return out


def _text_numbers(text: str) -> list[tuple[str, set[float]]]:
    return [(tok, _readings(tok)) for tok in NUM_RE.findall(_nfc(text))]


def check(reply: Any, digest: dict[str, Any], question: str) -> list[str]:
    """The guard's failures for one writer reply (empty list: the reply passes)."""
    if not isinstance(reply, dict):
        return ["the reply must be a JSON object"]
    errs: list[str] = []
    missing = [k for k in REPLY_KEYS if k not in reply]
    if missing:
        errs.append(f"missing keys: {', '.join(missing)}")
    if extra := sorted(set(reply) - set(REPLY_KEYS)):
        errs.append(f"unexpected keys: {', '.join(extra)}")
    text = reply.get("answer")
    if not isinstance(text, str) or not text.strip():
        errs.append("`answer` must be a non-empty string")
        text = ""
    signs, rules = reply.get("cited_signs", []), reply.get("cited_rules", [])
    if not isinstance(signs, list) or not all(isinstance(x, str) for x in signs):
        errs.append("`cited_signs` must be a list of sign ids")
        signs = []
    if not isinstance(rules, list) or not all(isinstance(x, str) for x in rules):
        errs.append("`cited_rules` must be a list of rule ids")
        rules = []

    verdict = digest["verdict"]
    if reply.get("verdict") != verdict:
        errs.append(f"verdict must be {verdict!r} (the engine's), not {reply.get('verdict')!r}")

    sign_ids = {s["id"] for s in digest.get("signs", [])}
    if bad := [s for s in signs if s not in sign_ids]:
        errs.append(f"cited_signs not in the proof: {', '.join(bad)}"
                    + (f" (allowed: {', '.join(sorted(sign_ids))})" if sign_ids else " (none allowed)"))
    rule_ids = {r["rule"] for r in digest.get("rules", [])}
    if bad := [r for r in rules if r not in rule_ids]:
        errs.append(f"cited_rules not in the proof: {', '.join(bad)}"
                    + (f" (allowed: {', '.join(sorted(rule_ids))})" if rule_ids else " (none allowed)"))

    source = to_text(digest) + "\n" + question
    if bad := sorted(codes_in(text) - codes_in(source)):
        errs.append(f"the text names codes that are not in the proof: {', '.join(bad)}")
    allowed = numbers_in(source)
    if bad := [tok for tok, vals in _text_numbers(text) if not (vals & allowed)
               and not all(float(p) in allowed for p in re.split(r"[.,]", tok) if p)]:
        errs.append(f"the text has numbers that are not in the proof or the question: {', '.join(bad)}")

    if text:
        pol = leading_polarity(text)
        if verdict in ("yes", "no"):
            want = verdict == "yes"
            if is_true_false(question):
                first = "Đúng" if want else "Sai"
                if not _nfc(text).strip().lstrip("\"'“”«»*-– ").lower().startswith(first.lower()):
                    errs.append(f"a true/false question is answered starting with {first!r}")
            elif pol is None:
                errs.append("a yes/no answer starts with its verdict word "
                            + ("(Có / Được / Đúng)" if want else "(Không / Sai)"))
            elif pol != want:
                errs.append(f"the text opens with a {'yes' if pol else 'no'} word, "
                            f"but the verdict is {verdict!r}")
        elif verdict in ("unknown", "uncertain") and pol is not None:
            errs.append(f"an {verdict!r} answer must not open with a yes or no word")
    return errs
