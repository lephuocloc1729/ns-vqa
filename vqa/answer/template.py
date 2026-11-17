"""Deterministic Vietnamese answers built from the digest (docs/plans/phase-4.md, item 1).

Used when the writer's reply fails the guard twice, so the shipped answer never
contradicts the engine. A template answer is the verdict in the dataset's style,
then the main reason and its citation:

    "Sai. Căn cứ: biển P.107a (Cấm xe ô tô khách), QCVN 41:2024/BGTVT B.7a."

Every template answer passes the guard by construction (tests check this).
"""

from __future__ import annotations

from typing import Any

from vqa.answer.faithfulness import is_true_false
from vqa.schemas import VehicleClass

VEHICLE_VI: dict[str, str] = {
    "vehicle": "xe",
    "motor_vehicle": "xe cơ giới",
    "car": "xe ô tô",
    "passenger_car": "xe ô tô con",
    "taxi": "xe taxi",
    "bus": "xe ô tô chở khách",
    "coach": "xe khách",
    "city_bus": "xe buýt",
    "truck": "xe ô tô tải",
    "motorbike": "xe máy",
    "motorcycle": "xe mô tô",
    "moped": "xe gắn máy",
    "sidecar": "xe mô tô ba bánh có thùng",
    "motor_tricycle": "xe ba bánh có động cơ",
    "special_machine": "xe máy chuyên dùng",
    "tractor": "máy kéo",
    "rudimentary": "xe thô sơ",
    "bicycle": "xe đạp",
    "cargo_bicycle": "xe đạp thồ",
    "cyclo": "xích lô",
    "hand_cart": "xe người kéo, đẩy",
    "animal_cart": "xe súc vật kéo",
    "similar_rudimentary": "xe thô sơ tương tự (xe 4 bánh thô sơ)",
    "pedestrian": "người đi bộ",
    "every_vehicle": "các loại xe",
}
assert set(VEHICLE_VI) == {c.value for c in VehicleClass}, "VEHICLE_VI must name every class"


DIRECTION_VI: dict[str, str | None] = {
    "straight": "Đi thẳng", "left": "Rẽ trái", "right": "Rẽ phải", "slight_left": "Đi chếch sang trái",
    "slight_right": "Đi chếch sang phải", "u_turn": "Quay đầu", "none": None,
}


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " và " + items[-1]


def _hm(t: str) -> str:
    """'06:30' -> '6:30'."""
    h, _, m = str(t).partition(":")
    return f"{int(h)}:{m}" if h.isdigit() and m else str(t)


def _sign_phrase(s: dict[str, Any]) -> str:
    if not s.get("readable", True):
        return f"biển {s['id']} (chưa đọc được)"
    name = s.get("name_vi")
    return f"biển {s['code']}" + (f" ({name})" if name else "")


def main_signs(digest: dict[str, Any]) -> list[dict[str, Any]]:
    """The digest's signs: those with a reason that holds (truth true) first, unreadable
    ones last."""
    applying = {r.get("sign_id") for r in digest.get("reasons", []) if r.get("truth") == "true"}
    signs = digest.get("signs", [])
    rank = lambda s: (s["id"] not in applying, not s.get("readable", True))  # noqa: E731
    return sorted(signs, key=rank)


def _basis(digest: dict[str, Any], limit: int = 2) -> str:
    """The main reason and citation: the first signs the answer rests on and the
    first articles cited."""
    signs = []
    for s in main_signs(digest):
        if (p := _sign_phrase(s)) not in signs:
            signs.append(p)
    signs = signs[:limit]
    cites = digest.get("citations", [])[:limit]
    parts = []
    if signs:
        parts.append(_join(signs))
    if cites:
        parts.append("; ".join(cites))
    return (" Căn cứ: " + ", ".join(parts) + ".") if parts else ""


def _vehicles(classes: list[str]) -> str:
    return _join([VEHICLE_VI.get(c, c) for c in classes])


def _conditions(digest: dict[str, Any]) -> str:
    """The plate texts of the signs whose reason is still open (truth unknown): the
    condition a conditional answer depends on, e.g. a plate's time windows."""
    open_ids = [r.get("sign_id") for r in digest.get("reasons", []) if r.get("truth") == "unknown"]
    texts = []
    for s in digest.get("signs", []):
        if s["id"] in open_ids:
            for p in s.get("plates", []):
                t = " ".join(str(p).split())
                if t and t not in texts:
                    texts.append(f"biển phụ «{t}» của biển {s['code']}")
    return "; ".join(texts)


def _value_text(digest: dict[str, Any]) -> str:
    v = digest.get("value")
    if isinstance(v, list):                                    # meaning
        names = [f"{x.get('name_vi')} ({x.get('code')})" if x.get("known") else
                 f"biển {x.get('sign_id')} chưa đọc được" for x in v if isinstance(x, dict)]
        return (_join(names) + ".") if names else "Không có biển phù hợp."
    if not isinstance(v, dict):
        return "Kết quả theo quy tắc: " + str(v) + "."
    if "bans" in v:                                            # ban_times
        if not v.get("banned"):
            return "Không bị cấm vào khung giờ nào."
        if any(b.get("always") for b in v["bans"]):
            return "Bị cấm mọi lúc."
        wins = [f"từ {_hm(a)} đến {_hm(b)}" for x in v["bans"] for a, b in x.get("windows", [])]
        text = _join(wins)
        return (text[:1].upper() + text[1:] + ".") if text else "Bị cấm theo điều kiện trên biển."
    if "lanes" in v and "lane_count" in v:                     # lanes_for / lanes_where
        lanes = v.get("lanes") or []
        text = ("Làn " + _join([str(x) for x in lanes]) + ".") if lanes else "Không có làn nào."
        if v.get("conditional"):
            text += " Còn tùy điều kiện: làn " + _join([str(x) for x in v["conditional"]]) + "."
        return text
    if "group" in v:                                           # meaning, aspect group (art. 11)
        return f"Thuộc nhóm {v['group']}."
    for aspect in ("conduct", "scope", "placement"):           # meaning, other aspects
        if isinstance(v.get(aspect), list):
            rows = []
            for x in v[aspect]:
                body = "; ".join(x[aspect]) if isinstance(x[aspect], list) else str(x[aspect])
                rows.append(f"{x.get('name_vi')} ({x.get('code')}): {body}")
            text = ". ".join(rows)
            return (text[:1].upper() + text[1:] + ".") if text else "Không có biển phù hợp."
    if "destination" in v:                                     # guide: direction / distance
        d = DIRECTION_VI.get(v.get("direction") or "none")
        parts = [f"{d} để đến {v['destination']}" if d else f"Đến {v['destination']}"]
        if v.get("distance"):
            parts.append(f"còn {v['distance']}")
        return ", ".join(parts) + "."
    if "destinations" in v:                                    # guide: the board's lines
        rows = [x["text"] + (f" {x['distance']}" if x.get("distance") else "")
                + (f" ({DIRECTION_VI[x['direction']].lower()})" if DIRECTION_VI.get(x.get("direction") or "none") else "")
                for x in v["destinations"]]
        return "Biển chỉ dẫn ghi: " + "; ".join(rows) + "."
    if "routes" in v:                                          # guide: route plates
        return "Tuyến " + _join(v["routes"]) + "."
    if "parts" in v and isinstance(v["parts"], list) and v["parts"] and isinstance(v["parts"][0], dict):
        # multi (phase 4.6 I1): each part's own text, joined
        texts = []
        for part in v["parts"]:
            sub = {**digest, "verdict": part["verdict"], "value": part["value"]}
            if part["verdict"] in ("yes", "no"):
                texts.append("Có" if part["verdict"] == "yes" else "Không")
            else:
                texts.append(_value_text(sub).rstrip("."))
        return ". ".join(texts) + "."
    if "because" in v and "answer" in v:                      # explain (phase 4.6 I3)
        inner = {**digest, "verdict": v["answer"], "value": v.get("inner")}
        head = ({"yes": "Có", "no": "Không"}.get(v["answer"]) or _value_text(inner).rstrip("."))
        why = [f"{b['name_vi']} ({b['code']})" for b in v["because"] if b.get("code") and b.get("truth") == "true"]
        return head + (", vì có biển " + _join(why) if why else "") + "."
    if "article" in v and isinstance(v["article"], list):     # meaning, aspect article (phase 4.6)
        rows = [f"biển {x['code']} ở Điều {x['article']}" for x in v["article"]]
        text = _join(rows)
        return text[:1].upper() + text[1:] + "."
    if "road_type" in v:                                       # guide road type (phase 4.6 I2)
        return {"expressway": "Đường cao tốc.", "national_road": "Quốc lộ.",
                "urban": "Đường đô thị.", "rural": "Đường ngoài đô thị."}.get(v["road_type"], str(v["road_type"]) + ".")
    if v.get("kind") == "range":                               # speed range (phase 4.6 I4)
        text = f"Tốc độ tối đa {v['max']:g} km/h"
        text += f", tối thiểu {v['min']:g} km/h" if v.get("min") is not None else ", không có biển quy định tốc độ tối thiểu"
        return text + "."
    if "per_vehicle" in v:                                     # speed_limit over several vehicles
        word = "tối đa" if v.get("kind") == "max" else "tối thiểu"
        rows = []
        for x in v["per_vehicle"]:
            name = VEHICLE_VI.get(x["vehicle"], x["vehicle"])
            if x.get("limit") is not None:
                rows.append(f"{name} {x['limit']} km/h")
            elif x.get("conditional"):
                rows.append(f"{name} {_join([str(c['value']) for c in x['conditional']])} km/h tùy điều kiện")
            else:
                rows.append(f"{name} chưa xác định")
        text = f"Tốc độ {word}: " + "; ".join(rows) + "."
        return text
    if "limit" in v and "kind" in v:                           # speed_limit
        word = "tối đa" if v.get("kind") == "max" else "tối thiểu"
        if v.get("per_lane"):
            rows = [f"làn {x['lane']}: {x['limit']} km/h" for x in v["per_lane"] if x.get("limit") is not None]
            if rows:
                return f"Tốc độ {word} " + "; ".join(rows) + "."
        if v.get("limit") is not None:
            return f"Tốc độ {word} {v['limit']} km/h."
        if v.get("conditional"):
            vals = _join([f"{c['value']:g}" if isinstance(c.get("value"), (int, float)) else str(c.get("value"))
                          for c in v["conditional"]])
            return f"Tốc độ {word} {vals} km/h, còn tùy điều kiện."
        return f"Tốc độ {word} còn tùy điều kiện trên biển."
    if "holding" in v and "options" in v:                      # choose
        hold = v.get("holding") or []
        text = (_join(hold) + ".") if hold else "Không có phương án nào."
        if v.get("unknown"):
            text += " Chưa xác định được: " + _join(v["unknown"]) + "."
        return text[:1].upper() + text[1:]
    if v.get("conditional") and "banned" in v:                # which_vehicles, a conditional ban (T3)
        cond = _conditions(digest)
        text = (_vehicles(v["conditional"]) + " bị cấm khi đúng điều kiện trên biển"
                + (f": {cond}" if cond else "") + ".")
        if hits := v.get("banned") or []:          # outright bans first, then the conditional ones
            text = _vehicles(hits) + " bị cấm. " + text[:1].upper() + text[1:]
        return text[:1].upper() + text[1:]
    for status in ("banned", "allowed"):                       # which_vehicles / lane_vehicles
        if status in v:
            hits = v.get(status) or []
            text = (_vehicles(hits) + ".") if hits else "Không có loại xe nào."
            if v.get("conditional"):
                text += " Còn tùy điều kiện: " + _vehicles(v["conditional"]) + "."
            return text[:1].upper() + text[1:]
    return "Kết quả theo quy tắc."


def template_answer(digest: dict[str, Any], question: str) -> str:
    """The deterministic answer for a digest."""
    verdict = digest["verdict"]
    if verdict in ("yes", "no"):
        if is_true_false(question):
            head = "Đúng." if verdict == "yes" else "Sai."
        else:
            head = "Có." if verdict == "yes" else "Không."
        return head + _basis(digest)
    if verdict == "uncertain":
        ids = digest.get("uncertain_signs") or [s["id"] for s in digest.get("signs", [])]
        return ("Chưa chắc chắn: biển " + _join(ids)
                + " có thể đọc theo nhiều cách, và các cách đọc cho kết quả khác nhau.")
    if verdict == "unknown":
        unread = [s for s in digest.get("signs", []) if not s.get("readable", True)]
        if unread or digest.get("uncertain_signs"):
            return "Chưa xác định được, vì có biển chưa đọc được." + _basis(digest)
        return "Chưa xác định được: câu trả lời còn tùy điều kiện không thấy trong ảnh." + _basis(digest)
    return _value_text(digest) + _basis(digest)


def template_reply(digest: dict[str, Any], question: str) -> dict[str, Any]:
    """The template as a writer-shaped reply (so the guard can check it)."""
    return {"verdict": digest["verdict"], "answer": template_answer(digest, question),
            "cited_signs": [s["id"] for s in main_signs(digest)[:2]],
            "cited_rules": [r["rule"] for r in digest.get("rules", [])[:2]]}
