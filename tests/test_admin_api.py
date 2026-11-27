"""The admin site's API (app/api/admin.py), live settings (app/api/live.py) and site accounts (app/api/accounts.py)."""

from __future__ import annotations

import base64
import dataclasses
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import accounts as acc
from app.api import live as live_mod
from app.api.main import create_app
from app.api.settings import Settings
from tests.test_api import FakePipeline, ask, jpeg

ADMIN = {"Authorization": "Basic " + base64.b64encode(b"admin:s3cret-admin").decode()}


@pytest.fixture
def make(tmp_path):
    def _make(pipe=None, **kw):
        base = dict(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "up", heartbeat_s=0.2,
                    admin_password="s3cret-admin", site_users_file=tmp_path / "auth" / "users.htpasswd",
                    site_shared_user="signcite", site_shared_password="shared-pw",
                    rag_cache_dir=tmp_path / "ragcache")
        base.update(kw)
        s = Settings(**base)
        pipe = pipe or FakePipeline()
        return TestClient(create_app(s, pipeline_factory=lambda: pipe)), pipe, s
    return _make


def users_file(s: Settings) -> dict[str, str]:
    lines = s.site_users_file.read_text().splitlines()
    return dict(ln.split(":", 1) for ln in lines)


# ---------------------------------------------------------------------- apr1
@pytest.mark.parametrize("pw", ["secret", "Xy7pQ2mn", "mật khẩu", "a" * 40])
def test_apr1_matches_openssl(pw):
    try:
        expected = subprocess.run(["openssl", "passwd", "-apr1", "-salt", "abcd1234", pw],
                                  capture_output=True, text=True, check=True).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("openssl with -apr1 not available")
    assert acc.apr1(pw, "abcd1234") == expected
    assert acc.check_apr1(pw, expected) and not acc.check_apr1(pw + "x", expected)


def test_generated_passwords_and_names():
    pw = acc.new_password()
    assert len(pw) == 12 and not set(pw) & set("0oO1lIi")
    assert acc.valid_name("p07") and acc.valid_name("ha.nguyen")
    assert not acc.valid_name("P07") and not acc.valid_name("a") and not acc.valid_name("x:y")
    with pytest.raises(ValueError):
        acc.htpasswd_text([("bad:name", acc.apr1("x"))])


# ---------------------------------------------------------------------- the admin login
def test_admin_needs_its_own_login(make):
    c, _, _ = make()
    assert c.get("/v1/admin/me").status_code == 401
    assert c.get("/v1/admin/me").headers["www-authenticate"].startswith("Basic")
    tester = {"Authorization": "Basic " + base64.b64encode(b"signcite:shared-pw").decode()}
    assert c.get("/v1/admin/me", headers=tester).status_code == 401
    assert c.get("/v1/admin/me", headers=ADMIN).json() == {"admin": "admin"}


def test_admin_is_off_without_a_password(make):
    c, _, _ = make(admin_password="")
    assert c.get("/v1/admin/me", headers=ADMIN).status_code == 404


# ---------------------------------------------------------------------- site accounts
def test_accounts_write_the_web_servers_password_file(make):
    c, _, s = make()
    assert set(users_file(s)) == {"signcite"}                      # written at start-up
    assert acc.check_apr1("shared-pw", users_file(s)["signcite"])

    r = c.post("/v1/admin/accounts", json={"name": "P07", "note": "UAT"}, headers=ADMIN)
    assert r.status_code == 200
    pw = r.json()["password"]
    assert r.json()["name"] == "p07"
    assert acc.check_apr1(pw, users_file(s)["p07"])
    assert pw not in s.site_users_file.read_text()                 # only the hash

    assert c.post("/v1/admin/accounts", json={"name": "p07"}, headers=ADMIN).status_code == 409
    assert c.post("/v1/admin/accounts", json={"name": "signcite"}, headers=ADMIN).status_code == 409
    assert c.post("/v1/admin/accounts", json={"name": "admin"}, headers=ADMIN).status_code == 409
    assert c.post("/v1/admin/accounts", json={"name": "x y"}, headers=ADMIN).status_code == 400

    new = c.post("/v1/admin/accounts/p07/reset", headers=ADMIN).json()["password"]
    assert new != pw and acc.check_apr1(new, users_file(s)["p07"])

    assert c.patch("/v1/admin/accounts/p07", json={"enabled": False}, headers=ADMIN).json()["enabled"] is False
    assert "p07" not in users_file(s)
    c.patch("/v1/admin/accounts/p07", json={"enabled": True}, headers=ADMIN)
    assert "p07" in users_file(s)
    assert c.post("/v1/admin/accounts/nobody/reset", headers=ADMIN).status_code == 404


def test_questions_are_stored_with_the_account_that_asked(make):
    c, _, _ = make()
    c.post("/v1/admin/accounts", json={"name": "p03"}, headers=ADMIN)
    for who in ("p03", "p03", None):
        c.post("/v1/ask", files={"image": ("p.jpg", jpeg(), "image/jpeg")}, data={"question": "Có được đi không?"},
               headers={"X-Remote-User": who} if who else {})
    items = c.get("/v1/admin/turns", headers=ADMIN).json()["items"]
    assert sorted(x["account"] or "-" for x in items) == ["-", "p03", "p03"]
    acct = c.get("/v1/admin/accounts", headers=ADMIN).json()["items"][0]
    assert acct["name"] == "p03" and acct["questions"] == 2 and acct["last_question_at"]


def test_deleting_an_account_removes_the_login_and_keeps_its_questions(make):
    c, _, s = make()
    c.post("/v1/admin/accounts", json={"name": "p05"}, headers=ADMIN)
    c.post("/v1/ask", files={"image": ("p.jpg", jpeg(), "image/jpeg")}, data={"question": "Có được đi không?"},
           headers={"X-Remote-User": "p05"})
    assert "p05" in users_file(s)

    assert c.delete("/v1/admin/accounts/p05").status_code == 401        # admin only
    r = c.delete("/v1/admin/accounts/p05", headers=ADMIN)
    assert r.status_code == 200 and r.json() == {"name": "p05", "deleted": True}
    assert "p05" not in users_file(s) and "signcite" in users_file(s)
    assert c.get("/v1/admin/accounts", headers=ADMIN).json()["items"] == []
    assert [x["account"] for x in c.get("/v1/admin/turns", headers=ADMIN).json()["items"]] == ["p05"]

    assert c.delete("/v1/admin/accounts/p05", headers=ADMIN).status_code == 404
    assert c.delete("/v1/admin/accounts/signcite", headers=ADMIN).status_code == 404   # the .env login is not here


def test_the_site_login_can_be_turned_off_for_everyone(make):
    c, _, s = make()
    flag = s.site_users_file.parent / "site_open"
    assert c.get("/v1/admin/accounts", headers=ADMIN).json()["login_required"] is True and not flag.exists()
    assert c.put("/v1/admin/site-login", json={"required": False}).status_code == 401     # admin only

    assert c.put("/v1/admin/site-login", json={"required": False}, headers=ADMIN).json() == {"login_required": False}
    assert flag.exists()
    assert c.get("/v1/admin/accounts", headers=ADMIN).json()["login_required"] is False
    c.post("/v1/admin/settings/reset", headers=ADMIN)                                     # not a live setting
    assert flag.exists()
    c2, _, _ = make()                                                                      # survives a restart
    assert flag.exists() and c2.get("/v1/admin/accounts", headers=ADMIN).json()["login_required"] is False

    assert c.put("/v1/admin/site-login", json={"required": True}, headers=ADMIN).json() == {"login_required": True}
    assert not flag.exists()


def test_accounts_are_refused_when_the_server_has_no_password_file(make):
    c, _, _ = make(site_users_file=None)
    assert c.post("/v1/admin/accounts", json={"name": "p01"}, headers=ADMIN).status_code == 409


# ---------------------------------------------------------------------- stored answers
def test_overview_turns_and_feedback_inbox(make):
    c, _, _ = make()
    t1 = ask(c).json()["turn_id"]
    t2 = ask(c, image=jpeg(colour=(10, 200, 10))).json()["turn_id"]
    ask(c)
    c.post(f"/v1/turns/{t1}/feedback", json={"thumb": "down", "corrected_answer": "Không được."})
    c.post(f"/v1/turns/{t2}/feedback", json={"thumb": "up"})

    o = c.get("/v1/admin/overview", headers=ADMIN).json()
    assert o["questions"] == 3 and o["photos"] == 2
    assert o["routes"] == {"rules": 3}
    assert o["feedback"] == {"rated": 2, "up": 1, "down": 1, "up_share": 0.5, "corrected": 1}
    assert o["seconds"]["first_on_photo_n"] == 2 and o["seconds"]["seen_before_n"] == 1
    assert sum(o["seconds"]["histogram"]) == 3
    assert o["per_day"][0]["questions"] == 3 and o["cost_usd"]["total"] == pytest.approx(0.006)

    inbox = c.get("/v1/admin/feedback", headers=ADMIN).json()
    assert inbox["total"] == 1 and inbox["items"][0]["corrected_answer"] == "Không được."
    assert c.get("/v1/admin/turns?rating=up", headers=ADMIN).json()["total"] == 1
    assert c.get("/v1/admin/turns?rating=none", headers=ADMIN).json()["total"] == 1
    assert c.get("/v1/admin/turns?route=rag", headers=ADMIN).json()["total"] == 0
    assert c.get("/v1/admin/turns?limit=2", headers=ADMIN).json()["total"] == 3
    assert len(c.get("/v1/admin/turns?limit=2", headers=ADMIN).json()["items"]) == 2
    assert c.get("/v1/admin/overview?since=2000-01-01&until=2000-01-02", headers=ADMIN).json()["questions"] == 0


# ---------------------------------------------------------------------- live settings
class ConfigPipeline(FakePipeline):
    """A fake with the switch and the spend guard the live settings change."""

    @dataclasses.dataclass(frozen=True)
    class Config:
        answer_fallback: bool = False

    def __init__(self):
        super().__init__()
        self.config = self.Config()
        self.guard = SimpleNamespace(limit=2.0, spent=0.25)
        self.seen: list[tuple[bool, float]] = []

    def answer(self, image_path, question):
        self.seen.append((self.config.answer_fallback, self.guard.limit))
        return super().answer(image_path, question)


def test_live_settings_apply_from_the_next_question(make, monkeypatch):
    import app.api.admin as admin_mod
    up = {"ok": False}
    monkeypatch.setattr(admin_mod.httpx, "get", lambda url, timeout: SimpleNamespace(
        status_code=200 if up["ok"] else 503, text='{"status":"ok"}' if up["ok"] else "down"))
    pipe = ConfigPipeline()
    c, _, _ = make(pipe)
    ask(c)
    assert pipe.seen[-1] == (False, pytest.approx(2.0, abs=10))   # the .env default spend limit

    r = c.put("/v1/admin/settings", json={"answer_fallback": "rag", "rag_url": "http://gpu:8100"}, headers=ADMIN)
    assert r.status_code == 409 and "RAG không trả lời" in r.json()["detail"]
    up["ok"] = True
    r = c.put("/v1/admin/settings", json={"answer_fallback": "rag", "rag_url": "http://gpu:8100/",
                                          "spend_limit": 7.5}, headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["live"]["answer_fallback"] == "rag" and body["live"]["rag_url"] == "http://gpu:8100"
    assert sorted(body["overridden"]) == ["answer_fallback", "rag_url", "spend_limit"]
    assert body["rag"]["reachable"] is True and body["fixed"]["answer_slots"] == 1
    assert c.get("/version").json()["answer_fallback"] == "rag"

    ask(c)
    assert pipe.seen[-1] == (True, 7.5)
    assert body["spend"]["spent"] == 0.25 and body["spend"]["limit"] == 2.0     # read before the next answer
    assert c.get("/v1/admin/settings", headers=ADMIN).json()["spend"]["limit"] == 7.5

    assert c.put("/v1/admin/settings", json={"spend_limit": -1}, headers=ADMIN).status_code == 400
    assert c.put("/v1/admin/settings", json={"answer_fallback": "maybe"}, headers=ADMIN).status_code == 400
    assert c.put("/v1/admin/settings", json={}, headers=ADMIN).status_code == 400

    r = c.post("/v1/admin/settings/reset", headers=ADMIN).json()
    assert r["overridden"] == [] and r["live"]["answer_fallback"] == "off"
    ask(c)
    assert pipe.seen[-1][0] is False


def test_the_api_pipeline_gets_a_rag_fallback_when_switched_live(tmp_path, monkeypatch):
    """With the API's own pipeline, switching to rag swaps in the (cached) RAG fallback, and back."""
    import vqa.pipeline as vp

    built = {}

    class StubPipeline(ConfigPipeline):
        def __init__(self, config):
            super().__init__()
            self.config = config
            self.fallback = SimpleNamespace(answer=lambda *a, **k: None, name="claude")
            built["pipe"] = self

    monkeypatch.setattr(vp, "Pipeline", StubPipeline)
    import app.api.admin as admin_mod
    monkeypatch.setattr(admin_mod.httpx, "get", lambda url, timeout: SimpleNamespace(status_code=200, text="ok"))
    s = Settings(database_url=f"sqlite:///{tmp_path / 'app.db'}", upload_dir=tmp_path / "up",
                 admin_password="s3cret-admin", rag_cache_dir=tmp_path / "ragcache", max_spend=3.0)
    c = TestClient(create_app(s))
    ask(c)
    pipe = built["pipe"]
    assert pipe.fallback.name == "claude" and pipe.config.answer_fallback is False

    c.put("/v1/admin/settings", json={"answer_fallback": "rag", "rag_url": "http://gpu:8100"}, headers=ADMIN)
    ask(c)
    from app.api.rag_cache import CachedRagFallback
    assert isinstance(pipe.fallback, CachedRagFallback) and pipe.fallback.url == "http://gpu:8100"
    assert pipe.config.answer_fallback is True and getattr(pipe.fallback, "_runner_wrapped", False)

    c.put("/v1/admin/settings", json={"rag_cache": False}, headers=ADMIN)
    ask(c)
    assert type(pipe.fallback).__name__ == "RagFallback"

    c.put("/v1/admin/settings", json={"answer_fallback": "off"}, headers=ADMIN)
    ask(c)
    assert pipe.fallback.name == "claude" and pipe.config.answer_fallback is False


def test_rag_cache_clear(make):
    c, _, s = make()
    from app.api.rag_cache import RagAnswerCache
    cache = RagAnswerCache(s.rag_cache_dir)
    cache.put(RagAnswerCache.key("0" * 64, "q", "v"), {"text": "x"})
    assert c.get("/v1/admin/settings", headers=ADMIN).json()["rag_cache_entries"] == 1
    assert c.post("/v1/admin/rag-cache/clear", headers=ADMIN).json() == {"removed": 1}


def test_live_cli_sets_and_resets(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VQA_DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("VQA_ANSWER_FALLBACK", "off")
    live_mod.main(["set", "answer_fallback=rag", "rag_url=http://rag-tunnel:8100"])
    out = capsys.readouterr().out
    assert "answer_fallback=rag  (live setting)" in out and "rag_cache=on  (.env)" in out
    with pytest.raises(ValueError):
        live_mod.main(["set", "answer_fallback=sometimes"])
    live_mod.main(["reset", "answer_fallback"])
    assert "answer_fallback=off  (.env)" in capsys.readouterr().out


def test_a_bad_stored_value_falls_back_to_the_default():
    s = Settings(answer_fallback="off")
    eff = live_mod.effective(s, {"answer_fallback": "nonsense", "spend_limit": "4", "unknown": "x"})
    assert eff.answer_fallback == "off" and eff.spend_limit == 4.0


def test_users_file_is_replaced_atomically(tmp_path):
    p = tmp_path / "a" / "users.htpasswd"
    acc.write_htpasswd(p, [("p01", acc.apr1("x"))])
    acc.write_htpasswd(p, [])
    assert p.read_text() == "" and not [f for f in p.parent.iterdir() if f.name.startswith(".users-")]
    assert oct(p.stat().st_mode & 0o777) == "0o644"


# ---------------------------------------------------------------------- the GPU connection (PR 2)
from app.api import gpu as gpu_mod  # noqa: E402


@pytest.mark.parametrize("host,port", [("122.117.118.68", 41413), ("ssh4.vast.ai", 22), ("gpu-1.example.org", "2222")])
def test_gpu_targets_accepted(host, port):
    assert gpu_mod.check_target(host, port) == (host, int(port))


@pytest.mark.parametrize("host,port", [("127.0.0.1", 22), ("localhost", 22), ("a b", 22), ("x;rm -rf /", 22),
                                       ("host", 0), ("host", 70000), ("host", "x"), ("", 22), ("-oProxyCommand=x", 22)])
def test_gpu_targets_refused(host, port):
    with pytest.raises(ValueError):
        gpu_mod.check_target(host, port)


def test_gpu_status_follows_the_target_and_the_tunnels_state(tmp_path):
    d = tmp_path / "gpu"
    assert gpu_mod.status(d)["state"] == "not_running"
    (d).mkdir()
    (d / "state").write_text("standby||\n")
    assert gpu_mod.status(d) == {"target": None, "state": "standby", "detail": "", "public_key": None}
    gpu_mod.set_target(d, "122.117.118.68", 41413)
    s = gpu_mod.status(d)
    assert s["target"] == {"host": "122.117.118.68", "port": 41413}
    assert s["state"] == "connecting"                    # the tunnel has not picked it up yet
    (d / "state").write_text("error|122.117.118.68 41413|Permission denied (publickey).\n")
    (d / "server_key.pub").write_text("ssh-ed25519 AAAA signcite-server\n")
    s = gpu_mod.status(d)
    assert (s["state"], s["detail"], s["public_key"]) == ("error", "Permission denied (publickey).", "ssh-ed25519 AAAA signcite-server")
    gpu_mod.clear_target(d)
    assert gpu_mod.status(d)["target"] is None and gpu_mod.status(d)["state"] == "standby"


def test_gpu_admin_endpoints(make, tmp_path, monkeypatch):
    import app.api.admin as admin_mod
    monkeypatch.setattr(admin_mod.httpx, "get", lambda url, timeout: SimpleNamespace(status_code=200, text='{"status":"ok"}'))
    gdir = tmp_path / "gpu"
    c, _, _ = make(gpu_dir=gdir)
    r = c.post("/v1/admin/gpu/connect", json={"host": "122.117.118.68", "port": 41413}, headers=ADMIN)
    assert r.status_code == 200 and r.json()["target"] == {"host": "122.117.118.68", "port": 41413}
    assert (gdir / "target").read_text() == "122.117.118.68 41413\n"
    assert c.post("/v1/admin/gpu/connect", json={"host": "localhost", "port": 22}, headers=ADMIN).status_code == 400

    (gdir / "state").write_text("connected|122.117.118.68 41413|\n")
    v = c.get("/v1/admin/gpu", headers=ADMIN).json()
    assert v["state"] == "connected" and v["rag"]["reachable"] is True and v["rag_in_use"] is False

    c.put("/v1/admin/settings", json={"answer_fallback": "rag", "rag_url": "http://rag-tunnel:8100"}, headers=ADMIN)
    assert c.get("/v1/admin/gpu", headers=ADMIN).json()["rag_in_use"] is True
    v = c.post("/v1/admin/gpu/disconnect", headers=ADMIN).json()
    assert v["target"] is None and v["rag_in_use"] is False
    assert c.get("/v1/admin/settings", headers=ADMIN).json()["live"]["answer_fallback"] == "off"   # turned off first
    assert (gdir / "target").read_text() == ""


def test_gpu_control_is_off_without_a_folder(make):
    c, _, _ = make()
    assert c.get("/v1/admin/gpu", headers=ADMIN).json() == {"enabled": False}
    assert c.post("/v1/admin/gpu/connect", json={"host": "1.2.3.4", "port": 22}, headers=ADMIN).status_code == 409


def test_gpu_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VQA_GPU_DIR", str(tmp_path / "g"))
    gpu_mod.main(["connect", "ssh4.vast.ai", "2222"])
    assert "not_running  ssh4.vast.ai:2222" in capsys.readouterr().out     # no tunnel in a test
    gpu_mod.main(["disconnect"])
    assert capsys.readouterr().out.startswith("not_running  -")


# ---------------------------------------------------------------------- CSV export
def test_csv_export_has_every_row_and_utf8(make):
    c, _, _ = make()
    for _ in range(3):
        ask(c, question="Ô tô có được đi vào không?")
    t = ask(c).json()["turn_id"]
    c.post(f"/v1/turns/{t}/feedback", json={"thumb": "down", "note": "sai biển"})
    r = c.get("/v1/admin/turns.csv", headers=ADMIN)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    text = r.content.decode("utf-8")
    assert text.startswith("﻿created_at,account,question")
    rows = list(__import__("csv").DictReader(__import__("io").StringIO(text.lstrip("﻿"))))
    assert len(rows) == 4 and rows[-1]["question"] == "Ô tô có được đi vào không?"
    fb = list(__import__("csv").DictReader(__import__("io").StringIO(
        c.get("/v1/admin/feedback.csv", headers=ADMIN).content.decode("utf-8").lstrip("﻿"))))
    assert len(fb) == 1 and fb[0]["note"] == "sai biển" and fb[0]["thumb"] == "down"
    assert c.get("/v1/admin/turns.csv").status_code == 401
