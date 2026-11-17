"""Check interpretation premises and posted-limit precedence against the local law corpus.

Circular 38 itself is outside this corpus. These checks detect competing text or a
change to a reviewed passage; they cannot certify Circular 38's numbers.
"""
import hashlib
import html
import json
import re

import janus_swi as janus
import pytest

from conftest import DATASET_DIR, V
from vqa.schemas import Position, Road, RulePermitted, SceneGraph, Sign

Q = "QCVN 41:2024/BGTVT"
L = "36/2024/QH15"
LAW = DATASET_DIR / "dataset/law_db/vlsp2025_law.json"
pytestmark = pytest.mark.skipif(not LAW.exists(), reason="local law corpus unavailable")

PREMISES = {
    "r_load_implies_gross": [(Q, "B.15", "trọng tải bản thân xe cộng với khối lượng người, hành lý và hàng hóa")],
    "r_kb1_pass_side": [(Q, "D.2", "đi vòng chướng ngại vật theo hướng mũi tên")],
    "r_kb2_roundabout": [(Q, "D.3", "chạy vòng theo đảo an toàn theo hướng mũi tên"),
                          (L, "22", "phải nhường đường cho xe đi đến từ bên trái")],
    "r_kb4_expressway_zone": [(Q, "47", s) for s in
                              ("IE.452 chỉ dẫn bắt đầu", "IE.451b chỉ dẫn lối vào",
                               "IE.453b chỉ dẫn điểm kết thúc", "IE.453c “Hết đường cao tốc”")],
    "r_c38_expressway": [(Q, "47", "giá trị hạn chế tốc độ tối đa và tốc độ tối thiểu"), (L, "25", "đường cao tốc")],
    "r_c38_residential": [(Q, "D.17", "bắt đầu bằng biển số R.420"), (L, "12", "quy định chi tiết về tốc độ")],
    "r_c38_moped": [(L, "34", "vận tốc thiết kế không lớn hơn 50 km/h"), (L, "12", "quy định chi tiết về tốc độ")],
    "r_c38_outside": [(Q, "D.18", "đã hết hiệu lực"), (Q, "B.27", "vượt quá trị số ghi trên biển"),
                      (L, "12", "quy định chi tiết về tốc độ")],
}


@pytest.fixture(scope="module")
def articles():
    return {(law["id"], row["id"]): row["text"] for law in json.loads(LAW.read_text())
            for row in law["articles"]}


def test_all_rule_sources_accounted_for(engine, articles):
    interpreted = set()
    for row in janus.query("rule_source(R,L,A)"):
        if row["L"] == "interpretation":
            interpreted.add(row["R"])
        else:
            assert (row["L"], row["A"]) in articles, row
    assert interpreted == set(PREMISES)


@pytest.mark.parametrize("rule", PREMISES)
def test_interpretation_premises(rule, articles):
    for law, article, phrase in PREMISES[rule]:
        assert phrase in " ".join(articles[law, article].split()), (rule, article)


def test_interpretation_effects_follow_deciding_phrases(engine, articles):
    catalog = engine.catalog
    assert janus.query_once("derived_gross([a(load_t,5)], iv(5,true,_,_))")["truth"]
    assert catalog.get("R.302a").effect.pass_side == "as_shown"
    assert catalog.get("R.303").effect.yield_from == "left"
    for code, end in [("IE.452", "start"), ("IE.451b", "start"), ("IE.453b", "end"), ("IE.453c", "end")]:
        zone = catalog.get(code).effect.zone
        assert (zone.kind, zone.at) == ("expressway", end)
    # KB-3 lives in informational catalog effects, without a rule_source.
    assert "chỉ dẫn hướng đi" in articles[Q, "35"]
    for row in catalog.signs:
        if row.effect.informational:
            assert not row.effect.prohibits and not row.effect.only_directions, row.code


# Reviewed numeric speed passages: sign/marking dimensions and placement, thresholds
# for warnings, transitions between posted limits, or design-speed vehicle definitions.
# B.27a is a real numeric ceiling on a *posted night sign*. None sets a competing
# unposted default for the four Circular 38 cases. A new or changed passage needs review.
SPEED_REVIEW = {('36/2024/QH15', '34'): '44be2998ed19a28f3d2c5626656c5f768d83e5778d0bf08777ce84cb6f8c6be3',
 ('QCVN 41:2024/BGTVT', '14'): 'e177ddb9cfd05ec2d62b9c46099f60c29241cb266329c2d8bbb18aaa89bcea02',
 ('QCVN 41:2024/BGTVT', '30'): '1c599c6d33837a215252840eed34ca0176a0ed742ad94750be2c48e76f1169ea',
 ('QCVN 41:2024/BGTVT', '45'): '01377765b607913a29d19e6a1973ebaef1dc05785eb845355c3cad87b0f3bdbc',
 ('QCVN 41:2024/BGTVT', '48'): 'a8f84909e2fef4ee78de190053e263b07b9e82c63743ef65abacf0ecce961914',
 ('QCVN 41:2024/BGTVT', '56'): '5e51865d70bcd52e9a8cbc44ce3fc67fce9f53bcbe50e7f2014aa571d19b5459',
 ('QCVN 41:2024/BGTVT', '62'): '29e113a33c134d3cb46337fa21fd1573bfc889e39c6d8cb29101063afcdd5d38',
 ('QCVN 41:2024/BGTVT', 'A.2'): '4fb1cf3b5f8c2778ae472dc7f7f5a0b4ecfeba5365f147a6fc039219cdcd88bf',
 ('QCVN 41:2024/BGTVT', 'B.27'): '31a69482627a9934a6a8470633e6f86862fdb63000633a27e14c7376a5d71aca',
 ('QCVN 41:2024/BGTVT', 'B.27a'): '160d1ad4755ef8f96477f545c9154196e2392ec10ca6dc1b94826f0ac586778d',
 ('QCVN 41:2024/BGTVT', 'C.21'): '4e0a53ec4ae3571fc9170a132095b0cc1512887c22bbf4bf0c050cdabb5d5d7b',
 ('QCVN 41:2024/BGTVT', 'C.24'): '8c3819c7f6d91c2ecd686e6c5d937be20ac7acf82591a600a383b4237e59f9bb',
 ('QCVN 41:2024/BGTVT', 'G.1'): 'a4f7630d5333f37f7f59c6eec3bfc94b248033955bcdf12c32c9e0277d2cec34',
 ('QCVN 41:2024/BGTVT', 'G.4'): '674f1700faf7982b4b5ac488a8db71370a3498d9985533408a0580c9774a84ac'}


def numeric_passages(articles):
    found = {}
    for key, raw in articles.items():
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())
        if re.search(r"\d\s*(?:km\s*/\s*(?:h|giờ)|ki-lô-mét trên giờ)", text, re.I):
            found[key] = hashlib.sha256(text.encode()).hexdigest()
    return found


def test_numeric_speed_articles_still_match_the_review(articles):
    assert numeric_passages(articles) == SPEED_REVIEW


@pytest.mark.parametrize("zone,cls,posted,speed,area", [
    ("IE.452", "passenger_car", 100, 110, None),  # below the default max, above the sign
    ("R.420", "passenger_car", 70, 65, None),   # above the default max, below the sign
    ("R.420", "moped", 35, 38, None),
    (None, "passenger_car", 70, 75, "outside_residential"),
])
def test_posted_sign_precedes_each_speed_interpretation(engine, articles, zone, cls, posted, speed, area):
    assert "vượt quá trị số ghi trên biển" in articles[Q, "B.27"]
    codes = ["P.127"] + ([zone] if zone else [])
    signs = [Sign(id=f"s{i}", code=code, confidence="high", value=posted if i == 0 else None,
                  position=Position(rank_top_down=i + 1, side="right")) for i, code in enumerate(codes)]
    scene = SceneGraph(scene_id="posted", road=Road(divided=False), signs=signs)
    answer = engine.answer(scene, RulePermitted(vehicle=V(cls), speed_kmh=speed, area=area, road_divided=False))
    assert answer.verdict.value == ("no" if speed > posted else "yes")
    assert any(c.article_id == "B.27" for c in answer.citations)
