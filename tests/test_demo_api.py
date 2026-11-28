"""Demo photos (app/api/demo.py): added on the admin site, shown on the public app while switched on."""

from __future__ import annotations

import hashlib

from tests.test_admin_api import ADMIN, make  # noqa: F401  (the fixture)
from tests.test_api import jpeg


def add(c, image=None, caption="Ngã tư có biển cấm", questions="Xe tải có được đi thẳng không?\n\nBiển này là gì?"):
    return c.post("/v1/admin/demo", headers=ADMIN, files={"image": ("d.jpg", image or jpeg(), "image/jpeg")},
                  data={"caption": caption, "questions": questions})


def test_gallery_is_off_until_switched_on(make):
    c, _, _ = make()
    img = jpeg(800, 600)
    r = add(c, img)
    assert r.status_code == 200
    sha = hashlib.sha256(img).hexdigest()
    assert r.json() == {"enabled": False, "items": [{"sha256": sha, "caption": "Ngã tư có biển cấm",
                                                     "questions": ["Xe tải có được đi thẳng không?", "Biển này là gì?"]}]}
    assert c.get("/v1/demo").json() == {"enabled": False, "items": []}

    assert c.put("/v1/admin/demo", headers=ADMIN, json={"enabled": True}).json()["enabled"] is True
    pub = c.get("/v1/demo").json()
    assert pub["enabled"] and [d["sha256"] for d in pub["items"]] == [sha]
    assert c.get(f"/v1/images/{sha}").content == img          # the app asks about the photo itself
    t = c.get(f"/v1/demo/{sha}/thumb")
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg" and len(t.content) < len(img) * 2

    c.put("/v1/admin/demo", headers=ADMIN, json={"enabled": False})
    assert c.get("/v1/demo").json()["items"] == []


def test_the_switch_survives_a_settings_reset(make):
    c, _, _ = make()
    c.put("/v1/admin/demo", headers=ADMIN, json={"enabled": True})
    c.post("/v1/admin/settings/reset", headers=ADMIN)
    assert c.get("/v1/demo").json()["enabled"] is True


def test_admin_endpoints_need_the_admin_login(make):
    c, _, _ = make()
    assert c.get("/v1/admin/demo").status_code == 401
    assert c.put("/v1/admin/demo", json={"enabled": True}).status_code == 401
    assert c.post("/v1/admin/demo", files={"image": ("d.jpg", jpeg(), "image/jpeg")}).status_code == 401
    assert c.get("/v1/demo").status_code == 200                 # the public list needs no admin login


def test_edit_order_and_delete(make):
    c, _, _ = make()
    a, b = jpeg(colour=(10, 20, 30)), jpeg(colour=(200, 20, 30))
    sa, sb = hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest()
    add(c, a, caption="A")
    add(c, b, caption="B", questions="")
    assert add(c, a).status_code == 409                          # the same photo twice

    r = c.patch(f"/v1/admin/demo/{sb}", headers=ADMIN, json={"caption": " B2 ", "questions": [" Câu 1 ", ""]})
    assert r.json()["items"][1] == {"sha256": sb, "caption": "B2", "questions": ["Câu 1"]}
    assert c.patch(f"/v1/admin/demo/{sb}", headers=ADMIN, json={}).status_code == 400
    assert c.patch(f"/v1/admin/demo/{'0' * 64}", headers=ADMIN, json={"caption": "x"}).status_code == 404

    r = c.post("/v1/admin/demo/order", headers=ADMIN, json={"order": [sb, sa]})
    assert [d["sha256"] for d in r.json()["items"]] == [sb, sa]

    assert [d["sha256"] for d in c.delete(f"/v1/admin/demo/{sb}", headers=ADMIN).json()["items"]] == [sa]
    assert c.get(f"/v1/demo/{sb}/thumb").status_code == 404
    assert c.get(f"/v1/images/{sb}").status_code == 200          # earlier questions still show the photo
    assert c.delete(f"/v1/admin/demo/{sb}", headers=ADMIN).status_code == 404


def test_bad_uploads_and_limits(make):
    c, _, _ = make()
    r = c.post("/v1/admin/demo", headers=ADMIN, files={"image": ("d.txt", b"not an image", "text/plain")})
    assert r.status_code == 415
    assert add(c, caption="x" * 121).status_code == 400
    assert add(c, questions="\n".join(f"q{i}" for i in range(6))).status_code == 400
    assert c.get("/v1/demo/not-a-sha/thumb").status_code == 400
    assert c.get("/v1/admin/demo", headers=ADMIN).json()["items"] == []
