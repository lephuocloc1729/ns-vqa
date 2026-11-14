"""Evidence for public_dev_audit_v2: every public-dev question that moved to A in
phase 1.6 is written as a hand-made scene + program and run through the engine,
and the engine's answer is compared with what the gold answer needs.

Hand-made scenes are audit material only (public_dev may be inspected); the
leakage guard keeps them out of inference code.

    .venv/bin/python eval/audits/public_dev_v2_checks.py
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from vqa.reasoning.engine import Engine  # noqa: E402
from vqa.schemas import (  # noqa: E402
    AllOf, BanTimes, Forbidden, IsSign, LanesFor, LaneVehicles, Meaning, Permitted, SceneGraph,
    Selector, SpeedLimit, Verify, When, WhichVehicles,
)


def V(cls, **kw):
    return {"class": cls, **kw}


def sc(*signs, lanes=None):
    return SceneGraph(scene_id="audit", signs=list(signs), road={"lanes": lanes})


def s(sid, code, **kw):
    return {"id": sid, "code": code, **kw}


def win(*pairs):
    return [{"start": a, "end": b} for a, b in pairs]


T = lambda h, m=0: When(time=dt.time(h, m))
only = Selector(only=True)

CHECKS = [
    # (question id, gold, scene, program, check(answer) -> bool)
    ("public_natural_0053", "Đúng", sc(s("s1", "P.125")),
     IsSign(sign=only, meaning="no_overtaking"), lambda a: a.verdict.value == "yes"),
    ("public_natural_0097", "Đúng", sc(s("s1", "P.102")),
     IsSign(sign=only, meaning="no_entry_one_way"), lambda a: a.verdict.value == "yes"),
    ("public_natural_0018", "Sai", sc(s("s1", "W.221b")),
     IsSign(sign=only, code="W.221a"), lambda a: a.verdict.value == "no"),
    ("public_natural_0044", "Đúng", sc(s("s1", "IE.465"), s("s2", "IE.464")),
     IsSign(sign=Selector(code="IE.465"), meaning="chi_dan_dia_diem_va_khoang_cach"),
     lambda a: a.verdict.value == "yes"),
    ("public_natural_0080", "Đúng", sc(s("s1", "I.419a")),
     IsSign(sign=only, code="I.419"), lambda a: a.verdict.value == "yes"),
    ("public_natural_0022", "Biển báo chỉ dẫn", sc(s("s1", "I.423a")),
     Meaning(sign=only), lambda a: a.value[0]["category"] == "information"),
    ("public_natural_0025", "Đường hầm",
     sc(s("s1", "P.110a", shape="circle"), s("s2", "P.112", shape="circle"),
        s("s3", "P.127", value=50, shape="circle"), s("s4", "P.128", shape="circle"),
        s("s5", "P.117", value=4.3, shape="circle"), s("s6", "W.240", shape="triangle")),
     Meaning(sign=Selector(shape="triangle")), lambda a: [v["name_vi"] for v in a.value] == ["Đường hầm"]),
    ("public_natural_0072", "Chỗ ngoặt nguy hiểm bên phải; đi chậm",
     sc(s("s1", "W.245a", shape="triangle"), s("s2", "W.201b", shape="triangle")),
     Meaning(sign=Selector(shape="triangle")),
     lambda a: {v["name_vi"] for v in a.value} == {"Đi chậm", "Chỗ ngoặt nguy hiểm vòng bên phải"}),
    ("public_natural_0086", "Biển báo chỉ dẫn",
     sc(s("s1", "I.414a"), s("s2", "I.414c"), s("s3", "I.414b")),
     Meaning(sign=Selector()), lambda a: {v["category"] for v in a.value} == {"information"}),
    ("public_natural_0051", "23:00 - 04:00",
     sc(s("s1", "P.111a", plates=[{"kind": "local", "text": "CẤM XE GẮN MÁY ĐI THẲNG 23:00-04:00",
                                   "actions": ["go_straight"], "time_windows": win(("23:00", "04:00"))}])),
     BanTimes(action="go_straight", vehicle=V("moped")),
     lambda a: a.value["bans"][0]["windows"] == [["23:00", "04:00"]] and a.basis == ["non_standard_plate"]),
    ("public_natural_0092", "Xe 3 bánh và 4 bánh thô sơ",
     sc(s("s1", "P.127", value=50), s("s2", "P.130"),
        s("s3", "P.111d", plates=[{"kind": "local", "text": "CẤM XE 3 BÁNH VÀ 4 BÁNH THÔ SƠ",
                                   "vehicles": [{"class": "cyclo"}, {"class": "similar_rudimentary"}],
                                   "time_windows": win(("05:00", "13:00"), ("16:00", "22:00"))}])),
     WhichVehicles(),  # no time in the question: banned during the plate's windows
     lambda a: set(a.value["conditional"]) == {"cyclo", "similar_rudimentary"}),
    ("public_natural_0058", "Người đi bộ", sc(s("s1", "P.112")),
     WhichVehicles(), lambda a: a.value["banned"] == ["pedestrian"]),
    ("public_natural_0005", "Đúng",
     sc(s("s1", "R.415a", lanes=[{"lane": i, "vehicles": [{"class": "car"}]} for i in (1, 2, 3)]
                            + [{"lane": 4, "vehicles": [{"class": "motorbike"}, {"class": "bicycle"}]}]),
        lanes=4),
     AllOf(claims=[Permitted(action="enter", vehicle=V("car"), lane=1),
                   Forbidden(action="enter", vehicle=V("motorbike"), lane=1)]),
     lambda a: a.verdict.value == "yes"),
    ("public_natural_0049", "2 làn đường",
     sc(s("s1", "R.415a", lanes=[{"lane": 1, "vehicles": [{"class": "car"}]},
                                 {"lane": 2, "vehicles": [{"class": "car"}]},
                                 {"lane": 3, "vehicles": [{"class": "motorbike"}]},
                                 {"lane": 4, "vehicles": [{"class": "bicycle"}]}]), lanes=4),
     LanesFor(vehicle=V("passenger_car")), lambda a: len(a.value["lanes"]) == 2),
    ("public_natural_0015", "40km/h",
     sc(s("s1", "P.127c", lanes=[{"lane": 1, "max_speed": 40, "vehicles": [{"class": "car"}]},
                                 {"lane": 2, "max_speed": 40, "vehicles": [{"class": "car"}, {"class": "bus"}]},
                                 {"lane": 3, "max_speed": 40, "vehicles": [{"class": "motorbike"}]}])),
     SpeedLimit(vehicle=V("motor_vehicle")),
     lambda a: {x["limit"] for x in a.value["per_lane"]} == {40}
     or {c["value"] for x in a.value["per_lane"] for c in x["conditional"]} == {40}),
    ("public_natural_0065", "Có",
     sc(s("s1", "P.127c", lanes=[{"lane": i, "max_speed": 60, "vehicles": [{"class": "car"}]} for i in (1, 2)]),
        s("s2", "P.103a", plates=[{"kind": "time", "time_windows": win(("06:00", "22:00"))},
                                  {"kind": "lane", "lanes": [3, 4]}]), lanes=4),
     Forbidden(action="enter", vehicle=V("car"), lane=3, when=T(10)),
     lambda a: a.verdict.value == "yes"),
    ("public_natural_0042", "Đúng",
     sc(s("s1", "P.130", plates=[{"kind": "time", "time_windows": win(("06:00", "09:00"), ("16:00", "19:00"))}])),
     Verify(claim=AllOf(claims=[Permitted(action="stop", vehicle=V("every_vehicle"), when=T(12)),
                                Permitted(action="park", vehicle=V("every_vehicle"), when=T(12))])),
     lambda a: a.verdict.value == "yes"),
    # A in v1 through meaning(); now a proper speed_limit query
    ("public_natural_0009", "60km/h", sc(s("s1", "P.127", value=60)),
     SpeedLimit(), lambda a: a.value["limit"] == 60),
    ("public_natural_0028", "40km/h", sc(s("s1", "P.127", value=40), s("s2", "W.203c")),
     SpeedLimit(), lambda a: a.value["limit"] == 40),
    ("public_natural_0093", "50km/h", sc(s("s1", "P.127", value=50), s("s2", "P.130")),
     SpeedLimit(), lambda a: a.value["limit"] == 50),
]


def main() -> int:
    eng = Engine()
    fails = 0
    for qid, gold, scene, program, ok in CHECKS:
        a = eng.answer(scene, program)
        good = bool(ok(a))
        fails += not good
        print(f"{'ok  ' if good else 'FAIL'} {qid}  gold={gold!r}  verdict={a.verdict.value}  "
              f"value={str(a.value)[:90]}  cites={sorted({c.article_id for c in a.citations})}")
    print(f"{len(CHECKS) - fails}/{len(CHECKS)} checks pass")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
