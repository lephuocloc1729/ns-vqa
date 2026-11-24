"""A readable view of the rule engine's proof (owner, 2026-11-24): the steps, and the rules behind them.

The engine's proof (kb/meta.pl via vqa/reasoning/explain.py) is complete but written in Prolog:
`assess(s2,p123a,[spec(vehicle,[])],veh(motor_vehicle,[]),ctx(unknown,unknown,unknown),[vehicle-true,…])`.
This module turns each reason's proof into

- `steps`: the steps that carry the argument, one row each, with the Prolog fact or rule on one side
  and a fixed Vietnamese sentence on the other: the sign read, what the sign rules, the vehicle
  match, the conditions (the routine ones folded into one row), the conclusion with its citations;
- `rules`: the rule clauses that concluded, as written in kb/, with a Vietnamese reading.

Every row comes from a node of the proof, and every sentence from a template below filled with the
proof's own values. No model writes anything, so the view is free, instant and always says what
the proof says. Anything this module does not know is shown as its Prolog text, never dropped.
Nothing here changes a verdict: the engine (vqa/) and the proof are untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------- Prolog terms


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class T:
    """A compound term (also `a-b` as T('-', (a, b)) and `\\+ g` as T('\\+', (g,)))."""
    f: str
    args: tuple = ()


class _Reader:
    """Reads the terms the meta-interpreter prints (write_canonical-like, plus `-` and `\\+`)."""

    def __init__(self, s: str) -> None:
        self.s, self.i = s, 0

    def peek(self) -> str:
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def eat(self, c: str) -> None:
        if self.peek() != c:
            raise ValueError(f"expected {c!r} at {self.i} in {self.s[:80]!r}")
        self.i += 1

    def term(self) -> Any:
        left = self.primary()
        if self.peek() == "-" and self.i + 1 < len(self.s) and not self.s[self.i + 1].isdigit():
            self.i += 1
            return T("-", (left, self.primary()))
        return left

    def primary(self) -> Any:
        c = self.peek()
        if self.s.startswith("\\+", self.i):
            self.i += 2
            return T("\\+", (self.term(),))
        if c == "[":
            self.i += 1
            items = []
            if self.peek() != "]":
                items.append(self.term())
                while self.peek() == ",":
                    self.i += 1
                    items.append(self.term())
            self.eat("]")
            return items
        if c == "(":
            self.i += 1
            t = self.term()
            self.eat(")")
            return t
        if c == "'":
            j = self.i + 1
            out = []
            while j < len(self.s):
                if self.s[j] == "\\" and j + 1 < len(self.s):
                    out.append(self.s[j + 1])
                    j += 2
                    continue
                if self.s[j] == "'":
                    if self.s[j + 1:j + 2] == "'":
                        out.append("'")
                        j += 2
                        continue
                    break
                out.append(self.s[j])
                j += 1
            self.i = j + 1
            name = "".join(out)
            return self.args_of(name)
        m = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?").match(self.s, self.i)
        if m:
            self.i = m.end()
            return float(m.group()) if (m.group(1) or m.group(2)) else int(m.group())
        m = re.compile(r"[A-Za-z_][A-Za-z0-9_]*").match(self.s, self.i)
        if not m:
            raise ValueError(f"unexpected {self.s[self.i:self.i + 10]!r}")
        self.i = m.end()
        name = m.group()
        if name[0].isupper() or name[0] == "_":
            return Var(name)
        return self.args_of(name)

    def args_of(self, name: str) -> Any:
        if self.i < len(self.s) and self.s[self.i] == "(":
            self.i += 1
            args = [self.term()]
            while self.peek() == ",":
                self.i += 1
                args.append(self.term())
            self.eat(")")
            return T(name, tuple(args))
        return name


def parse(goal: str | None) -> Any:
    """A goal's text as a term; None if it cannot be read (it is then shown as text)."""
    if not goal:
        return None
    try:
        r = _Reader(goal)
        t = r.term()
        return t if r.peek() in ("", ",") else None
    except (ValueError, IndexError):
        return None


def functor(t: Any) -> str:
    return t.f if isinstance(t, T) else (t if isinstance(t, str) else "")


# ---------------------------------------------------------------------- names in Vietnamese

ACTION = {
    "enter": "đi vào", "go_straight": "đi thẳng", "turn_left": "rẽ trái", "turn_right": "rẽ phải",
    "u_turn": "quay đầu xe", "overtake": "vượt xe", "stop": "dừng xe", "park": "đỗ xe", "honk": "bấm còi",
    "drive": "chạy xe", "pass": "đi qua",
}
CHECK = {
    "vehicle": "loại xe", "exception": "ngoại lệ", "plate": "biển phụ về loại xe", "time": "giờ",
    "day": "ngày", "scope": "phạm vi hiệu lực", "lane": "làn", "limit": "tốc độ so với giới hạn",
    "lane_closed": "làn dành riêng", "other_board": "biển làn khác", "direction": "hướng đi",
    "required": "hướng bắt buộc",
}
TRUTH = {"true": "✓", "false": "✗", "unknown": "?"}
WHY = {
    "vehicle_not_covered": "loại xe được hỏi không thuộc nhóm biển cấm",
    "excepted": "xe được hỏi thuộc ngoại lệ của biển",
    "plate_vehicle_not_covered": "biển phụ giới hạn loại xe, và xe được hỏi không thuộc loại đó",
    "outside_time_window": "thời điểm được hỏi nằm ngoài khung giờ của biển",
    "wrong_day": "ngày được hỏi không phải ngày biển có hiệu lực",
    "within_limit": "tốc độ được hỏi không vượt giới hạn",
    "lane_not_covered": "biển không áp dụng cho làn được hỏi",
    "vehicle_allowed_on_lane": "xe được hỏi được phép đi trên làn này",
    "direction_allowed": "hướng đi được hỏi không bị cấm",
    "not_the_only_direction": "đây không phải hướng duy nhất được phép",
    "action_not_covered": "biển không quy định hành vi được hỏi",
    "no_restricting_sign": "trong ảnh không có biển nào hạn chế việc này",
}
CONF = {"high": "cao", "medium": "trung bình", "low": "thấp"}


def vehicle_vi(cls: str) -> str:
    from vqa.answer.template import VEHICLE_VI
    if cls == "vehicle":
        return "mọi loại xe"
    return VEHICLE_VI.get(cls, cls)


CATEGORY = {"prohibitory": "biển cấm", "mandatory": "biển hiệu lệnh", "warning": "biển cảnh báo",
            "information": "biển chỉ dẫn", "auxiliary": "biển phụ"}


@lru_cache(maxsize=1)
def _catalog_by_atom() -> dict[str, tuple[str, str]]:
    try:
        from vqa.kb import load_catalog
        return {s.atom: (s.code, s.name_vi) for s in load_catalog().signs}
    except Exception:                      # the view must never break an answer
        return {}


def code_of(atom: Any) -> str:
    a = str(atom)
    hit = _catalog_by_atom().get(a)
    if hit:
        return hit[0]
    m = re.match(r"^([a-z]+)(\d.*)$", a)
    return f"{m.group(1).upper()}.{m.group(2)}" if m else a


def name_of(atom: Any) -> str | None:
    hit = _catalog_by_atom().get(str(atom))
    return hit[1] if hit else None


def _num(x: Any) -> str:
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return f"{x:g}" if isinstance(x, float) else str(x)


ATTR = {"load_t": ("tải", "t"), "gross_t": ("khối lượng toàn bộ", "t"), "axle_t": ("tải trục", "t"),
        "seats": ("số chỗ", ""), "height_m": ("chiều cao", "m"), "width_m": ("chiều rộng", "m"),
        "length_m": ("chiều dài", "m")}


def _attr_text(a: Any, vi: bool) -> str:
    """a(load_t, 5) or a(load_t, iv(Lo, LoIn, Hi, HiIn)) as "load > 5 t"."""
    if not (isinstance(a, T) and a.f == "a" and len(a.args) == 2):
        return pretty(a)
    name, v = a.args
    label, unit = ATTR.get(str(name), (str(name), "")) if vi else (str(name), "")
    unit = f" {unit}" if unit and vi else ""
    if isinstance(v, T) and v.f == "iv" and len(v.args) == 4:
        lo, lo_in, hi, hi_in = v.args
        parts = []
        if isinstance(lo, (int, float)) and lo > 0:
            parts.append(f"{'≥' if lo_in == 'true' else '>'} {_num(lo)}{unit}")
        if isinstance(hi, (int, float)) and hi < 1e15:
            parts.append(f"{'≤' if hi_in == 'true' else '<'} {_num(hi)}{unit}")
        return f"{label} {' và '.join(parts)}" if parts else label
    return f"{label} = {pretty(v) if not isinstance(v, (int, float)) else _num(v)}{unit}"


def veh_text(v: Any, vi: bool = True) -> str:
    """veh(truck, [a(load_t, iv(5,…))]) as "xe ô tô tải (tải > 5 t)"."""
    if isinstance(v, T) and v.f == "veh" and v.args:
        cls = str(v.args[0])
        attrs = v.args[1] if len(v.args) > 1 and isinstance(v.args[1], list) else []
        base = vehicle_vi(cls) if vi else cls
        extra = ", ".join(_attr_text(a, vi) for a in attrs)
        return f"{base} ({extra})" if extra else base
    return pretty(v)


def specs_text(specs: Any, vi: bool = True) -> str:
    if not isinstance(specs, list):
        return pretty(specs)
    out = []
    for s in specs:
        if isinstance(s, T) and s.f == "spec" and s.args:
            cls = str(s.args[0])
            attrs = s.args[1] if len(s.args) > 1 and isinstance(s.args[1], list) else []
            base = vehicle_vi(cls) if vi else cls
            extra = ", ".join(_attr_text(a, vi) for a in attrs)
            out.append(f"{base} ({extra})" if extra else base)
        else:
            out.append(pretty(s))
    if not vi:
        return "[" + ", ".join(out) + "]"
    return ", ".join(out[:-1]) + (" và " if len(out) > 1 else "") + out[-1] if out else "—"


def pretty(t: Any) -> str:
    """A term in short Prolog: spec(truck,[]) → truck, veh(…) → truck(load > 5), ctx(…) kept short."""
    if t is None:
        return ""
    if isinstance(t, Var):
        return "_"
    if isinstance(t, list):
        return "[" + ", ".join(pretty(x) for x in t) + "]"
    if isinstance(t, (int, float)):
        return _num(t)
    if isinstance(t, str):
        return t
    if t.f == "-" and len(t.args) == 2:
        return f"{pretty(t.args[0])}-{pretty(t.args[1])}"
    if t.f == "\\+":
        return "not " + pretty(t.args[0])
    if t.f == "spec" and t.args:
        attrs = t.args[1] if len(t.args) > 1 and isinstance(t.args[1], list) else []
        return str(t.args[0]) + (f"({', '.join(_attr_text(a, False) for a in attrs)})" if attrs else "")
    if t.f == "veh" and t.args:
        attrs = t.args[1] if len(t.args) > 1 and isinstance(t.args[1], list) else []
        return str(t.args[0]) + (f"({', '.join(_attr_text(a, False) for a in attrs)})" if attrs else "")
    if t.f == "ctx" and len(t.args) == 3:
        names = ("phút", "ngày", "làn")
        known = [f"{n}={pretty(a)}" for n, a in zip(names, t.args) if a != "unknown"]
        return "ctx(" + ", ".join(known) + ")" if known else ""
    return f"{t.f}(" + ", ".join(x for x in (pretty(a) for a in t.args) if x) + ")"


def _hm(minutes: Any) -> str:
    try:
        m = int(minutes)
        return f"{m // 60:02d}:{m % 60:02d}"
    except (TypeError, ValueError):
        return str(minutes)


def ctx_text(c: Any) -> str:
    if not (isinstance(c, T) and c.f == "ctx" and len(c.args) == 3):
        return ""
    minute, day, lane = c.args
    parts = []
    if minute != "unknown":
        parts.append(f"lúc {_hm(minute)}")
    if day != "unknown":
        parts.append(f"ngày {pretty(day)}")
    if lane != "unknown":
        parts.append(f"làn {pretty(lane)}")
    return ", ".join(parts)


# ---------------------------------------------------------------------- the steps

@dataclass
class Step:
    rule: str                       # the Prolog fact or rule, shortened
    text: str                       # what it means, in Vietnamese
    result: str                     # ✓ ✗ ? or a word (Cấm, Được, …)
    cite: list[str] = field(default_factory=list)
    decisive: bool = False          # the condition that decided the answer (✗ or ?)
    sign_id: str | None = None      # a step about a sign: the page can show it on the photo
    detail: list["Step"] = field(default_factory=list)   # folded rows (the routine conditions)

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"rule": self.rule, "text": self.text, "result": self.result}
        if self.cite:
            d["cite"] = self.cite
        if self.decisive:
            d["decisive"] = True
        if self.sign_id:
            d["sign_id"] = self.sign_id
        if self.detail:
            d["detail"] = [x.as_dict() for x in self.detail]
        return d


def _cite(node: dict[str, Any]) -> str | None:
    src = node.get("source") or {}
    if not src.get("law_id"):
        return None
    if src.get("law_id") == "interpretation":
        return "diễn giải của nhóm (không phải trích dẫn luật)"
    return f"{src['law_id']} {src.get('article_id', '')}".strip()


def _walk(node: dict[str, Any]):
    yield node
    for c in node.get("children") or []:
        yield from _walk(c)


def _facts_under(node: dict[str, Any]) -> list[Any]:
    return [parse(n.get("goal")) for n in _walk(node) if n.get("type") == "fact" and n.get("goal")]


def _check_list(t: Any) -> list[tuple[str, str]] | None:
    """The `[vehicle-true, time-false, …]` list a checking rule ends with."""
    if isinstance(t, T) and t.args and isinstance(t.args[-1], list) and t.args[-1] and all(
            isinstance(x, T) and x.f == "-" and len(x.args) == 2 for x in t.args[-1]):
        return [(str(x.args[0]), str(x.args[1])) for x in t.args[-1]]
    return None


def _check_node(assess: dict[str, Any], name: str) -> dict[str, Any] | None:
    """The child of a checking rule that decided one check (time_check for `time`, …)."""
    want = {"time": "time_check", "day": "day_check", "plate": "plate_check", "scope": "scope_check",
            "lane": "lane_check", "exception": "exception_check"}.get(name)
    for n in _walk(assess):
        if want and functor(parse(n.get("goal"))) == want:
            return n
    return None


def _check_step(name: str, truth: str, assess: dict[str, Any], vehicle: Any, specs: Any,
                ctx: Any, sid: str | None, plates: list[str] | None = None) -> Step:
    label = CHECK.get(name, name)
    rule = f"{name}-{truth}"
    node = _check_node(assess, name)
    facts = _facts_under(node) if node else []
    # what the proof says about the plate: absent (a negation-as-failure node) or present (a fact/leaf)
    under = [(x.get("type"), functor(parse(x.get("goal")))) for x in _walk(node)] if node else []
    no_plate = lambda f: ("naf", f) in under and not any(t != "naf" and g == f for t, g in under)  # noqa: E731
    asked = ctx_text(ctx)
    if name == "vehicle":
        v = veh_text(vehicle)
        group = specs_text(specs) if specs is not None else "của biển"
        text = {"true": f"Xe được hỏi ({v}) thuộc nhóm biển áp dụng: {group}",
                "false": f"Xe được hỏi ({v}) không thuộc nhóm biển áp dụng: {group}",
                "unknown": f"Chưa rõ xe được hỏi ({v}) có thuộc nhóm {group} không "
                           "(câu hỏi thiếu thông tin như tải trọng, số chỗ)"}[truth]
        return Step(rule, text, TRUTH.get(truth, truth), decisive=truth != "true", sign_id=sid)
    if name == "time":
        windows = [f"{_hm(f.args[1])}–{_hm(f.args[2])}" for f in facts
                   if isinstance(f, T) and f.f == "plate_time" and len(f.args) >= 3]
        w = ", ".join(windows) or ", ".join(f"«{p}»" for p in plates or [])
        has_plate = any(g in ("has_time_plate", "plate_time") and t != "naf" for t, g in under)
        if has_plate:
            yes = f"Thời điểm được hỏi{(' (' + asked + ')') if asked else ''} nằm trong khung giờ " \
                  f"{w or 'ghi trên biển phụ'} ⇒ biển áp dụng"
        elif no_plate("plate_time"):
            yes = "Không có biển phụ giới hạn giờ ⇒ biển áp dụng cả ngày"
        else:
            yes = "Biển áp dụng vào thời điểm được hỏi"
        text = {"true": yes,
                "false": f"Thời điểm được hỏi{(' (' + asked + ')') if asked else ''} nằm ngoài khung giờ {w or 'của biển'}",
                "unknown": f"Biển chỉ áp dụng trong khung giờ {w or 'ghi trên biển phụ'}, "
                           "nhưng câu hỏi không nói giờ"}[truth]
        return Step(rule, text, TRUTH.get(truth, truth), decisive=truth != "true")
    simple = {
        "exception": ("Xe được hỏi không thuộc ngoại lệ của biển", "Xe được hỏi thuộc ngoại lệ của biển",
                      "Chưa rõ xe có thuộc ngoại lệ của biển không"),
        "plate": ("Không có biển phụ về loại xe" if no_plate("plate_vehicle") else
                  "Biển phụ về loại xe áp dụng cho xe này",
                  "Biển phụ giới hạn loại xe, và xe được hỏi không thuộc loại đó",
                  "Chưa rõ biển phụ về loại xe có áp dụng cho xe này không"),
        "day": ("Biển áp dụng vào ngày được hỏi (hoặc không giới hạn ngày)",
                "Ngày được hỏi không phải ngày biển có hiệu lực",
                "Biển chỉ áp dụng vào một số ngày, nhưng câu hỏi không nói ngày"),
        "scope": ("Không có biển hết hiệu lực trong ảnh", "Trong ảnh có biển báo hết hiệu lực",
                  "Chưa rõ biển còn hiệu lực không"),
        "lane": ("Biển áp dụng cho làn được hỏi (hoặc mọi làn)", "Biển không áp dụng cho làn được hỏi",
                 "Biển chỉ áp dụng cho một số làn, nhưng câu hỏi không nói làn"),
        "limit": ("Tốc độ được hỏi vượt giới hạn của biển", "Tốc độ được hỏi không vượt giới hạn của biển",
                  "Chưa rõ tốc độ có vượt giới hạn không"),
        "lane_closed": ("Làn được hỏi dành riêng cho xe khác, xe này không được đi",
                        "Xe được hỏi được đi trên làn này", "Chưa rõ làn này có dành cho xe được hỏi không"),
        "other_board": ("Không có biển làn khác cho phép xe này", "Một biển làn khác cho phép xe này",
                        "Chưa rõ các biển làn khác"),
    }
    if name in simple:
        yes, no, unk = simple[name]
        text = {"true": yes, "false": no, "unknown": unk}[truth]
    else:
        text = f"Điều kiện «{label}»: " + {"true": "thỏa", "false": "không thỏa", "unknown": "chưa rõ"}[truth]
    return Step(rule, text, TRUTH.get(truth, truth), decisive=truth != "true")


CONCLUSION = {
    # top rule -> (Vietnamese when the reason is true, when false); {a} action, {v} vehicle
    "forbids": ("Đủ mọi điều kiện ⇒ biển cấm {v} {a}", "Biển không cấm {v} {a}"),
    "clears": ("Biển không cấm {v} {a}", "Biển không cấm {v} {a}"),
    "general_forbids": ("Theo quy tắc chung của Luật, {v} không được {a} ở đây",
                        "Quy tắc chung của Luật không cấm {v} {a} ở đây"),
    "speed_violation": ("Tốc độ được hỏi vượt giới hạn của biển ⇒ vi phạm", "Tốc độ được hỏi không vi phạm"),
    "speed_clears": ("Tốc độ được hỏi không vi phạm biển này", "Tốc độ được hỏi không vi phạm biển này"),
    "limit_candidate": ("Biển này cho giới hạn tốc độ áp dụng với xe được hỏi", "Biển này không áp dụng với xe được hỏi"),
    "lane_block": ("Xe được hỏi không được đi trên làn này", "Xe được hỏi được đi trên làn này"),
    "lane_clears": ("Xe được hỏi được đi trên làn này", "Xe được hỏi được đi trên làn này"),
    "sign_identity": ("Biển đúng là biển được hỏi", "Biển không phải biển được hỏi"),
    "unrelated_sign": ("Biển không quy định việc {a} ⇒ không cấm", "Biển không quy định việc {a} ⇒ không cấm"),
    "\\+": ("Trong ảnh không có biển nào hạn chế việc này ⇒ được phép", "Trong ảnh không có biển nào hạn chế việc này"),
    "required": ("Biển bắt buộc việc được hỏi", "Biển không bắt buộc việc được hỏi"),
    "covers": ("Biển áp dụng cho đối tượng được hỏi", "Biển không áp dụng cho đối tượng được hỏi"),
    "unrelated_speed_sign": ("Biển không phải biển tốc độ", "Biển không phải biển tốc độ"),
    "c38_outside_limit": ("Tốc độ được hỏi vượt tốc độ tối đa theo Thông tư 38/2024 cho loại đường này",
                          "Tốc độ được hỏi không vượt tốc độ tối đa theo Thông tư 38/2024"),
    "vehicle_class_truth": ("Xe được hỏi thuộc loại xe được nói đến", "Xe được hỏi không thuộc loại xe được nói đến"),
    "must_yield": ("Xe được hỏi phải nhường đường", "Xe được hỏi không phải nhường đường"),
    "precedence_truth": ("Thứ tự ưu tiên giữa các hiệu lệnh đúng như câu hỏi nói",
                         "Thứ tự ưu tiên giữa các hiệu lệnh không như câu hỏi nói"),
    "light_forbids": ("Đèn tín hiệu cấm việc được hỏi", "Đèn tín hiệu không cấm việc được hỏi"),
    "officer_forbids": ("Hiệu lệnh của người điều khiển giao thông cấm việc được hỏi",
                        "Hiệu lệnh của người điều khiển giao thông không cấm việc được hỏi"),
    "marking_forbids": ("Vạch kẻ đường cấm việc được hỏi", "Vạch kẻ đường không cấm việc được hỏi"),
    "tunnel_stop": ("Không được dừng, đỗ xe trong hầm", "Quy tắc trong hầm không áp dụng"),
    "row_basis": ("Căn cứ quyền ưu tiên đi trước", "Không có căn cứ quyền ưu tiên"),
    "requirement_clears": ("Biển không bắt buộc việc được hỏi", "Biển không bắt buộc việc được hỏi"),
}
RESULT = {"forbids": "Cấm", "general_forbids": "Cấm", "speed_violation": "Vi phạm", "lane_block": "Không được",
          "required": "Bắt buộc", "sign_identity": "Đúng"}


def _action_vehicle(top: Any) -> tuple[str, str]:
    a, v = "", ""
    if isinstance(top, T):
        for x in top.args:
            if isinstance(x, str) and x in ACTION and not a:
                a = ACTION[x]
            if isinstance(x, T) and x.f == "veh" and not v:
                v = veh_text(x)
    return a or "làm việc được hỏi", v or "xe được hỏi"


def reason_view(reason: dict[str, Any], signs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One reason's steps. None when the reason has no proof."""
    proof = reason.get("proof")
    if not proof:
        return None
    number = {s.get("id"): (i + 1, s) for i, s in enumerate(signs or [])}
    top = parse(proof.get("goal")) if proof.get("goal") else None
    top_f = functor(top) if top is not None else (proof.get("rule") or "")
    steps: list[Step] = []
    cites: list[str] = []
    shown_codes: set[str] = set()
    folded_routine: list[Step] = []
    vehicle = None
    for n in _walk(proof):
        t = parse(n.get("goal"))
        f = functor(t)
        typ = n.get("type")
        if typ == "cite":
            c = _cite(n)
            if c and c not in cites:
                cites.append(c)
            continue
        if isinstance(t, T) and f == "veh" and vehicle is None:
            vehicle = t
        if typ == "fact" and f == "sign" and isinstance(t, T) and len(t.args) >= 2:
            sid, code = str(t.args[0]), t.args[1]
            if f"sign:{sid}" in shown_codes:
                continue
            shown_codes.add(f"sign:{sid}")
            num, _s = number.get(sid, (None, None))
            name = name_of(code)
            conf = CONF.get(str(t.args[2]), str(t.args[2])) if len(t.args) > 2 else None
            label = f"Biển {num}" if num else "Biển"
            text = f"{label} trong ảnh được đọc là {code_of(code)}" + (f" ({name})" if name else "") + \
                   (f", độ tin cậy {conf}" if conf else "")
            steps.append(Step(f"sign({sid}, {code_of(code)})", text, "✓", sign_id=sid))
            continue
        if typ == "fact" and f == "prohibits" and isinstance(t, T) and len(t.args) == 3:
            code, act, specs = t.args
            key = f"prohibits:{code}:{act}"
            if key in shown_codes:
                continue
            shown_codes.add(key)
            c = _cite(n)
            steps.append(Step(f"prohibits({code_of(code)}, {act}, {specs_text(specs, vi=False)})",
                              f"{code_of(code)} cấm {specs_text(specs)} {ACTION.get(str(act), str(act))}",
                              "✓", cite=[c] if c else []))
            continue
        if typ == "fact" and f == "catalog_sign" and isinstance(t, T) and len(t.args) >= 2 \
                and top_f in ("unrelated_sign", "unrelated_speed_sign", "sign_identity") \
                and f"cat:{t.args[0]}" not in shown_codes:
            shown_codes.add(f"cat:{t.args[0]}")
            c = _cite(n)
            steps.append(Step(f"catalog_sign({code_of(t.args[0])}, {t.args[1]})",
                              f"{code_of(t.args[0])} là {CATEGORY.get(str(t.args[1]), str(t.args[1]))}",
                              "✓", cite=[c] if c else []))
            continue
        if typ == "naf" and f == "effective_prohibits" and isinstance(t, T) and len(t.args) >= 3:
            code, act = t.args[1], t.args[2]
            steps.append(Step(f"not prohibits({code_of(code)}, {pretty(act)})",
                              f"{code_of(code)} không có quy định cấm {ACTION.get(str(act), str(act))}",
                              "✗", decisive=True))
            continue
        if typ == "fact" and f in ("max_speed_for", "min_speed_for") and isinstance(t, T) and len(t.args) == 2:
            code, cls = t.args
            c = _cite(n)
            kind = "tối đa" if f == "max_speed_for" else "tối thiểu"
            steps.append(Step(f"{f}({code_of(code)}, {cls})",
                              f"{code_of(code)} là biển tốc độ {kind}, áp dụng cho {vehicle_vi(str(cls))}",
                              "✓", cite=[c] if c else []))
            continue
        if f in ("sign_value", "limit_value") and isinstance(t, T) and len(t.args) == 2 and "value" not in shown_codes:
            shown_codes.add("value")
            steps.append(Step(f"{f}({t.args[0]}, {pretty(t.args[1])})", f"Biển ghi {pretty(t.args[1])} km/h", "✓"))
            continue
        if f == "cmp_truth" and isinstance(t, T) and len(t.args) == 4:
            op, a, b, tr = t.args
            sym = {"gt": ">", "ge": "≥", "lt": "<", "le": "≤"}.get(str(op), str(op))
            steps.append(Step(f"{pretty(a)} {sym} {pretty(b)}",
                              f"Tốc độ được hỏi {pretty(a)} km/h {sym} giới hạn {pretty(b)} km/h: "
                              + {"true": "đúng", "false": "sai", "unknown": "chưa rõ"}.get(str(tr), str(tr)),
                              TRUTH.get(str(tr), str(tr))))
            continue
        if f == "lane_specs" and isinstance(t, T) and len(t.args) == 3:
            steps.append(Step(f"lane_specs({t.args[0]}, {t.args[1]}, {specs_text(t.args[2], vi=False)})",
                              f"Làn {t.args[1]} dành cho {specs_text(t.args[2])}", "✓"))
            continue
        if f == "meaning_truth" and isinstance(t, T) and len(t.args) == 3:
            code, meaning, tr = t.args
            steps.append(Step(f"meaning({code_of(code)}, {pretty(meaning)})",
                              f"Ý nghĩa của {code_of(code)} {'là' if tr == 'true' else 'không phải là'} «{pretty(meaning)}»",
                              TRUTH.get(str(tr), str(tr))))
            continue
        if typ == "fact" and f in ("attr_interpretation", "class_interpretation"):
            steps.append(Step(pretty(t), "Diễn giải của nhóm: "
                              + ("tải trọng chở hàng > x ⇒ khối lượng toàn bộ > x (QCVN 41 B.15)"
                                 if "load_implies_gross" in (n.get("goal") or "") else f"«{pretty(t.args[0])}»"),
                              "ℹ"))
            continue
        checks = _check_list(t)
        if checks and f != "assess" and any(functor(parse(x.get("goal"))) == "assess"
                                            for x in _walk(n) if x is not n):
            continue                            # the 7 conditions come from the nested assess
        if checks and f in ("assess", "max_speed_sign", "lane_sign_checks", "zone_checks"):
            specs = t.args[2] if f == "assess" and len(t.args) > 2 else None
            ctx = next((a for a in t.args if isinstance(a, T) and a.f == "ctx"), None)
            veh = next((a for a in t.args if isinstance(a, T) and a.f == "veh"), vehicle)
            sid = str(t.args[0]) if f == "assess" else None
            plates = [str(x) for x in (number.get(sid, (None, {}))[1] or {}).get("plates") or []] if sid else []
            routine = []
            for name, truth in checks:
                if name == "limit":
                    continue                    # shown by the comparison row (cmp_truth)
                if name == "vehicle" and specs is not None:
                    steps.append(_check_step(name, truth, n, veh, specs, ctx, sid, plates))
                    continue
                st = _check_step(name, truth, n, veh, specs, ctx, sid, plates)
                (routine if truth == "true" else steps).append(st)
            if routine:
                folded_routine = routine
                names = ", ".join(CHECK.get(s.rule.split("-")[0], s.rule) for s in routine)
                steps.append(Step(f"{len(routine)} điều kiện khác", f"Không có điều kiện nào giới hạn: {names}",
                                  f"✓ {len(routine)}/{len(routine)}", detail=routine))
            continue
    # the conclusion
    truth = reason.get("truth")
    a, v = _action_vehicle(top)
    yes, no = CONCLUSION.get(top_f, (None, None))
    detail = reason.get("detail")
    if truth == "unknown":
        text = "Chưa đủ dữ kiện để kết luận: xem điều kiện «?» ở trên"
    elif yes:
        text = (yes if truth == "true" else no).format(a=a, v=v)
    else:
        text = f"Kết luận của luật {top_f}"
    if top_f in ("unrelated_sign", "unrelated_speed_sign", "\\+"):
        pass                                    # the rows above already say why
    elif detail and detail in WHY:
        text += f" — vì {WHY[detail]}"
    elif detail:
        text += f" — {detail}"
    result = RESULT.get(top_f, "") if truth == "true" else ""
    result = result or {"true": "Đúng", "false": "Không áp dụng", "unknown": "Chưa xác định"}.get(str(truth), "")
    head = pretty(top) if top is not None else (proof.get("goal") or proof.get("rule") or "")
    steps.append(Step(f"⇒ {head}", text, result, cite=cites))
    sid = reason.get("sign_id")
    num, s = number.get(sid, (None, None))
    title = (f"Biển {num} · {s.get('code')}" + (f" — {s.get('name')}" if s.get("name") else "")) if num else None
    _ = folded_routine
    return {"sign_id": sid, "title": title, "truth": truth, "steps": [x.as_dict() for x in steps],
            "rules": rule_cards(proof)}


def explain(proof: dict[str, Any] | None, signs: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """The readable view of an engine answer (the API's `proof`), or None."""
    if not proof:
        return None
    out = []
    for r in proof.get("reasons") or []:
        try:
            v = reason_view(r, signs or [])
        except Exception:                  # never break an answer: the raw tree is still there
            v = None
        if v:
            out.append(v)
    return out or None


# ---------------------------------------------------------------------- the rules, as written in kb/

READING = {
    "forbids": "Biển S cấm xe Veh làm hành vi Action khi: (1) trong ảnh có biển S với mã Code; (2) mã đó (hoặc biển "
               "phụ ghi chữ của nó) cấm Action với nhóm xe Specs; (3) theo Điều 22 QCVN 41 về biển cấm; (4) và biển "
               "áp dụng cho xe này: đủ cả 7 điều kiện (loại xe, ngoại lệ, biển phụ, giờ, ngày, phạm vi, làn).",
    "clears": "Biển S không cấm xe Veh làm Action khi biển có quy định về Action nhưng ít nhất một trong 7 điều kiện "
              "không thỏa; Why là điều kiện đầu tiên không thỏa (ví dụ: xe không thuộc nhóm bị cấm, ngoài khung giờ).",
    "applies": "Biển áp dụng cho xe này khi kết quả của cả 7 điều kiện (assess) đều đúng.",
    "assess": "Kiểm tra 7 điều kiện của một biển với xe và hoàn cảnh được hỏi: loại xe, ngoại lệ, biển phụ về loại xe, "
              "giờ, ngày, phạm vi hiệu lực, làn. Mỗi điều kiện ra đúng, sai hoặc chưa rõ (thiếu dữ kiện).",
    "speed_violation": "Xe vi phạm tốc độ khi trong ảnh có biển tốc độ tối đa áp dụng cho xe này và tốc độ được hỏi "
                       "lớn hơn con số trên biển.",
    "speed_clears": "Xe không vi phạm biển tốc độ khi tốc độ không vượt con số trên biển, hoặc biển không áp dụng cho xe.",
    "max_speed_sign": "Kiểm tra một biển tốc độ tối đa: so tốc độ được hỏi với con số trên biển, rồi 7 điều kiện "
                      "áp dụng như với biển cấm.",
    "limit_candidate": "Một biển tốc độ cho giới hạn áp dụng với xe được hỏi: biển tốc độ tối đa (hoặc tối thiểu) "
                       "trong ảnh, con số ghi trên biển, và biển áp dụng cho xe này.",
    "lane_block": "Xe không được đi trên một làn khi biển làn (QCVN 41 D.14) dành làn đó cho loại xe khác và không "
                  "có ngoại lệ, giờ hay biển làn khác cho phép xe này.",
    "lane_clears": "Xe được đi trên làn khi biển làn cho phép loại xe này trên làn đó.",
    "lane_sign_checks": "Kiểm tra một biển làn với xe và làn được hỏi: làn có dành riêng không, ngoại lệ, giờ, ngày, "
                        "và các biển làn khác.",
    "sign_identity": "Biển được chọn đúng là biển được hỏi khi mã biển trong danh mục có ý nghĩa (hoặc mã, nhóm) "
                     "đúng như câu hỏi nói.",
    "unrelated_sign": "Biển không liên quan đến câu hỏi khi đó là biển hạn chế nhưng không quy định hành vi được hỏi.",
    "\\+": "Mặc định được phép: không tìm thấy biển nào trong ảnh hạn chế việc được hỏi (phủ định do thất bại "
           "– negation as failure – trên tập biển đã đọc).",
    "general_forbids": "Quy tắc chung của Luật Trật tự, an toàn giao thông đường bộ 2024 (không cần biển), "
                       "ví dụ cấm dừng đỗ ở một số nơi.",
}


@lru_cache(maxsize=1)
def _kb_clauses() -> dict[str, list[str]]:
    """Every clause in kb/, by functor, as written (comments kept out)."""
    out: dict[str, list[str]] = {}
    for p in sorted((ROOT / "kb").rglob("*.pl")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("%")]
        buf: list[str] = []
        for ln in lines:
            if not buf and (not ln.strip() or ln.startswith((" ", "\t", ":-"))):
                continue
            buf.append(ln.rstrip())
            code = re.sub(r"%.*$", "", ln).rstrip()
            if code.endswith(".") and not code.endswith(".."):
                clause = "\n".join(buf).strip()
                m = re.match(r"([a-z_][a-zA-Z0-9_]*)\(", clause)
                if m and ":-" in clause:
                    out.setdefault(m.group(1), []).append(clause)
                buf = []
    return out


def _body_functors(clause: str) -> list[str]:
    body = clause.split(":-", 1)[1]
    return re.findall(r"(?<![a-zA-Z0-9_])([a-z_][a-zA-Z0-9_]*)\(", body)


def clause_for(node: dict[str, Any]) -> str | None:
    """The kb/ clause whose body best matches this proof node's children, as written."""
    f = functor(parse(node.get("goal")))
    clauses = _kb_clauses().get(f)
    if not clauses:
        return None
    kids = [functor(parse(c.get("goal"))) or c.get("rule") or "" for c in node.get("children") or []]
    kids = [k for k in kids if k]

    def score(c: str) -> tuple[int, int]:
        body = _body_functors(c)
        hit = sum(1 for k in kids if k in body or (k == "r_prohibition" and "cite" in body))
        return hit, -len(body)
    return max(clauses, key=score)


def rule_cards(proof: dict[str, Any]) -> list[dict[str, Any]]:
    """The main rules of a proof (those with a reading), each with its clause as written in kb/."""
    cards, seen = [], set()
    top_f = functor(parse(proof.get("goal")))
    if top_f == "\\+":
        return [{"name": "không có biển hạn chế", "clause": proof.get("goal"), "reading": READING["\\+"]}]
    for n in _walk(proof):
        if n.get("type") != "rule":
            continue
        f = functor(parse(n.get("goal")))
        if f in READING and f not in seen:
            seen.add(f)
            cards.append({"name": f, "clause": clause_for(n), "reading": READING[f]})
    return cards
